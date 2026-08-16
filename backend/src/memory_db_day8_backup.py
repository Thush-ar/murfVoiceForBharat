
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

    cursor.execute("""
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
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            call_id TEXT PRIMARY KEY,
            user_id TEXT,
            channel TEXT,
            outcome TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


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
    return await asyncio.to_thread(_sync_get_student, user_id)


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
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            call_id,
            user_id,
            channel,
            outcome,
            datetime.now().isoformat(),
        ),
    )

    conn.commit()
    conn.close()

    return call_id


async def record_call(
    user_id: str,
    channel: str,
    outcome: str,
) -> str:
    return await asyncio.to_thread(
        _sync_record_call,
        user_id,
        channel,
        outcome,
    )


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

    conn.close()

    return {
        "total": total,
        "successful": successful,
        "failed": failed,
    }


async def get_call_stats():
    return await asyncio.to_thread(_sync_get_call_stats)

