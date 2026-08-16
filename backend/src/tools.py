import aiohttp
import html
import logging
import random
from datetime import datetime

logger = logging.getLogger("tools")


# ---------------------------------------------------------------------------
# Local practice bank
# ---------------------------------------------------------------------------

LOCAL_BANK = {
    "math": {
        "easy": [
            "What is seven plus eight?",
            "What is nine times six?",
        ],
        "medium": [
            "What is the square root of one hundred forty four?",
            "Solve for x: two x plus five equals seventeen.",
        ],
        "hard": [
            "What is fifteen percent of two hundred forty?",
            "Simplify: three x squared plus five x squared.",
        ],
    },
    "calculus": {
        "easy": [
            "What is the derivative of x with respect to x?",
            "What is the derivative of a constant, like five?",
        ],
        "medium": [
            "What is the derivative of x squared with respect to x?",
            "What is the integral of two x with respect to x?",
        ],
        "hard": [
            "What is the derivative of x cubed plus three x, with respect to x?",
            "What is the integral of x squared with respect to x?",
        ],
    },
    "physics": {
        "easy": [
            "What force pulls objects toward the earth?",
            "What unit do we use to measure force?",
        ],
        "medium": [
            "State Newton's first law of motion in your own words.",
            "What is the formula relating force, mass, and acceleration?",
        ],
        "hard": [
            "What is the difference between speed and velocity?",
            "Explain why a satellite stays in orbit instead of falling to earth.",
        ],
    },
    "chemistry": {
        "easy": [
            "What is the chemical symbol for water?",
            "What is the chemical symbol for oxygen?",
        ],
        "medium": [
            "What are the three basic states of matter?",
            "What gas do we exhale when we breathe out?",
        ],
        "hard": [
            "What is the difference between an atom and a molecule?",
            "Explain what happens during a chemical reaction.",
        ],
    },
    "biology": {
        "easy": [
            "What is the powerhouse of the cell called?",
            "What organ pumps blood through the body?",
        ],
        "medium": [
            "What is photosynthesis, in simple terms?",
            "What is the function of red blood cells?",
        ],
        "hard": [
            "Explain the difference between mitosis and meiosis in one or two sentences.",
            "What role does DNA play inside a cell?",
        ],
    },
    "astrophysics": {
        "easy": [
            "What is at the center of our solar system?",
            "What is the closest planet to the sun?",
        ],
        "medium": [
            "What is a light-year a measurement of?",
            "Why does the moon appear to change shape through the month?",
        ],
        "hard": [
            "What is a black hole, in simple terms?",
            "Explain what causes a star to eventually die out.",
        ],
    },
    "evs": {
        "easy": [
            "Name one renewable source of energy.",
            "What is the main gas in the air we breathe?",
        ],
        "medium": [
            "Why is the Amazon rainforest important for the planet?",
            "What causes acid rain?",
        ],
        "hard": [
            "Explain the greenhouse effect in one sentence.",
            "What is biodiversity and why does it matter?",
        ],
    },
    "history": {
        "easy": [
            "In what year did India gain independence?",
            "Who is known as the Father of the Nation in India?",
        ],
        "medium": [
            "What was the significance of the Dandi March?",
            "Who was the first Prime Minister of India?",
        ],
        "hard": [
            "Explain briefly why the partition of India happened in 1947.",
            "What was the significance of the Quit India Movement?",
        ],
    },
    "values": {
        "easy": [
            "Why is it important to tell the truth, even when it's hard?",
            "What does it mean to be kind to someone?",
        ],
        "medium": [
            "Why do you think respecting other people's opinions matters, even when you disagree?",
            "What is the difference between being confident and being arrogant?",
        ],
        "hard": [
            "Why might treating all people with equal dignity matter, even across different cultures?",
            "How would you explain the idea of empathy to a younger student?",
        ],
    },
    "general": {
        "easy": [
            "What is the capital of India?",
            "How many continents are there on Earth?",
        ],
        "medium": [
            "Who wrote the Indian national anthem?",
            "What is the largest planet in our solar system?",
        ],
        "hard": [
            "What is the longest river in the world?",
            "Name one of the founding members of the United Nations.",
        ],
    },
}


# ---------------------------------------------------------------------------
# Open Trivia Database category mapping
# ---------------------------------------------------------------------------

_API_CATEGORY_MAP = {
    "math": 19,
    "science": 17,
    "physics": 17,
    "chemistry": 17,
    "biology": 17,
    "evs": 17,
    "history": 23,
    "general": 9,
}


