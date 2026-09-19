from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Callable

import httpx

from app.models import ChatCompletionRequest, EmbeddingRequest, ImageGenerationRequest, ProviderSpec
from app.normalization import normalize_request_body
from app.providers.base import AdapterCapabilities, ProviderAdapter, ProviderError


class OpenAICompatibleAdapter(ProviderAdapter):
    capabilities = AdapterCapabilities(embeddings=True, transcription=True, image_generation=True)

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


    async def embeddings(
        self,
        provider: ProviderSpec,
        model: str,
        request: EmbeddingRequest,
    ) -> tuple[dict[str, Any], httpx.Headers]:
        if (
            provider.env_key
            and provider.auth == "bearer"
            and not self._api_key(provider)
        ):
            raise ProviderError(f"Missing API key: {provider.env_key}", 401)

        payload = request.model_dump(exclude_none=True)
        payload["model"] = self._model_id(provider, model)
        try:
            response = await self.client.post(
                f"{self._base_url(provider)}/embeddings",
                headers=self._headers(provider),
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), None) from exc

        if response.status_code >= 400:
            raise ProviderError(response.text[:1000], response.status_code)
        try:
            return response.json(), response.headers
        except ValueError as exc:
            raise ProviderError(
                "Provider returned a non-JSON embedding response",
                response.status_code,
            ) from exc

    async def image_generation(
        self,
        provider: ProviderSpec,
        model: str,
        request: ImageGenerationRequest,
    ) -> tuple[dict[str, Any], httpx.Headers]:
        if provider.id != "cloudflare-ai":
            raise ProviderError(
                f"Image generation is not implemented for adapter provider {provider.id}",
                501,
            )
        if request.n != 1:
            raise ProviderError("Cloudflare FLUX currently supports n=1 through The Router.", 422)
        if len(request.prompt) > 2048:
            raise ProviderError(
                "Cloudflare FLUX prompt must be 2048 characters or fewer.",
                422,
            )
        if request.size not in {None, "auto"}:
            raise ProviderError(
                "Cloudflare FLUX does not expose an image-size parameter through this route.",
                422,
            )
        if request.background == "transparent":
            raise ProviderError(
                "Cloudflare FLUX does not expose transparent background control.",
                422,
            )
        if request.output_format not in {None, "jpeg"}:
            raise ProviderError(
                "Cloudflare FLUX returns JPEG; png/webp output is not supported by this route.",
                422,
            )
        if request.response_format == "url":
            raise ProviderError(
                "Cloudflare FLUX returns image bytes/base64, not a hosted result URL.",
                422,
            )
        if (
            provider.env_key
            and provider.auth == "bearer"
            and not self._api_key(provider)
        ):
            raise ProviderError(f"Missing API key: {provider.env_key}", 401)

        base = self._base_url(provider)
        if not base.endswith("/ai/v1"):
            raise ProviderError("Cloudflare Workers AI base URL is not recognized.", 500)
        endpoint = base[: -len("/ai/v1")] + "/ai/run/" + self._model_id(provider, model)

        steps = 4
        quality = (request.quality or "auto").lower()
        if quality in {"high", "hd", "xhigh", "max"}:
            steps = 8
        elif quality in {"low"}:
            steps = 2

        payload: dict[str, Any] = {
            "prompt": request.prompt,
            "steps": steps,
        }
        if request.seed is not None:
            payload["seed"] = request.seed

        try:
            response = await self.client.post(
                endpoint,
                headers=self._headers(provider),
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), None) from exc

        if response.status_code >= 400:
            raise ProviderError(response.text[:1000], response.status_code)

        try:
            envelope = response.json()
        except ValueError as exc:
            raise ProviderError(
                "Cloudflare image provider returned a non-JSON response",
                response.status_code,
            ) from exc

        result = envelope.get("result") if isinstance(envelope, dict) else None
        image = result.get("image") if isinstance(result, dict) else None
        if not image:
            raise ProviderError("Cloudflare image response did not contain image data.", 502)

        return {
            "created": int(time.time()),
            "data": [{"b64_json": image}],
            "output_format": request.output_format or "jpeg",
            "quality": request.quality or "auto",
        }, response.headers

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
        if (
            provider.env_key
            and provider.auth == "bearer"
            and not self._api_key(provider)
        ):
            raise ProviderError(f"Missing API key: {provider.env_key}", 401)

        headers = self._headers(provider)
        headers.pop("Content-Type", None)
        form: dict[str, str] = {
            "model": self._model_id(provider, model),
            "response_format": response_format,
        }
        if language:
            form["language"] = language
        if prompt:
            form["prompt"] = prompt
        if temperature is not None:
            form["temperature"] = str(temperature)

        try:
            response = await self.client.post(
                f"{self._base_url(provider)}/audio/transcriptions",
                headers=headers,
                data=form,
                files={"file": (filename, data, content_type)},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), None) from exc

        if response.status_code >= 400:
            raise ProviderError(response.text[:1000], response.status_code)
        return response.content, response.headers, response.headers.get(
            "content-type", "application/json"
        )
