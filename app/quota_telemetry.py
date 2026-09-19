from __future__ import annotations

from typing import Any, Callable

import httpx


def _root(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def parse_openrouter_key(payload: Any) -> dict[str, Any]:
    """Normalize OpenRouter key telemetry without treating credit limits as request quota."""
    data = _root(payload)
    out: dict[str, Any] = {"source": "openrouter:/api/v1/key"}

    field_map = {
        "usage": "credit_usage_total",
        "usage_daily": "credit_usage_daily",
        "usage_weekly": "credit_usage_weekly",
        "usage_monthly": "credit_usage_monthly",
        "limit": "credit_limit",
        "limit_remaining": "credit_limit_remaining",
        "limit_reset": "credit_limit_reset",
        "is_free_tier": "is_free_tier",
    }
    for source, dest in field_map.items():
        if source in data and data[source] is not None:
            out[dest] = data[source]

    return out


class QuotaTelemetry:
    def __init__(
        self,
        client: httpx.AsyncClient,
        value_resolver: Callable[[str], str | None],
    ) -> None:
        self.client = client
        self.value_resolver = value_resolver

    def _value(self, key: str) -> str | None:
        import os

        return os.getenv(key) or self.value_resolver(key)

    async def refresh(self, provider_id: str) -> dict[str, Any] | None:
        if provider_id == "openrouter":
            key = self._value("OPENROUTER_API_KEY")
            if not key:
                return None
            response = await self.client.get(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": f"Bearer {key}"},
            )
            response.raise_for_status()
            return parse_openrouter_key(response.json())

        # SiliconFlow's former /v1/user/info endpoint was retired in Aug 2026.
        # Do not reintroduce it unless an official replacement exists.
        return None
