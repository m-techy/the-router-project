from __future__ import annotations

import os
import re
from typing import Any

from pydantic import BaseModel, Field

from .registry import ProviderRegistry
from .state import StateStore

PLACEHOLDER_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


class SetupValue(BaseModel):
    key: str
    value: str = Field(min_length=1, max_length=20_000)


def known_setup_keys(registry: ProviderRegistry) -> set[str]:
    keys: set[str] = set()
    for provider in registry.providers:
        if provider.env_key:
            keys.add(provider.env_key)
        for match in PLACEHOLDER_RE.findall(provider.base_url):
            if match != "ROUTER_SESSION_ID":
                keys.add(match)
        for template in provider.extra_headers.values():
            for match in PLACEHOLDER_RE.findall(template):
                if match != "ROUTER_SESSION_ID":
                    keys.add(match)
    return keys


def value_source(store: StateStore, key: str) -> str:
    if os.getenv(key):
        return "environment"
    if store.get_secret(key):
        return "local"
    return "missing"


def configured_value(store: StateStore, key: str | None) -> bool:
    if not key:
        return True
    return bool(os.getenv(key) or store.get_secret(key))


def provider_setup_status(
    registry: ProviderRegistry,
    store: StateStore,
) -> list[dict[str, Any]]:
    result = []
    for provider in registry.providers:
        required: list[dict[str, Any]] = []
        if provider.env_key:
            required.append(
                {
                    "key": provider.env_key,
                    "label": "API key",
                    "secret": True,
                    "configured": configured_value(store, provider.env_key),
                    "source": value_source(store, provider.env_key),
                    "optional": provider.auth == "optional_bearer",
                }
            )

        placeholders = set(PLACEHOLDER_RE.findall(provider.base_url))
        for template in provider.extra_headers.values():
            placeholders.update(PLACEHOLDER_RE.findall(template))

        placeholders.discard("ROUTER_SESSION_ID")
        if provider.env_key:
            placeholders.discard(provider.env_key)

        for key in sorted(placeholders):
            required.append(
                {
                    "key": key,
                    "label": key.replace("_", " ").title(),
                    "secret": "KEY" in key or "TOKEN" in key or "SECRET" in key,
                    "configured": configured_value(store, key),
                    "source": value_source(store, key),
                    "optional": False,
                }
            )

        no_key = provider.auth in {"none", "optional_bearer"} or provider.env_key is None
        ready = no_key or all(item["configured"] for item in required)

        result.append(
            {
                "id": provider.id,
                "name": provider.name,
                "tier": provider.tier.value,
                "ready": ready,
                "no_key_required": no_key,
                "requirements": required,
                "signup_url": provider.signup_url,
                "docs_url": provider.docs_url,
                "verification": provider.verification,
                "notes": provider.notes,
            }
        )
    return result
