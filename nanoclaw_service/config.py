from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class ProviderConfig(BaseModel):
    base_url: str
    timeout: int = 10


class ToolConfig(BaseModel):
    name: str
    provider: str
    method: str
    path: str
    description: str
    supervised: bool = False
    schema_path: str | None = None


class AgentConfig(BaseModel):
    model: str = "claude-opus-4-6"
    max_tool_rounds: int = 6
    system_prompt: str = ""


class MemoryConfig(BaseModel):
    redis_ttl_seconds: int = 86400
    max_messages_in_redis: int = 20


class ServerConfig(BaseModel):
    port: int = 8002
    cors_origins: list[str] = ["http://localhost:3000"]


class Settings(BaseModel):
    providers: dict[str, ProviderConfig]
    tools: list[ToolConfig]
    agent: AgentConfig
    memory: MemoryConfig = MemoryConfig()
    server: ServerConfig = ServerConfig()


def _load_settings() -> Settings:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        raw: dict[str, Any] = yaml.safe_load(f)
    return Settings(**raw)


settings = _load_settings()
