from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml

from .models import ModelSpec, ProviderSpec, RegistryFile, TierType


def model_is_current(model: ModelSpec, now: dt.datetime | None = None) -> bool:
    expires = model.promotional_expires_at
    if not expires:
        return True
    try:
        value = dt.datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except ValueError:
        # A malformed expiry must fail closed rather than route a possibly-ended promo.
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    return current < value


class ProviderRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = self._load()

    def _load(self) -> RegistryFile:
        return RegistryFile.model_validate(
            yaml.safe_load(self.path.read_text(encoding="utf-8"))
        )

    def reload(self) -> RegistryFile:
        self.data = self._load()
        return self.data

    @property
    def providers(self) -> list[ProviderSpec]:
        return self.data.providers

    def get(self, provider_id: str) -> ProviderSpec:
        for provider in self.providers:
            if provider.id == provider_id:
                return provider
        raise KeyError(provider_id)

    def allowed_providers(
        self,
        *,
        allow_trial: bool,
        allow_promo: bool,
    ) -> list[ProviderSpec]:
        out = []
        for provider in self.providers:
            if not provider.enabled:
                continue
            if provider.tier == TierType.PERSISTENT_FREE:
                out.append(provider)
            elif provider.tier == TierType.TRIAL and allow_trial:
                out.append(provider)
            elif provider.tier == TierType.PROMOTIONAL and allow_promo:
                out.append(provider)
        return out
