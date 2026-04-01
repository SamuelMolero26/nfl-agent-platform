from __future__ import annotations

import logging

from nanoclaw_service.config import ProviderConfig, ToolConfig
from nanoclaw_service.providers.http_client import get_client
from nanoclaw_service.tools.definitions import build_claude_tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolConfig] = {}
        self._claude_tools: list[dict] = []

    async def load(
        self,
        tool_configs: list[ToolConfig],
        providers: dict[str, ProviderConfig],
    ) -> None:
        """
        Build Claude tool definitions from config.
        For tools with a schema_path, fetch the remote schema from the model platform
        and use it as the input_schema. Falls back to inferred schema on failure.
        """
        for cfg in tool_configs:
            self._tools[cfg.name] = cfg

            remote_schema: dict | None = None
            if cfg.schema_path:
                provider_cfg = providers.get(cfg.provider)
                if provider_cfg:
                    try:
                        client = get_client(cfg.provider)
                        resp = await client.get(cfg.schema_path)
                        resp.raise_for_status()
                        remote_schema = resp.json()
                    except Exception as exc:
                        logger.warning(
                            "Could not fetch schema for tool '%s' from %s%s: %s — using inferred schema.",
                            cfg.name,
                            provider_cfg.base_url,
                            cfg.schema_path,
                            exc,
                        )

            self._claude_tools.append(build_claude_tool(cfg, remote_schema))

        logger.info("Tool registry loaded: %d tools", len(self._tools))

    def claude_tools(self) -> list[dict]:
        """Return the list of tool definitions to pass to the Claude API."""
        return self._claude_tools

    def get(self, name: str) -> ToolConfig | None:
        return self._tools.get(name)

    def is_supervised(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool.supervised if tool else False

    def tool_manifest(self) -> list[dict]:
        """Summary for GET /tools — name, description, supervised flag."""
        return [
            {
                "name": cfg.name,
                "provider": cfg.provider,
                "method": cfg.method,
                "path": cfg.path,
                "supervised": cfg.supervised,
                "description": cfg.description.strip(),
            }
            for cfg in self._tools.values()
        ]


registry = ToolRegistry()
