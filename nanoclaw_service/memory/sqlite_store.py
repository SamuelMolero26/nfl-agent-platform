from __future__ import annotations

import os
from datetime import datetime, timezone

import aiosqlite

_DB_PATH = os.getenv("SQLITE_PATH", "./nanoclaw.db")


async def init_db() -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                ts TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session_id_id
            ON messages (session_id, id)
        """)
        await db.commit()


async def ensure_session(session_id: str) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO sessions (session_id, created_at) VALUES (?, ?)",
            (session_id, _now()),
        )
        await db.commit()


async def append_message(session_id: str, role: str, content: str) -> None:
    await ensure_session(session_id)
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (session_id, role, content, ts) VALUES (?, ?, ?, ?)",
            (session_id, role, content, _now()),
        )
        await db.commit()


async def get_history(session_id: str, limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT role, content, ts FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in reversed(rows)]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
