from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nanoclaw_service.agent import core
from nanoclaw_service.memory import redis_store, sqlite_store

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response schemas ───────────────────────────────────────────────


class Message(BaseModel):
    role: str
    content: str


class ConfirmedTool(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)


class ChatRequest(BaseModel):
    session_id: str
    messages: list[Message]
    confirmed_tool: ConfirmedTool | None = (
        None  # set when user approves a supervised tool
    )


class VisualizationSpec(BaseModel):
    type: str  # "bar" | "line" | "table" | "shap" | "graph"
    title: str
    data: list | dict
    config: dict


class AwaitingConfirmation(BaseModel):
    tool: str
    args: dict


class ChatResponse(BaseModel):
    message: Message
    visualizations: list[VisualizationSpec]
    tool_calls_made: list[str]
    awaiting_confirmation: AwaitingConfirmation | None


# ── Endpoint ─────────────────────────────────────────────────────────────────


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    messages = [m.model_dump() for m in req.messages]
    confirmed = req.confirmed_tool.model_dump() if req.confirmed_tool else None

    # Persist incoming user message to durable log
    user_turn = next((m for m in reversed(messages) if m["role"] == "user"), None)
    if user_turn:
        await sqlite_store.append_message(req.session_id, "user", user_turn["content"])
        await redis_store.push_message(req.session_id, "user", user_turn["content"])

    try:
        result = await core.run(req.session_id, messages, confirmed_tool=confirmed)
    except Exception as exc:
        logger.exception("Agent error for session %s", req.session_id)
        raise HTTPException(status_code=500, detail="Internal server error")

    # Persist assistant reply
    reply_content = result["message"]["content"]
    await sqlite_store.append_message(req.session_id, "assistant", reply_content)
    await redis_store.push_message(req.session_id, "assistant", reply_content)

    return ChatResponse(
        message=Message(**result["message"]),
        visualizations=[
            VisualizationSpec(**v) for v in result.get("visualizations", [])
        ],
        tool_calls_made=result.get("tool_calls_made", []),
        awaiting_confirmation=(
            AwaitingConfirmation(**result["awaiting_confirmation"])
            if result.get("awaiting_confirmation")
            else None
        ),
    )


@router.get("/history/{session_id}")
async def get_history(session_id: str, limit: int = 50):
    """Retrieve full conversation history for a session from SQLite."""
    limit = max(1, min(limit, 500))
    messages = await sqlite_store.get_history(session_id, limit=limit)
    return {"session_id": session_id, "messages": messages}
