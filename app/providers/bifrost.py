from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx

from app.models import ChatCompletionRequest, ProviderSpec
from app.providers.base import ProviderAdapter, ProviderError


class BifrostAdapter(ProviderAdapter):
    """Optional transport through a separately configured Bifrost gateway."""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    def _url(self) -> str:
        return os.getenv("ROUTER_BIFROST_URL", "http://bifrost:8080").rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = os.getenv("ROUTER_BIFROST_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _payload(self, provider: ProviderSpec, model: str, request: ChatCompletionRequest):
        body = request.model_dump(exclude_none=True)
        upstream_model = model
        if provider.model_prefix_strip and upstream_model.startswith(provider.model_prefix_strip):
            upstream_model = upstream_model[len(provider.model_prefix_strip):]
        body["model"] = f"{provider.id}/{upstream_model}"
        return body

    async def chat(self, provider: ProviderSpec, model: str, request: ChatCompletionRequest):
        try:
            response = await self.client.post(
                f"{self._url()}/v1/chat/completions",
                headers=self._headers(),
                json=self._payload(provider, model, request),
            )
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), None) from exc
        if response.status_code >= 400:
            raise ProviderError(response.text[:1000], response.status_code)
        return response.json(), response.headers

    async def stream(self, provider: ProviderSpec, model: str, request: ChatCompletionRequest) -> AsyncIterator[bytes]:
        payload = self._payload(provider, model, request)
        payload["stream"] = True
        try:
            async with self.client.stream(
                "POST", f"{self._url()}/v1/chat/completions", headers=self._headers(), json=payload
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise ProviderError(body.decode(errors="replace")[:1000], response.status_code)
                async for chunk in response.aiter_raw():
                    yield chunk
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), None) from exc