_LOCAL_ONLY_SUBJECTS = {
    "calculus",
    "astrophysics",
    "values",
    "moral",
    "morals",
    "ethics",
    "human values",
}


# ---------------------------------------------------------------------------
# Day 8 - Last exercise metadata
#
# fetch_exercise() still returns a normal string to the agent.
# This metadata allows agent.py to retrieve the actual question and
# correct answer for analytics.
# ---------------------------------------------------------------------------

_last_exercise = {
    "subject": "general",
    "difficulty": "easy",
    "question": "",
    "correct_answer": "",
    "source": "",
}


def _set_last_exercise(
    subject: str,
    difficulty: str,
    question: str,
    correct_answer: str,
    source: str,
) -> None:
    global _last_exercise

    _last_exercise = {
        "subject": subject,
        "difficulty": difficulty,
        "question": question,
        "correct_answer": correct_answer,
        "source": source,
    }


def get_last_exercise() -> dict:
    """
    Return metadata for the most recently generated exercise.
    """

    return dict(_last_exercise)


# ---------------------------------------------------------------------------
# Subject normalization
# ---------------------------------------------------------------------------

def _normalize_subject(subject: str) -> str:
    """
    Map loose/free-form subject phrasing onto one of our known buckets.
    Safe against None values.
    """

    if not subject:
        return "general"

    s = str(subject).lower().strip()

    if "calc" in s:
        return "calculus"

    if "astro" in s:
        return "astrophysics"

    if "moral" in s or "ethic" in s or "value" in s:
        return "values"

    if "physic" in s:
        return "physics"

    if "chem" in s:
        return "chemistry"

    if "bio" in s:
        return "biology"

    if "evs" in s or "environ" in s:
        return "evs"

    if (
        "math" in s
        or "algebra" in s
        or "arithmetic" in s
        or "trig" in s
    ):
        return "math"

    if "hist" in s:
        return "history"

    if s in LOCAL_BANK:
        return s

    return "general"


# ---------------------------------------------------------------------------
# Exercise fetching
# ---------------------------------------------------------------------------

async def fetch_exercise(
    subject: str = "general",
    difficulty: str = "easy",
) -> str:
    """
    Fetch a practice question safely.

    The function continues to return a string for compatibility with
    the existing agent, while also recording metadata for Day 8 analytics.
    """

    safe_subj = str(subject) if subject else "general"
    safe_diff = str(difficulty) if difficulty else "easy"

    subj = _normalize_subject(safe_subj)

    diff = safe_diff.lower().strip()

    if diff not in ("easy", "medium", "hard"):
        diff = "easy"

    try:
        # ---------------------------------------------------------------
        # Try Open Trivia Database first where supported.
        # ---------------------------------------------------------------

        if (
            subj not in _LOCAL_ONLY_SUBJECTS
            and subj in _API_CATEGORY_MAP
        ):
            category_id = _API_CATEGORY_MAP[subj]
            timestamp = datetime.now().strftime("%I:%M %p")

            try:
                async with aiohttp.ClientSession() as session:
                    url = (
                        "https://opentdb.com/api.php"
                        f"?amount=1"
                        f"&category={category_id}"
                        f"&difficulty={diff}"
                        f"&type=multiple"
                    )

                    async with session.get(
                        url,
                        timeout=3.0,
                    ) as resp:

                        if resp.status == 200:
                            data = await resp.json()

                            if isinstance(data, dict):
                                results = data.get("results")

                                if (
                                    isinstance(results, list)
                                    and len(results) > 0
                                ):
                                    first_item = results[0]

                                    if isinstance(first_item, dict):
                                        raw_question = first_item.get(
                                            "question"
                                        )

                                        raw_correct_answer = (
                                            first_item.get(
                                                "correct_answer"
                                            )
                                        )

                                        if raw_question:
                                            clean_question = html.unescape(
                                                str(raw_question)
                                            )

                                            clean_answer = (
                                                html.unescape(
                                                    str(raw_correct_answer)
                                                )
                                                if raw_correct_answer
                                                else ""
                                            )

                                            _set_last_exercise(
                                                subject=subj,
                                                difficulty=diff,
                                                question=clean_question,
                                                correct_answer=clean_answer,
                                                source="Open Trivia Database",
                                            )

                                            return (
                                                "Here's a question pulled "
                                                f"live just now, at {timestamp}: "
                                                f"{clean_question}"
                                            )

            except Exception as e:
                logger.warning(
                    "External API blocked or failed: %s",
                    e,
                )

        # ---------------------------------------------------------------
        # Local fallback
        # ---------------------------------------------------------------

        fallback_question, fallback_answer = _get_local_exercise(
            subj,
            diff,
        )

        _set_last_exercise(
            subject=subj,
            difficulty=diff,
            question=fallback_question,
            correct_answer=fallback_answer,
            source="Curated practice set",
        )

        return (
            "I'm using a question from my curated practice set "
            f"for this one: {fallback_question}"
        )

    except Exception as e:
        logger.exception(
            "Complete failure in fetch_exercise: %s",
            e,
        )

        # Absolute last resort.
        fallback_question = "What is fifteen plus twenty-five?"
        fallback_answer = "forty"

        _set_last_exercise(
            subject="math",
            difficulty="easy",
            question=fallback_question,
            correct_answer=fallback_answer,
            source="Emergency fallback",
        )

        return (
            "I seem to have lost my notes for a second. "
            "Let's practice some math. "
            f"{fallback_question}"
        )


