import asyncio
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

from tools import fetch_exercise, get_last_exercise
from escalation_db import create_escalation
from memory_db import record_call

logger = logging.getLogger("agent")

load_dotenv(".env.local")


# ---------------------------------------------------------------------------
# Murf voice IDs
# ---------------------------------------------------------------------------

# main vc
ENGLISH_VOICE = "Nimisha"

# ml-in palo voice
MALAYALAM_VOICE = "Nimisha"

# voice api for math spc
MATH_SPECIALIST_VOICE = "Madhavan"


# ---------------------------------------------------------------------------
# Groq models
# ---------------------------------------------------------------------------

# Main/general tutor
MAIN_LLM_MODEL = "qwen/qwen3.6-27b"

# Stronger reasoning model for mathematics
MATH_SPECIALIST_LLM_MODEL = "openai/gpt-oss-120b"


# ---------------------------------------------------------------------------
# Palo System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are Palo, a patient, encouraging, and highly intelligent AI tutor for students.

DOMAIN KNOWLEDGE:

You are an expert across ALL fields: basic arithmetic, calculus, physics,
chemistry, biology, astrophysics, EVS, history, moral and human values,
and general knowledge.

DAY 9 SPECIALIST HANDOFF:

You are the MAIN/general tutor.

You can answer normal educational questions yourself.

However, you should NOT try to be a specialist at everything.

If the learner asks for focused mathematics practice, detailed mathematical
problem solving, step-by-step mathematics help, or wants to work through
a mathematics exercise, hand the conversation to the Maths Practice Specialist
using handoff_to_math_specialist.

Examples that SHOULD trigger the maths specialist:

- "Help me solve this equation."
- "Can you teach me quadratic equations?"
- "Give me a maths problem."
- "I need help with calculus."
- "Can we practice algebra?"
- "Explain this maths problem step by step."

Do NOT hand off simply because a question contains numbers.

For example:
- "What year did India become independent?"
should remain with Palo.

Before handing off, clearly tell the learner:

"I'll connect you to our maths specialist."

The learner should NOT need to repeat their question.

The maths specialist receives the previous conversation context
and continues naturally.

RETURN FROM MATHS SPECIALIST:

If the maths specialist has finished helping and the learner asks to
return to Palo, asks a general/non-mathematical question, or explicitly
asks to speak with Palo again, the specialist will hand the conversation
back to you.

Continue naturally from the existing conversation.

The learner must NOT need to repeat anything.

OUTBOUND CALL RULES (CRITICAL FOR PHONE CALLS):

Opening Statement:
If this is an outbound phone call, state immediately who you are,
why you are calling (daily practice call), and how to opt-out.

Guardrails:
Refuse non-educational requests (e.g. medical, financial) and suggest
talking to a parent or teacher.

VOICE & SPOKEN FORMATTING RULES (CRITICAL):

No Math/LaTeX Symbols:
Speak all mathematical expressions in plain English.

Write "x squared" NOT "x^2".

Write "the derivative of x with respect to y" NOT "d/dy(x)".

Write "plus", "minus", "divided by", "times", "integral of".
Never use raw symbols like +, -, *, /, ^, or LaTeX commands.

No Narration of Tool Calls:
Never read system tags, timestamps, brackets, function names, or tool
output framing out loud.

Never say "calling the tool", "let me check", "according to the function",
or "tool result."

If a tool returns text, fold the fact directly into your own sentence,
as if you already knew it.

Language Rules & Persistence:

By default, speak clear, natural English.

The speech recognizer only transcribes in English script.

Treat words like "Malayalam", "Malay", "Malayard", or "mallu"
as a request to switch languages and call switch_language immediately.

LOCK IN MALAYALAM: Once switched to Malayalam, respond ONLY in native
Malayalam script.

STAY IN MALAYALAM MODE: Do NOT switch back to English automatically
just because incoming transcripts arrive in English script.

Stay in Malayalam mode until the user explicitly requests
"switch to English" or "speak in English".

Never blend two languages inside a single sentence.

Length:
Keep spoken turns under 25 words so Murf Falcon TTS stays ultra-fast.

Tool Usage:

If a user asks for a test, quiz, practice question, or exercise,
call get_next_exercise.

