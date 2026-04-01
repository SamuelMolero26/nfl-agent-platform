from __future__ import annotations

import json
import logging
import os

import anthropic

from nanoclaw_service.agent.tool_executor import execute
from nanoclaw_service.composer.response import compose
from nanoclaw_service.config import settings
from nanoclaw_service.memory import redis_store
from nanoclaw_service.tools.registry import registry

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    """Return the shared Anthropic client, creating it lazily so that load_dotenv() has run first."""
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


async def run(
    session_id: str,
    messages: list[dict],
    confirmed_tool: dict | None = None,
) -> dict:
    """
    Main agentic loop.

    - If a supervised tool is pending confirmation and confirmed_tool matches, execute it.
    - Otherwise run the Claude loop: call Claude → execute tools → repeat until text response.
    - Returns a structured NanoClaw response dict.
    """

    # ── Handle confirmed supervised tool ────────────────────────────────────
    pending = await redis_store.get_pending_confirmation(session_id)

    if pending and confirmed_tool and confirmed_tool.get("tool") == pending["tool"]:
        tool_name = pending["tool"]
        tool_cfg = registry.get(tool_name)
        if tool_cfg:
            await redis_store.clear_pending_confirmation(session_id)
            try:
                result = await execute(tool_cfg, pending["args"])
                return await _finalize(session_id, messages, tool_name, result)
            except Exception as exc:
                logger.error("Supervised tool '%s' failed: %s", tool_name, exc)
                return _error_response(str(exc))

    # ── Standard agentic loop ────────────────────────────────────────────────
    tool_calls_made: list[str] = []
    raw_results: list[dict] = []
    current_messages = list(messages)

    for _ in range(settings.agent.max_tool_rounds):
        response = await _get_client().messages.create(
            model=settings.agent.model,
            max_tokens=4096,
            system=settings.agent.system_prompt,
            tools=registry.claude_tools(),
            messages=current_messages,
        )

        # Text response — we're done
        if response.stop_reason == "end_turn":
            text = _extract_text(response)
            return {
                "message": {"role": "assistant", "content": text},
                "visualizations": compose(tool_calls_made, raw_results),
                "tool_calls_made": tool_calls_made,
                "awaiting_confirmation": None,
            }

        # Tool use — process each tool call in the response
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_args = block.input
                tool_cfg = registry.get(tool_name)

                if tool_cfg is None:
                    tool_results.append(
                        _tool_error(block.id, f"Unknown tool: {tool_name}")
                    )
                    continue

                # Supervised tool — pause and ask for confirmation
                if registry.is_supervised(tool_name):
                    await redis_store.set_pending_confirmation(
                        session_id, tool_name, tool_args
                    )
                    text = _extract_text(response)
                    return {
                        "message": {
                            "role": "assistant",
                            "content": text
                            or f"I'd like to run **{tool_name}**. Please confirm to proceed.",
                        },
                        "visualizations": [],
                        "tool_calls_made": tool_calls_made,
                        "awaiting_confirmation": {"tool": tool_name, "args": tool_args},
                    }

                # Execute the tool
                try:
                    result = await execute(tool_cfg, tool_args)
                    tool_calls_made.append(tool_name)
                    raw_results.append({"tool": tool_name, "result": result})
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )
                except Exception as exc:
                    logger.error("Tool '%s' failed: %s", tool_name, exc)
                    tool_results.append(_tool_error(block.id, str(exc)))

            # Append assistant turn + tool results and continue the loop
            current_messages = current_messages + [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": tool_results},
            ]

    # Exceeded max_tool_rounds
    return _error_response(
        "Agent reached maximum tool rounds without a final response."
    )


async def _finalize(
    session_id: str,
    messages: list[dict],
    tool_name: str,
    result: dict,
) -> dict:
    """After executing a confirmed supervised tool, send result back to Claude for a summary."""
    followup = messages + [
        {
            "role": "user",
            "content": f"The tool {tool_name} completed successfully. Result: {json.dumps(result)}. Please summarize.",
        }
    ]
    response = await _get_client().messages.create(
        model=settings.agent.model,
        max_tokens=2048,
        system=settings.agent.system_prompt,
        messages=followup,
    )
    return {
        "message": {"role": "assistant", "content": _extract_text(response)},
        "visualizations": compose([tool_name], [{"tool": tool_name, "result": result}]),
        "tool_calls_made": [tool_name],
        "awaiting_confirmation": None,
    }


def _extract_text(response) -> str:
    for block in response.content:
        if hasattr(block, "text"):
            return block.text
    return ""


def _tool_error(tool_use_id: str, message: str) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": f"Error: {message}",
        "is_error": True,
    }


def _error_response(message: str) -> dict:
    return {
        "message": {"role": "assistant", "content": f"Something went wrong: {message}"},
        "visualizations": [],
        "tool_calls_made": [],
        "awaiting_confirmation": None,
    }
