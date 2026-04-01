from __future__ import annotations

import httpx

from nanoclaw_service.config import ProviderConfig

# provider_name → AsyncClient
_clients: dict[str, httpx.AsyncClient] = {}


async def init_clients(providers: dict[str, ProviderConfig]) -> None:
    for name, cfg in providers.items():
        _clients[name] = httpx.AsyncClient(
            base_url=cfg.base_url,
            timeout=cfg.timeout,
        )


async def close_clients() -> None:
    for client in _clients.values():
        await client.aclose()
    _clients.clear()


def get_client(provider_name: str) -> httpx.AsyncClient:
    if provider_name not in _clients:
        raise KeyError(
            f"No HTTP client for provider '{provider_name}'. Check config.yaml."
        )
    return _clients[provider_name]


async def call(
    provider_name: str,
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json: dict | None = None,
) -> dict:
    client = get_client(provider_name)
    response = await client.request(method, path, params=params, json=json)
    response.raise_for_status()
    return response.json()