# ---------------------------------------------------------------------------
# Local question + answer bank
# ---------------------------------------------------------------------------

def _get_local_exercise(
    subject: str,
    difficulty: str,
) -> tuple[str, str]:
    """
    Return a local question together with its expected answer.
    """

    local_questions = {
        "math": {
            "easy": [
                (
                    "What is seven plus eight?",
                    "fifteen",
                ),
                (
                    "What is nine times six?",
                    "fifty-four",
                ),
            ],
            "medium": [
                (
                    "What is the square root of one hundred forty four?",
                    "twelve",
                ),
                (
                    "Solve for x: two x plus five equals seventeen.",
                    "six",
                ),
            ],
            "hard": [
                (
                    "What is fifteen percent of two hundred forty?",
                    "thirty-six",
                ),
                (
                    "Simplify: three x squared plus five x squared.",
                    "eight x squared",
                ),
            ],
        },
        "calculus": {
            "easy": [
                (
                    "What is the derivative of x with respect to x?",
                    "one",
                ),
                (
                    "What is the derivative of a constant, like five?",
                    "zero",
                ),
            ],
            "medium": [
                (
                    "What is the derivative of x squared with respect to x?",
                    "two x",
                ),
                (
                    "What is the integral of two x with respect to x?",
                    "x squared plus c",
                ),
            ],
            "hard": [
                (
                    "What is the derivative of x cubed plus three x, with respect to x?",
                    "three x squared plus three",
                ),
                (
                    "What is the integral of x squared with respect to x?",
                    "x cubed divided by three plus c",
                ),
            ],
        },
        "physics": {
            "easy": [
                (
                    "What force pulls objects toward the earth?",
                    "gravity",
                ),
                (
                    "What unit do we use to measure force?",
                    "newton",
                ),
            ],
            "medium": [
                (
                    "State Newton's first law of motion in your own words.",
                    "an object remains at rest or in uniform motion unless acted on by an external force",
                ),
                (
                    "What is the formula relating force, mass, and acceleration?",
                    "force equals mass times acceleration",
                ),
            ],
            "hard": [
                (
                    "What is the difference between speed and velocity?",
                    "speed is a scalar and velocity is a vector",
                ),
                (
                    "Explain why a satellite stays in orbit instead of falling to earth.",
                    "its forward motion and gravity combine to produce an orbit",
                ),
            ],
        },
        "chemistry": {
            "easy": [
                (
                    "What is the chemical symbol for water?",
                    "H2O",
                ),
                (
                    "What is the chemical symbol for oxygen?",
                    "O",
                ),
            ],
            "medium": [
                (
                    "What are the three basic states of matter?",
                    "solid liquid and gas",
                ),
                (
                    "What gas do we exhale when we breathe out?",
                    "carbon dioxide",
                ),
            ],
            "hard": [
                (
                    "What is the difference between an atom and a molecule?",
                    "an atom is a single unit of an element while a molecule contains two or more bonded atoms",
                ),
                (
                    "Explain what happens during a chemical reaction.",
                    "atoms are rearranged to form new substances",
                ),
            ],
        },
        "biology": {
            "easy": [
                (
                    "What is the powerhouse of the cell called?",
                    "mitochondria",
                ),
                (
                    "What organ pumps blood through the body?",
                    "heart",
                ),
            ],
            "medium": [
                (
                    "What is photosynthesis, in simple terms?",
                    "plants use sunlight carbon dioxide and water to make food",
                ),
                (
                    "What is the function of red blood cells?",
                    "to carry oxygen",
                ),
            ],
            "hard": [
                (
                    "Explain the difference between mitosis and meiosis in one or two sentences.",
                    "mitosis produces two genetically similar cells while meiosis produces four genetically different sex cells",
                ),
                (
                    "What role does DNA play inside a cell?",
                    "it stores genetic information",
                ),
            ],
        },
        "astrophysics": {
            "easy": [
                (
                    "What is at the center of our solar system?",
                    "the sun",
                ),
                (
                    "What is the closest planet to the sun?",
                    "mercury",
                ),
            ],
            "medium": [
                (
                    "What is a light-year a measurement of?",
                    "distance",
                ),
                (
                    "Why does the moon appear to change shape through the month?",
                    "because we see different portions of its sunlit side as it orbits earth",
                ),
            ],
            "hard": [
                (
                    "What is a black hole, in simple terms?",
                    "a region of space where gravity is so strong that light cannot escape",
                ),
                (
                    "Explain what causes a star to eventually die out.",
                    "it eventually exhausts the fuel needed for nuclear fusion",
                ),
            ],
        },
        "evs": {
            "easy": [
                (
                    "Name one renewable source of energy.",
                    "solar energy",
                ),
                (
                    "What is the main gas in the air we breathe?",
                    "nitrogen",
                ),
            ],
            "medium": [
                (
                    "Why is the Amazon rainforest important for the planet?",
                    "it supports biodiversity and helps regulate the climate",
                ),
                (
                    "What causes acid rain?",
                    "sulfur dioxide and nitrogen oxides reacting with water in the atmosphere",
                ),
            ],
            "hard": [
                (
                    "Explain the greenhouse effect in one sentence.",
                    "greenhouse gases trap heat in the atmosphere",
                ),
                (
                    "What is biodiversity and why does it matter?",
                    "biodiversity is the variety of life and it supports healthy ecosystems",
                ),
            ],
        },
        "history": {
            "easy": [
                (
                    "In what year did India gain independence?",
                    "1947",
                ),
                (
                    "Who is known as the Father of the Nation in India?",
                    "Mahatma Gandhi",
                ),
            ],
            "medium": [
                (
                    "What was the significance of the Dandi March?",
                    "it protested the British salt tax",
                ),
                (
                    "Who was the first Prime Minister of India?",
                    "Jawaharlal Nehru",
                ),
            ],
            "hard": [
                (
                    "Explain briefly why the partition of India happened in 1947.",
                    "political and communal divisions led to the partition into India and Pakistan",
                ),
                (
                    "What was the significance of the Quit India Movement?",
                    "it demanded an end to British rule in India",
                ),
            ],
        },
        "values": {
            "easy": [
                (
                    "Why is it important to tell the truth, even when it's hard?",
                    "because honesty builds trust",
                ),
                (
                    "What does it mean to be kind to someone?",
                    "to treat them with care respect and consideration",
                ),
            ],
            "medium": [
                (
                    "Why do you think respecting other people's opinions matters, even when you disagree?",
                    "it encourages understanding and respectful communication",
                ),
                (
                    "What is the difference between being confident and being arrogant?",
                    "confidence respects others while arrogance considers oneself superior",
                ),
            ],
            "hard": [
                (
                    "Why might treating all people with equal dignity matter, even across different cultures?",
                    "because every person deserves respect and fair treatment",
                ),
                (
                    "How would you explain the idea of empathy to a younger student?",
                    "empathy means understanding and caring about another person's feelings",
                ),
            ],
        },
        "general": {
            "easy": [
                (
                    "What is the capital of India?",
                    "New Delhi",
                ),
                (
                    "How many continents are there on Earth?",
                    "seven",
                ),
            ],
            "medium": [
                (
                    "Who wrote the Indian national anthem?",
                    "Rabindranath Tagore",
                ),
                (
                    "What is the largest planet in our solar system?",
                    "Jupiter",
                ),
            ],
            "hard": [
                (
                    "What is the longest river in the world?",
                    "Nile",
                ),
                (
                    "Name one of the founding members of the United Nations.",
                    "India",
                ),
            ],
        },
    }

    try:
        bank = local_questions.get(
            subject,
            local_questions["general"],
        )

        pool = bank.get(difficulty) or bank.get("easy", [])

        if not pool:
            pool = local_questions["general"]["easy"]

        return random.choice(pool)

    except Exception:
        return (
            "What is the capital city of India?",
            "New Delhi",
        )