If a user asks to change languages, or says anything that could be
a mangled attempt at "Malayalam" or "English" in that context,
call switch_language immediately, before answering their underlying question.

PRACTICE QUESTION FLOW:

When you fetch an exercise, remember its subject, difficulty, and question.

Ask the learner to answer the question.

Listen carefully to the learner's answer.

Respond naturally by explaining whether the answer is correct.

Do not reveal internal analytics or database information.

HUMAN HELP / ESCALATION:

If the learner explicitly asks to speak with a teacher or human,
offer to create a human-help request.

If the learner is clearly frustrated and says they need help from a teacher,
offer escalation instead of repeatedly trying the same explanation.

BEFORE creating an escalation, briefly tell the learner what information
you intend to share and ask for permission.

NEVER call create_human_help_request before the learner gives clear permission.

If the learner says no, do not create a request and respect their decision.

Only share useful information:
who needs help, what happened, what Palo already tried,
urgency, language, and preferred follow-up method.

Never include passwords, OTPs, PINs, account numbers,
or unnecessary private information.

After creating a request, tell the learner the reference ID and explain
that it has been recorded for teacher follow-up.

Do not promise that a teacher will respond immediately unless that is
actually guaranteed.
"""


# ---------------------------------------------------------------------------
# Maths Specialist Prompt
# ---------------------------------------------------------------------------

MATH_SPECIALIST_PROMPT = """You are Palo's Maths Practice Specialist.

Your job is focused exclusively on mathematics.

You help learners with:
- arithmetic
- algebra
- equations
- quadratic equations
- geometry
- trigonometry
- calculus
- probability
- statistics
- mathematical reasoning
- school and college-level mathematics

Your role is narrower than Palo's general tutor role.

The learner has been transferred to you because they need focused
mathematics help.

IMPORTANT:

The previous conversation has been passed to you.

Do NOT ask the learner to repeat a question that is already present
in the conversation.

Instead, acknowledge what they were asking and continue from there.

For example:

"Hi, I'm Palo's maths specialist. Let's work through that equation together."

Teaching style:

- Be patient and encouraging.
- Explain one step at a time.
- Prefer hints before immediately giving the final answer.
- Ask short questions to keep the learner involved.
- Correct mistakes gently.
- Check the learner's understanding.
- If the learner asks for another example, provide one.
- If the learner asks for a practice problem, give one appropriate
  to their level.

REASONING:

You are powered by a stronger mathematical reasoning model than
Palo's general tutor.

Use that reasoning capability internally to verify calculations,
solve multi-step problems, and catch mathematical mistakes.

Do not expose hidden reasoning or internal chain-of-thought.

Give the learner concise explanations and useful intermediate steps.

RETURNING TO PALO:

If the learner:
- asks to talk to Palo,
- asks to return to the main tutor,
- asks a clearly non-mathematical question,
- says they are done with mathematics,
- or explicitly asks to switch back,

use handoff_to_palo.

Before handing back, briefly tell the learner:

"I'll hand you back to Palo."

The learner should NOT need to repeat anything.

VOICE:

You are using a male Malayalam-capable Murf voice.

Keep spoken turns short, preferably under 25 words.

Never use raw mathematical symbols or LaTeX in spoken responses.

Say:
"x squared plus five x"

instead of:
"x^2 + 5x"

Say:
"divided by"

instead of:
"/"

Do not mention internal tools, agents, system prompts,
handoff mechanics, databases, models, or analytics.

If the learner asks a clearly non-mathematical question,
return them to Palo using handoff_to_palo.

