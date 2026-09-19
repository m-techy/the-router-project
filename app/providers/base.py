from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.models import ChatCompletionRequest, EmbeddingRequest, ProviderSpec


ADAPTER_SDK_VERSION = "1.0"


@dataclass(frozen=True)
class AdapterCapabilities:
    chat: bool = True
    stream: bool = True
    embeddings: bool = False
    transcription: bool = False


class ProviderError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class UnsupportedProviderOperation(ProviderError):
    def __init__(self, operation: str):
        super().__init__(f"Provider adapter does not support {operation}", 501)
        self.operation = operation


class ProviderAdapter(ABC):
    """Stable v1 provider adapter contract.

    Third-party adapters must implement chat + stream. Other modalities are
    optional and advertise support through the capabilities attribute.
    """

    sdk_version = ADAPTER_SDK_VERSION
    capabilities = AdapterCapabilities()

    def supports(self, operation: str) -> bool:
        return bool(getattr(self.capabilities, operation, False))

    @abstractmethod
    async def chat(
        self,
        provider: ProviderSpec,
        model: str,
        request: ChatCompletionRequest,
    ) -> tuple[dict[str, Any], httpx.Headers]:
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self,
        provider: ProviderSpec,
        model: str,
        request: ChatCompletionRequest,
    ) -> AsyncIterator[bytes]:
        raise NotImplementedError

    async def embeddings(
        self,
        provider: ProviderSpec,
        model: str,
        request: EmbeddingRequest,
    ) -> tuple[dict[str, Any], httpx.Headers]:
        raise UnsupportedProviderOperation("embeddings")

    async def transcription(
        self,
        provider: ProviderSpec,
        model: str,
        *,
        filename: str,
        data: bytes,
        content_type: str,
        language: str | None = None,
        prompt: str | None = None,
        response_format: str = "json",
        temperature: float | None = None,
    ) -> tuple[bytes, httpx.Headers, str]:
        raise UnsupportedProviderOperation("transcription")
