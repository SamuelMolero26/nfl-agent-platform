from __future__ import annotations

from nanoclaw_service.config import ToolConfig


def build_claude_tool(tool_cfg: ToolConfig, remote_schema: dict | None) -> dict:
    """Convert a ToolConfig + optional remote JSON schema into a Claude tool definition."""
    if remote_schema:
        input_schema = _adapt_remote_schema(remote_schema)
    else:
        input_schema = _infer_schema_from_config(tool_cfg)

    return {
        "name": tool_cfg.name,
        "description": tool_cfg.description,
        "input_schema": input_schema,
    }


def _adapt_remote_schema(schema: dict) -> dict:
    if schema.get("type") == "object":
        return schema
    if "properties" in schema:
        return {
            "type": "object",
            "properties": schema["properties"],
            "required": schema.get("required", []),
        }
    return {"type": "object", "properties": {}, "additionalProperties": True}


def _infer_schema_from_config(tool_cfg: ToolConfig) -> dict:
    """Build a minimal schema from path params + method convention."""
    path_params = [
        seg[1:-1]
        for seg in tool_cfg.path.split("/")
        if seg.startswith("{") and seg.endswith("}")
    ]
    properties: dict = {}
    required: list[str] = []

    for param in path_params:
        properties[param] = {
            "type": "string",
            "description": f"Path parameter: {param}",
        }
        required.append(param)

    if tool_cfg.method == "GET" and not path_params:
        properties["query_params"] = {
            "type": "object",
            "description": "Optional query parameters as key-value pairs.",
            "additionalProperties": True,
        }

    if tool_cfg.method == "POST":
        properties["body"] = {
            "type": "object",
            "description": "Request body as a JSON object.",
            "additionalProperties": True,
        }
        required.append("body")

    return {"type": "object", "properties": properties, "required": required}
