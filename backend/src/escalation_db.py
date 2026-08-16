import sqlite3
import os
import uuid
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "palo_memory.db")


def init_escalation_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS escalations (
        reference_id TEXT PRIMARY KEY,
        user_id TEXT,
        student_name TEXT,
        reason TEXT,
        summary TEXT,
        what_was_checked TEXT,
        urgency TEXT,
        language TEXT,
        follow_up_method TEXT,
        status TEXT DEFAULT 'open',
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


def _sync_create_escalation(
    user_id: str,
    student_name: str,
    reason: str,
    summary: str,
    what_was_checked: str,
    urgency: str,
    language: str,
    follow_up_method: str,
) -> str:

    reference_id = "ESC-" + datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO escalations (
        reference_id,
        user_id,
        student_name,
        reason,
        summary,
        what_was_checked,
        urgency,
        language,
        follow_up_method,
        status,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
    """, (
        reference_id,
        user_id,
        student_name,
        reason,
        summary,
        what_was_checked,
        urgency,
        language,
        follow_up_method,
        datetime.now().isoformat(),
    ))

    conn.commit()
    conn.close()

    return reference_id


async def create_escalation(
    user_id: str,
    student_name: str,
    reason: str,
    summary: str,
    what_was_checked: str,
    urgency: str,
    language: str,
    follow_up_method: str,
) -> str:

    import asyncio

    return await asyncio.to_thread(
        _sync_create_escalation,
        user_id,
        student_name,
        reason,
        summary,
        what_was_checked,
        urgency,
        language,
        follow_up_method,
    )


def list_escalations():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        reference_id,
        student_name,
        reason,
        summary,
        what_was_checked,
        urgency,
        language,
        follow_up_method,
        status,
        created_at
    FROM escalations
    ORDER BY created_at DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return rows
