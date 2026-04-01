from __future__ import annotations

import json
import os

import redis.asyncio as aioredis

from nanoclaw_service.config import settings

_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
        )
    return _redis


# ── Session message cache ────────────────────────────────────────────────────


def _messages_key(session_id: str) -> str:
    return f"nanoclaw:session:{session_id}:messages"


def _confirmation_key(session_id: str) -> str:
    return f"nanoclaw:session:{session_id}:confirmation"


async def push_message(session_id: str, role: str, content: str) -> None:
    """Append a message to the session list, keeping only the last N turns."""
    key = _messages_key(session_id)
    r = _client()
    await r.rpush(key, json.dumps({"role": role, "content": content}))
    await r.ltrim(key, -settings.memory.max_messages_in_redis, -1)
    await r.expire(key, settings.memory.redis_ttl_seconds)


async def get_messages(session_id: str) -> list[dict]:
    """Return the hot message list for a session."""
    r = _client()
    raw = await r.lrange(_messages_key(session_id), 0, -1)
    return [json.loads(m) for m in raw]


# ── Pending confirmation state ───────────────────────────────────────────────


async def set_pending_confirmation(session_id: str, tool: str, args: dict) -> None:
    r = _client()
    key = _confirmation_key(session_id)
    await r.hset(key, mapping={"tool": tool, "args": json.dumps(args)})
    await r.expire(key, settings.memory.redis_ttl_seconds)


async def get_pending_confirmation(session_id: str) -> dict | None:
    r = _client()
    raw = await r.hgetall(_confirmation_key(session_id))
    if not raw:
        return None
    return {"tool": raw["tool"], "args": json.loads(raw["args"])}


async def clear_pending_confirmation(session_id: str) -> None:
    await _client().delete(_confirmation_key(session_id))
