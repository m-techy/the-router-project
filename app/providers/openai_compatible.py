from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any, Callable

import httpx

from app.models import ChatCompletionRequest, ProviderSpec
from app.normalization import normalize_request_body
from app.providers.base import ProviderAdapter, ProviderError


class OpenAICompatibleAdapter(ProviderAdapter):
    def __init__(
        self,
        client: httpx.AsyncClient,
        value_resolver: Callable[[str], str | None] | None = None,
    ):
        self.client = client
        self._session_id = str(uuid.uuid4())
        self._value_resolver = value_resolver or (lambda _: None)

    def _value(self, key: str | None) -> str | None:
        if not key:
            return None
        return os.getenv(key) or self._value_resolver(key)

    def _api_key(self, provider: ProviderSpec) -> str | None:
        return self._value(provider.env_key)

    def _base_url(self, provider: ProviderSpec) -> str:
        url = provider.base_url
        placeholders = set()
        start = 0
        while True:
            start = url.find("${", start)
            if start < 0:
                break
            end = url.find("}", start)
            if end < 0:
                break
            placeholders.add(url[start + 2 : end])
            start = end + 1

        for key in placeholders:
            value = self._value(key)
            if value:
                url = url.replace("${" + key + "}", value)
        return url.rstrip("/")

    def _headers(self, provider: ProviderSpec) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = self._api_key(provider)
        if key and provider.auth in {"bearer", "optional_bearer"}:
            headers["Authorization"] = f"Bearer {key}"

        for header_name, template in provider.extra_headers.items():
            value = template.replace("${ROUTER_SESSION_ID}", self._session_id)
            start = 0
            while True:
                start = value.find("${", start)
                if start < 0:
                    break
                end = value.find("}", start)
                if end < 0:
                    break
                key_name = value[start + 2 : end]
                replacement = self._value(key_name)
                if replacement:
                    value = value.replace("${" + key_name + "}", replacement)
                start = end + 1
            headers[header_name] = value
        return headers

    def _model_id(self, provider: ProviderSpec, model: str) -> str:
        if provider.model_prefix_strip and model.startswith(provider.model_prefix_strip):
            return model[len(provider.model_prefix_strip) :]
        return model

    def _payload(
        self,
        provider: ProviderSpec,
        model: str,
        request: ChatCompletionRequest,
    ) -> dict[str, Any]:
        body = request.model_dump(exclude_none=True)
        body["model"] = self._model_id(provider, model)
        return normalize_request_body(provider.id, body)

    async def chat(
        self,
        provider: ProviderSpec,
        model: str,
        request: ChatCompletionRequest,
    ):
        if (
            provider.env_key
            and provider.auth == "bearer"
            and not self._api_key(provider)
        ):
            raise ProviderError(f"Missing API key: {provider.env_key}", 401)
        try:
            response = await self.client.post(
                f"{self._base_url(provider)}/chat/completions",
                headers=self._headers(provider),
                json=self._payload(provider, model, request),
            )
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), None) from exc

        if response.status_code >= 400:
            raise ProviderError(response.text[:1000], response.status_code)

        try:
            return response.json(), response.headers
        except ValueError as exc:
            raise ProviderError(
                "Provider returned a non-JSON response",
                response.status_code,
            ) from exc

    async def stream(
        self,
        provider: ProviderSpec,
        model: str,
        request: ChatCompletionRequest,
    ) -> AsyncIterator[bytes]:
        if (
            provider.env_key
            and provider.auth == "bearer"
            and not self._api_key(provider)
        ):
            raise ProviderError(f"Missing API key: {provider.env_key}", 401)

        payload = self._payload(provider, model, request)
        payload["stream"] = True

        try:
            async with self.client.stream(
                "POST",
                f"{self._base_url(provider)}/chat/completions",
                headers=self._headers(provider),
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise ProviderError(
                        body.decode(errors="replace")[:1000],
                        response.status_code,
                    )
                async for chunk in response.aiter_raw():
                    yield chunk
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), None) from exc
