from __future__ import annotations

from typing import Final

from .base import (
    ADAPTER_SDK_VERSION,
    AdapterCapabilities,
    ProviderAdapter,
    ProviderError,
    UnsupportedProviderOperation,
)

SDK_VERSION: Final[str] = ADAPTER_SDK_VERSION


def validate_adapter(name: str, adapter: ProviderAdapter) -> None:
    normalized = name.replace("_", "").replace("-", "")
    if not name or not normalized.isalnum():
        raise ValueError(
            "Adapter name must contain only letters, numbers, hyphens, or underscores"
        )
    if getattr(adapter, "sdk_version", None) != SDK_VERSION:
        raise ValueError(
            f"Adapter '{name}' targets SDK {getattr(adapter, 'sdk_version', None)!r}; "
            f"The Router requires SDK {SDK_VERSION}"
        )
    for operation in ("chat", "stream"):
        if not callable(getattr(adapter, operation, None)):
            raise TypeError(f"Adapter '{name}' is missing required operation: {operation}")


__all__ = [
    "SDK_VERSION",
    "AdapterCapabilities",
    "ProviderAdapter",
    "ProviderError",
    "UnsupportedProviderOperation",
    "validate_adapter",
]
