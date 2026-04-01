from __future__ import annotations

import logging

from nanoclaw_service.config import ToolConfig
from nanoclaw_service.providers.http_client import call

logger = logging.getLogger(__name__)


async def execute(tool_cfg: ToolConfig, args: dict) -> dict:
    """
    Execute a tool call by dispatching to the appropriate provider HTTP client.
    Handles path parameter substitution and separates query params from body.
    """
    path = _resolve_path(tool_cfg.path, args)

    if tool_cfg.method == "GET":
        query_params = args.get("query_params") or {
            k: v
            for k, v in args.items()
            if k not in _path_params(tool_cfg.path) and k != "query_params"
        }
        result = await call(tool_cfg.provider, "GET", path, params=query_params or None)

    elif tool_cfg.method == "POST":
        if "body" in args:
            body = args["body"]
        else:
            # Remote schemas expose fields at the top level (no "body" wrapper).
            # Build the POST body from all args that are not path params.
            path_keys = set(_path_params(tool_cfg.path))
            body = {k: v for k, v in args.items() if k not in path_keys}
        result = await call(tool_cfg.provider, "POST", path, json=body)

    else:
        raise ValueError(
            f"Unsupported method '{tool_cfg.method}' for tool '{tool_cfg.name}'"
        )

    logger.debug("Tool '%s' → %s", tool_cfg.name, path)
    return result


def _resolve_path(path_template: str, args: dict) -> str:
    """Replace {param} placeholders with values from args."""
    for param in _path_params(path_template):
        value = args.get(param)
        if value is None:
            raise ValueError(f"Missing required path parameter '{param}'")
        path_template = path_template.replace(f"{{{param}}}", str(value))
    return path_template


def _path_params(path_template: str) -> list[str]:
    return [
        seg[1:-1]
        for seg in path_template.split("/")
        if seg.startswith("{") and seg.endswith("}")
    ]
