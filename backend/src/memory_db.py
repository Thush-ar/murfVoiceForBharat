import sqlite3
import json
import os
import asyncio
import uuid
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "palo_memory.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # -----------------------------------------------------------------------
    # Students
    # -----------------------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            language_preference TEXT,
            current_level TEXT,
            topics_covered TEXT,
            learning_mistakes TEXT,
            consent_given INTEGER DEFAULT 0,
            last_interaction TEXT
        )
        """
    )

    # -----------------------------------------------------------------------
    # Day 8 - Call Analytics
    # -----------------------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS calls (
            call_id TEXT PRIMARY KEY,
            user_id TEXT,
            channel TEXT,
            outcome TEXT,
            created_at TEXT
        )
        """
    )

    # -----------------------------------------------------------------------
    # Day 8 - Detailed Call Analytics
    #
    # These columns let the teacher dashboard show:
    # - reference/call ID
    # - question asked
    # - student's answer
    # - whether the answer was correct
    # - subject and difficulty
    # - failure reason, if any
    # -----------------------------------------------------------------------

    existing_columns = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(calls)").fetchall()
    }

    new_columns = {
        "subject": "TEXT",
        "difficulty": "TEXT",
        "question": "TEXT",
        "student_answer": "TEXT",
        "correct_answer": "TEXT",
        "answer_correct": "INTEGER",
        "failure_reason": "TEXT",
    }

    for column_name, column_type in new_columns.items():
        if column_name not in existing_columns:
            cursor.execute(
                f"ALTER TABLE calls ADD COLUMN {column_name} {column_type}"
            )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Student Memory
# ---------------------------------------------------------------------------


