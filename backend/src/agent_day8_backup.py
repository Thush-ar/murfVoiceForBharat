import logging
import re

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
)
from livekit.plugins import deepgram, groq, murf, silero

from tools import fetch_exercise
from escalation_db import create_escalation


logger = logging.getLogger("agent")

load_dotenv(".env.local")


# --- Murf voice IDs ----------------------------------------------------------

ENGLISH_VOICE = "Nimisha"
MALAYALAM_VOICE = "Nimisha"


SYSTEM_PROMPT = """You are Palo, a patient, encouraging, and highly intelligent AI tutor for students.

DOMAIN KNOWLEDGE:

- You are an expert across ALL fields: basic arithmetic, calculus, physics, chemistry, biology, astrophysics, EVS, history, moral and human values, and general knowledge.

OUTBOUND CALL RULES (CRITICAL FOR PHONE CALLS):

1. Opening Statement:
   If this is an outbound phone call, state immediately who you are, why you are calling (daily practice call), and how to opt-out.

2. Guardrails:
   Refuse non-educational requests (e.g. medical, financial) and suggest talking to a parent or teacher.

VOICE & SPOKEN FORMATTING RULES (CRITICAL):

1. No Math/LaTeX Symbols:
   Speak all mathematical expressions in plain English.
   - Write "x squared" NOT "x^2".
   - Write "the derivative of x with respect to y" NOT "d/dy(x)".
   - Write "plus", "minus", "divided by", "times", "integral of".
   Never use raw symbols like +, -, *, /, ^, or LaTeX commands.

2. No Narration of Tool Calls:
   Never read system tags, timestamps, brackets, function names, or tool output framing out loud.
   Never say "calling the tool", "let me check", "according to the function",
   or "tool result."
   If a tool returns text, fold the fact directly into your own sentence,
   as if you already knew it.

3. Language Rules & Persistence:
   - By default, speak clear, natural English.
   - The speech recognizer only transcribes in English script.
   - Treat words like "Malayalam", "Malay", "Malayard", or "mallu"
     as a request to switch languages and call switch_language immediately.
   - LOCK IN MALAYALAM: Once switched to Malayalam, respond ONLY in native
     Malayalam script.
   - STAY IN MALAYALAM MODE: Do NOT switch back to English automatically
     just because incoming transcripts arrive in English script.
   - Stay in Malayalam mode until the user explicitly requests
     "switch to English" or "speak in English".
   - Never blend two languages inside a single sentence.

4. Length:
   Keep spoken turns under 25 words so Murf Falcon TTS stays ultra-fast.

5. Tool Usage:
   - If a user asks for a test, quiz, practice question, or exercise,
     call get_next_exercise.
   - If a user asks to change languages, or says anything that could be
     a mangled attempt at "Malayalam" or "English" in that context,
     call switch_language immediately, before answering their underlying question.

HUMAN HELP / ESCALATION:

- If the learner explicitly asks to speak with a teacher or human,
  offer to create a human-help request.

- If the learner is clearly frustrated and says they need help from a teacher,
  offer escalation instead of repeatedly trying the same explanation.

- BEFORE creating an escalation, briefly tell the learner what information
  you intend to share and ask for permission.

- NEVER call create_human_help_request before the learner gives clear permission.

- If the learner says no, do not create a request and respect their decision.

- Only share useful information:
  who needs help, what happened, what Palo already tried,
  urgency, language, and preferred follow-up method.

- Never include passwords, OTPs, PINs, account numbers,
  or unnecessary private information.

- After creating a request, tell the learner the reference ID and explain
  that it has been recorded for teacher follow-up.

- Do not promise that a teacher will respond immediately unless that is
  actually guaranteed.
"""


# Loose matcher for how Deepgram is likely to mangle "Malayalam"
# in en-IN mode.

_MALAYALAM_TRIGGERS = re.compile(
    r"\bmal[a-z]{2,1000}\b|\bmallu\b",
    re.IGNORECASE,
)