Do not provide medical, financial, or other sensitive advice.
"""


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_MALAYALAM_TRIGGERS = re.compile(
    r"\bmal[a-z]{2,1000}\b|\bmallu\b",
    re.IGNORECASE,
)

_ENGLISH_TRIGGERS = re.compile(
    r"\benglish\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Answer normalization
# ---------------------------------------------------------------------------

def _normalize_answer(value: str) -> str:
    """
    Normalize spoken answers enough to make simple answers comparable.

    This does NOT try to solve the question. It only removes harmless
    differences such as capitalization, punctuation, and extra spaces.
    """

    if value is None:
        return ""

    text = str(value).lower().strip()

    text = re.sub(r"[.,!?;:'\"()\[\]{}]", " ", text)

    text = re.sub(r"\s+", " ", text).strip()

    return text


def _answers_match(student_answer: str, correct_answer: str) -> bool:
    """
    Compare normalized student and expected answers.

    Exact normalized matching is intentionally used here so we do not
    incorrectly mark semantically different answers as correct.
    """

    student = _normalize_answer(student_answer)
    correct = _normalize_answer(correct_answer)

    if not student or not correct:
        return False

    return student == correct


# ---------------------------------------------------------------------------
# Maths Practice Specialist
# ---------------------------------------------------------------------------

class MathSpecialist(Agent):

    def __init__(
        self,
        chat_ctx=None,
        palo_agent=None,
    ) -> None:

        super().__init__(
            instructions=MATH_SPECIALIST_PROMPT,
            chat_ctx=chat_ctx,

            # Stronger Groq reasoning model
            llm=groq.LLM(
                model=MATH_SPECIALIST_LLM_MODEL,
            ),

            # Specialist voice
            tts=murf.TTS(
                voice=MATH_SPECIALIST_VOICE,
                style="Conversation",
                text_pacing=True,
            ),
        )

        # --------------------------------------------------------------
        # Keep a reference to the ORIGINAL Palo agent.
        #
        # This is important.
        #
        # We do NOT create a brand-new Assistant when returning.
        # We return the same Palo instance that originally handed
        # the learner to the specialist.
        # --------------------------------------------------------------

        self.palo_agent = palo_agent

    async def on_enter(self) -> None:
        """
        Introduce the specialist after the handoff.
        """

        logger.info(
            "Day 9: Maths Specialist entered | "
            "LLM=%s | TTS=%s",
            MATH_SPECIALIST_LLM_MODEL,
            MATH_SPECIALIST_VOICE,
        )

        await self.session.generate_reply(
            instructions=(
                "Say briefly: 'Hi, I'm Palo's maths specialist.' "
                "Then immediately continue helping with the mathematics "
                "question already present in the conversation. "
                "Do not ask the learner to repeat the question."
            )
        )

    # ----------------------------------------------------------------------
    # Return handoff: Maths Specialist -> Palo
    # ----------------------------------------------------------------------

    @function_tool(
        description=(
            "Hand the learner back to Palo, the main general tutor. "
            "Use this when the learner asks to return to Palo, asks for "
            "the main tutor, finishes mathematics and wants general help, "
            "or asks a clearly non-mathematical question. "
            "The learner should not need to repeat anything."
        )
    )
    async def handoff_to_palo(
        self,
        context: RunContext,
    ):
        """
        Return the learner to the ORIGINAL Palo agent.

        This preserves Palo's existing state instead of creating a
        completely new Assistant instance.
        """

        logger.info(
            "Day 9: Handoff requested -> Palo"
        )

        if self.palo_agent is None:
            logger.error(
                "Cannot hand off to Palo: original Palo agent "
                "reference is missing."
            )

            return (
                None,
                "Palo is unavailable right now."
            )

        logger.info(
            "Day 9: Returning to original Palo agent instance."
        )

        return (
            self.palo_agent,
            "Returning the learner to Palo, the main tutor.",
        )


# ---------------------------------------------------------------------------
# Palo Assistant
# ---------------------------------------------------------------------------

class Assistant(Agent):

    def __init__(self) -> None:

        super().__init__(
            instructions=SYSTEM_PROMPT
        )

        self.current_language = "english"

        # ------------------------------------------------------------------
        # Day 8 analytics state
        # ------------------------------------------------------------------

        self.exercise_requested = False

        self.exercise_subject = ""
        self.exercise_difficulty = ""
        self.exercise_question = ""

        self.student_answer = ""

        self.correct_answer = ""
        self.answer_correct = None

        self.awaiting_answer = False

    # ----------------------------------------------------------------------
    # Day 9 - Maths Specialist Handoff
    # ----------------------------------------------------------------------

    @function_tool(
        description=(
            "Hand off the learner to Palo's Maths Practice Specialist. "
            "Use this when the learner needs focused mathematics help, "
            "such as solving equations, algebra, calculus, geometry, "
            "mathematical problem solving, or mathematics practice. "
            "Do NOT use this for ordinary questions that merely contain "
            "numbers. Before using this tool, tell the learner that you "
            "will connect them to the maths specialist."
        )
    )
    async def handoff_to_math_specialist(
        self,
        context: RunContext,
    ):
        """
        Transfer the conversation to the maths specialist.

        The existing conversation history is copied so the learner
        does not need to repeat their question.
        """

        logger.info(
            "Day 9: Handoff requested -> Maths Specialist"
        )

        # --------------------------------------------------------------
        # Preserve conversation history.
        #
        # Exclude Palo's system instructions so the specialist receives
        # the conversation but not the main tutor's system prompt.
        # --------------------------------------------------------------

        specialist_context = self.chat_ctx.copy(
            exclude_instructions=True,
        )

        specialist = MathSpecialist(
            chat_ctx=specialist_context,

            # ----------------------------------------------------------
            # CRITICAL:
            # Give the specialist the ORIGINAL Palo instance.
            # ----------------------------------------------------------

            palo_agent=self,
        )

        return (
            specialist,
            "Transferring the learner to the Maths Practice Specialist.",
        )

    # ----------------------------------------------------------------------
    # Practice exercise tool
    # ----------------------------------------------------------------------

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

        logger.info(
            "Tool triggered -> Subject: %s, Difficulty: %s",
            subject,
            difficulty,
        )

        try:
            result = await fetch_exercise(
                subject,
                difficulty,
            )

            exercise = get_last_exercise()

            self.exercise_requested = True

            # Reset answer state for the new exercise.
            self.student_answer = ""
            self.answer_correct = None

            if exercise:

                self.exercise_subject = exercise.get(
                    "subject",
                    str(subject),
                )

                self.exercise_difficulty = exercise.get(
                    "difficulty",
                    str(difficulty),
                )

                self.exercise_question = exercise.get(
                    "question",
                    result,
                )

                self.correct_answer = exercise.get(
                    "correct_answer",
                    "",
                )

            else:

                self.exercise_subject = str(subject)
                self.exercise_difficulty = str(difficulty)
                self.exercise_question = result
                self.correct_answer = ""

            self.awaiting_answer = True

            logger.info(
                "Day 8 exercise stored -> "
                "subject=%s difficulty=%s question=%s correct_answer=%s",
                self.exercise_subject,
                self.exercise_difficulty,
                self.exercise_question,
                self.correct_answer,
            )

            return result

        except Exception as e:

            logger.exception(
                "fetch_exercise failed for subject='%s': %s",
                subject,
                e,
            )

            self.awaiting_answer = False
            self.exercise_requested = False

            return (
                "I couldn't pull a question just now — "
                "could you ask me again in a moment?"
            )

    # ----------------------------------------------------------------------
    # Human escalation tool
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # Language switching tool
    # ----------------------------------------------------------------------

    @function_tool(
        description=(
            "Switch the spoken language between English and Malayalam. "
            "Call this the instant the student asks to switch languages, "
            "or says a word that could be a mis-transcribed attempt at "
            "'Malayalam' or 'English'."
        )
    )
    async def switch_language(
        self,
        language: str,
    ) -> str:

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
                    "Failed to switch TTS to Malayalam: %s",
                    e,
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
                    "Failed to switch TTS to English: %s",
                    e,
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


# ---------------------------------------------------------------------------
# LiveKit server
# ---------------------------------------------------------------------------

server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


# ---------------------------------------------------------------------------
# Main LiveKit session
# ---------------------------------------------------------------------------

@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):

    session = AgentSession(

        # ------------------------------------------------------------------
        # STT
        # ------------------------------------------------------------------

        stt=deepgram.STT(
            model="nova-3",
            language="en-IN",
        ),

        # ------------------------------------------------------------------
        # Main/general tutor LLM
        # ------------------------------------------------------------------

        llm=groq.LLM(
            model=MAIN_LLM_MODEL,
        ),

        # ------------------------------------------------------------------
        # Default Palo TTS
        # ------------------------------------------------------------------

        tts=murf.TTS(
            voice=ENGLISH_VOICE,
            style="Conversation",
            text_pacing=True,
        ),

        # ------------------------------------------------------------------
        # VAD
        # ------------------------------------------------------------------

        vad=ctx.proc.userdata["vad"],

        preemptive_generation=False,
    )

    # ----------------------------------------------------------------------
    # Create Palo
    # ----------------------------------------------------------------------

    assistant = Assistant()

    # ----------------------------------------------------------------------
    # Day 6 SIP detection
    # ----------------------------------------------------------------------

    room_name = ctx.room.name.lower()

    is_sip_call = (
        "sip" in room_name
        or "call" in room_name
    )

    for participant in ctx.room.remote_participants.values():

        if (
            participant.kind
            == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
            or "sip" in participant.identity.lower()
        ):
            is_sip_call = True
            break

    channel = "sip" if is_sip_call else "browser"

    # ----------------------------------------------------------------------
    # Day 8: capture learner answer
    # ----------------------------------------------------------------------

    def on_conversation_item_added(event):

        """
        Capture the learner's committed answer.

        This deliberately checks for role=user so Day 9 handoff events
        and other conversation items cannot accidentally become answers.
        """

        if not assistant.awaiting_answer:
            return

        item = getattr(event, "item", None)

        if item is None:
            return

        if getattr(item, "role", None) != "user":
            return

        transcript = getattr(
            item,
            "text_content",
            "",
        )

        if not transcript:
            return

        assistant.student_answer = transcript.strip()

        assistant.awaiting_answer = False

        if assistant.correct_answer:

            assistant.answer_correct = _answers_match(
                assistant.student_answer,
                assistant.correct_answer,
            )

        else:

            assistant.answer_correct = None

        logger.info(
            "Day 8 student answer captured: %s",
            assistant.student_answer,
        )

        logger.info(
            "Day 8 answer evaluation: "
            "correct_answer=%s answer_correct=%s",
            assistant.correct_answer,
            assistant.answer_correct,
        )

    session.on(
        "conversation_item_added",
        on_conversation_item_added,
    )

    # ----------------------------------------------------------------------
    # Day 8: save analytics
    # ----------------------------------------------------------------------

    call_recorded = False

    async def record_call_outcome():

        nonlocal call_recorded

        if call_recorded:
            return

        call_recorded = True

        if assistant.answer_correct is True:

            outcome = "SUCCESS"
            failure_reason = None

        else:

            outcome = "FAILED"

            if not assistant.exercise_requested:

                failure_reason = (
                    "Practice exercise was not completed because "
                    "an exercise could not be fetched."
                )

            elif assistant.student_answer:

                failure_reason = (
                    "Learner answered the exercise incorrectly."
                )

            else:

                failure_reason = (
                    "Learner did not provide an answer before the call ended."
                )

        logger.info(
            "Day 8 call outcome: "
            "channel=%s outcome=%s subject=%s difficulty=%s "
            "answer_correct=%s",
            channel,
            outcome,
            assistant.exercise_subject,
            assistant.exercise_difficulty,
            assistant.answer_correct,
        )

        try:

            call_id = await record_call(
                user_id="local-demo-user",
                channel=channel,
                outcome=outcome,
                subject=assistant.exercise_subject,
                difficulty=assistant.exercise_difficulty,
                question=assistant.exercise_question,
                student_answer=assistant.student_answer,
                correct_answer=assistant.correct_answer,
                answer_correct=assistant.answer_correct,
                failure_reason=failure_reason,
            )

            logger.info(
                "Day 8 analytics saved: "
                "call_id=%s outcome=%s answer_correct=%s",
                call_id,
                outcome,
                assistant.answer_correct,
            )

        except Exception:

            logger.exception(
                "Failed to save Day 8 call analytics."
            )

    def on_session_close(*args):

        logger.info(
            "Agent session closed. "
            "Recording Day 8 detailed analytics."
        )

        asyncio.create_task(
            record_call_outcome()
        )

    session.on(
        "close",
        on_session_close,
    )

    # ----------------------------------------------------------------------
    # Start session
    # ----------------------------------------------------------------------

    await session.start(
        agent=assistant,
        room=ctx.room,
    )

    # ----------------------------------------------------------------------
    # Initial greeting
    # ----------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli.run_app(server)