def _sync_get_student(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            name,
            language_preference,
            current_level,
            topics_covered,
            learning_mistakes,
            consent_given
        FROM students
        WHERE user_id = ?
        """,
        (user_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "name": row[0],
            "language_preference": row[1],
            "current_level": row[2],
            "topics_covered": json.loads(row[3]) if row[3] else [],
            "learning_mistakes": json.loads(row[4]) if row[4] else [],
            "consent_given": bool(row[5]),
        }

    return None


def _sync_save_student(
    user_id: str,
    name: str,
    language_preference: str,
    current_level: str,
    topics_covered: list,
    learning_mistakes: list,
    consent_given: bool,
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute(
        """
        INSERT INTO students (
            user_id,
            name,
            language_preference,
            current_level,
            topics_covered,
            learning_mistakes,
            consent_given,
            last_interaction
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            name=excluded.name,
            language_preference=excluded.language_preference,
            current_level=excluded.current_level,
            topics_covered=excluded.topics_covered,
            learning_mistakes=excluded.learning_mistakes,
            consent_given=excluded.consent_given,
            last_interaction=excluded.last_interaction
        """,
        (
            user_id,
            name,
            language_preference,
            current_level,
            json.dumps(topics_covered),
            json.dumps(learning_mistakes),
            1 if consent_given else 0,
            now,
        ),
    )

    conn.commit()
    conn.close()


async def get_student(user_id: str):
    return await asyncio.to_thread(
        _sync_get_student,
        user_id,
    )


async def save_student(
    user_id: str,
    name: str,
    language_preference: str,
    current_level: str,
    topics_covered: list,
    learning_mistakes: list,
    consent_given: bool,
):
    return await asyncio.to_thread(
        _sync_save_student,
        user_id,
        name,
        language_preference,
        current_level,
        topics_covered,
        learning_mistakes,
        consent_given,
    )


# ---------------------------------------------------------------------------
# Day 8 - Call Analytics
# ---------------------------------------------------------------------------


def _sync_record_call(
    user_id: str,
    channel: str,
    outcome: str,
    subject: str | None = None,
    difficulty: str | None = None,
    question: str | None = None,
    student_answer: str | None = None,
    correct_answer: str | None = None,
    answer_correct: bool | None = None,
    failure_reason: str | None = None,
) -> str:

    outcome = outcome.upper().strip()

    if outcome not in {"SUCCESS", "FAILED"}:
        raise ValueError("outcome must be SUCCESS or FAILED")

    call_id = "CALL-" + uuid.uuid4().hex[:8].upper()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO calls (
            call_id,
            user_id,
            channel,
            outcome,
            created_at,
            subject,
            difficulty,
            question,
            student_answer,
            correct_answer,
            answer_correct,
            failure_reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            call_id,
            user_id,
            channel,
            outcome,
            datetime.now().isoformat(),
            subject,
            difficulty,
            question,
            student_answer,
            correct_answer,
            (
                1
                if answer_correct is True
                else 0
                if answer_correct is False
                else None
            ),
            failure_reason,
        ),
    )

    conn.commit()
    conn.close()

    return call_id


async def record_call(
    user_id: str,
    channel: str,
    outcome: str,
    subject: str | None = None,
    difficulty: str | None = None,
    question: str | None = None,
    student_answer: str | None = None,
    correct_answer: str | None = None,
    answer_correct: bool | None = None,
    failure_reason: str | None = None,
) -> str:

    return await asyncio.to_thread(
        _sync_record_call,
        user_id,
        channel,
        outcome,
        subject,
        difficulty,
        question,
        student_answer,
        correct_answer,
        answer_correct,
        failure_reason,
    )


# ---------------------------------------------------------------------------
# Day 8 - Get Overall Call Statistics
# ---------------------------------------------------------------------------


def _sync_get_call_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM calls")
    total = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM calls WHERE outcome = 'SUCCESS'"
    )
    successful = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM calls WHERE outcome = 'FAILED'"
    )
    failed = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM calls
        WHERE answer_correct = 1
        """
    )
    correct_answers = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM calls
        WHERE answer_correct = 0
        """
    )
    incorrect_answers = cursor.fetchone()[0]

    conn.close()

    return {
        "total": total,
        "successful": successful,
        "failed": failed,
        "correct_answers": correct_answers,
        "incorrect_answers": incorrect_answers,
    }


async def get_call_stats():
    return await asyncio.to_thread(
        _sync_get_call_stats
    )


# ---------------------------------------------------------------------------
# Day 8 - Get Detailed Call History
# ---------------------------------------------------------------------------


def _sync_get_call_history(limit: int = 100):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            call_id,
            user_id,
            channel,
            outcome,
            created_at,
            subject,
            difficulty,
            question,
            student_answer,
            correct_answer,
            answer_correct,
            failure_reason
        FROM calls
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "call_id": row[0],
            "user_id": row[1],
            "channel": row[2],
            "outcome": row[3],
            "created_at": row[4],
            "subject": row[5],
            "difficulty": row[6],
            "question": row[7],
            "student_answer": row[8],
            "correct_answer": row[9],
            "answer_correct": (
                bool(row[10])
                if row[10] is not None
                else None
            ),
            "failure_reason": row[11],
        }
        for row in rows
    ]


async def get_call_history(limit: int = 100):
    return await asyncio.to_thread(
        _sync_get_call_history,
        limit,
    )


# ---------------------------------------------------------------------------
# Day 8 - Get One Call By Reference ID
# ---------------------------------------------------------------------------


def _sync_get_call(call_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            call_id,
            user_id,
            channel,
            outcome,
            created_at,
            subject,
            difficulty,
            question,
            student_answer,
            correct_answer,
            answer_correct,
            failure_reason
        FROM calls
        WHERE call_id = ?
        """,
        (call_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "call_id": row[0],
        "user_id": row[1],
        "channel": row[2],
        "outcome": row[3],
        "created_at": row[4],
        "subject": row[5],
        "difficulty": row[6],
        "question": row[7],
        "student_answer": row[8],
        "correct_answer": row[9],
        "answer_correct": (
            bool(row[10])
            if row[10] is not None
            else None
        ),
        "failure_reason": row[11],
    }


async def get_call(call_id: str):
    return await asyncio.to_thread(
        _sync_get_call,
        call_id,
    )


# ---------------------------------------------------------------------------
# Initialize database when this module is imported.
# ---------------------------------------------------------------------------

init_db()