_ENGLISH_TRIGGERS = re.compile(
    r"\benglish\b",
    re.IGNORECASE,
)


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        self.current_language = "english"

    @function_tool(
        description=(
            "Fetch a practice exercise or quiz question for a student. "
            "Covers math, calculus, physics, chemistry, biology, astrophysics, "
            "EVS, history, general knowledge, and moral or human values discussions."
        )
    )
    async def get_next_exercise(
        self,
        subject: str = "general",
        difficulty: str = "easy",
    ) -> str:
        """Called automatically when the student requests practice or quiz questions."""

        logger.info(
            f"Tool triggered -> Subject: {subject}, Difficulty: {difficulty}"
        )

        try:
            result = await fetch_exercise(subject, difficulty)
        except Exception as e:
            logger.exception(
                f"fetch_exercise failed for subject='{subject}': {e}"
            )
            result = (
                "I couldn't pull a question just now — "
                "could you ask me again in a moment?"
            )

        return result

    @function_tool(
        description=(
            "Create a human-help request for a learner. "
            "Use this only when the learner explicitly asks for a teacher or human, "
            "or is seriously frustrated and needs teacher assistance. "
            "IMPORTANT: Only call this AFTER the learner has explicitly "
            "given permission to share the necessary information."
        )
    )
    async def create_human_help_request(
        self,
        reason: str,
        summary: str,
        what_was_checked: str,
        urgency: str = "medium",
        follow_up_method: str = "teacher follow-up",
    ) -> str:
        """Create a human-help request after the learner gives consent."""

        # Temporary identity for the Day 7 demo.
        # We will connect this to palo_memory.db later.
        user_id = "local-demo-user"
        student_name = "Palo learner"

        urgency = urgency.lower().strip()

        if urgency not in {"low", "medium", "high"}:
            urgency = "medium"

        reference_id = await create_escalation(
            user_id=user_id,
            student_name=student_name,
            reason=reason,
            summary=summary,
            what_was_checked=what_was_checked,
            urgency=urgency,
            language=self.current_language,
            follow_up_method=follow_up_method,
        )

        logger.info(
            "Human-help request created: %s",
            reference_id,
        )

        return (
            f"Human help request created. Reference ID is {reference_id}. "
            "Tell the learner that the request has been recorded "
            "for teacher follow-up."
        )

    @function_tool(
        description=(
            "Switch the spoken language between English and Malayalam. "
            "Call this the instant the student asks to switch languages, "
            "or says a word that could be a mis-transcribed attempt at "
            "'Malayalam' or 'English'."
        )
    )
    async def switch_language(self, language: str) -> str:
        """Called when the student wants to change the spoken language."""

        lang = language.lower().strip()
        session = self.session

        if _MALAYALAM_TRIGGERS.search(lang) or "malayalam" in lang:
            self.current_language = "malayalam"

            try:
                session.tts.update_options(
                    voice=MALAYALAM_VOICE,
                    style="Conversation",
                )
            except Exception as e:
                logger.exception(
                    f"Failed to switch TTS to Malayalam: {e}"
                )

            return (
                "SUCCESS: Switched to Malayalam. "
                "Now greet the user or answer their question directly "
                "in native Malayalam script. "
                "Do not recite 'Language switched'."
            )

        if _ENGLISH_TRIGGERS.search(lang) or "english" in lang:
            self.current_language = "english"

            try:
                session.tts.update_options(
                    voice=ENGLISH_VOICE,
                    style="Conversation",
                )
            except Exception as e:
                logger.exception(
                    f"Failed to switch TTS to English: {e}"
                )

            return (
                "SUCCESS: Switched to English. "
                "Now greet the user or answer their question directly "
                "in clear English. "
                "Do not recite 'Language switched'."
            )

        return (
            f"System note: '{language}' is unsupported. "
            f"Continue naturally in {self.current_language} "
            "without mentioning system errors."
        )


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    session = AgentSession(
        stt=deepgram.STT(
            model="nova-3",
            language="en-IN",
        ),
        llm=groq.LLM(
            model="qwen/qwen3.6-27b",
        ),
        tts=murf.TTS(
            voice="Nimisha",
            style="Conversation",
            text_pacing=True,
        ),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=False,
    )

    await session.start(
        agent=Assistant(),
        room=ctx.room,
    )

    # Check room name and remote participants for SIP indicators.
    room_name = ctx.room.name.lower()
    is_sip_call = "sip" in room_name or "call" in room_name

    for participant in ctx.room.remote_participants.values():
        if (
            participant.kind
            == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
            or "sip" in participant.identity.lower()
        ):
            is_sip_call = True
            break

    # Deliver greeting tailored for inbound web vs phone call.
    if is_sip_call:
        await session.say(
            "Hello! This is Palo calling for your daily 2-minute practice session. "
            "If you would like to stop receiving these daily calls, just tell me "
            "to stop calls. Are you ready for today's practice question?",
            allow_interruptions=True,
        )
    else:
        await session.say(
            "Namaste! I am Palo, your AI tutor. "
            "Ask me anything about math, science, or general topics, "
            "or ask for a practice question!",
            allow_interruptions=True,
        )


if __name__ == "__main__":
    cli.run_app(server)
