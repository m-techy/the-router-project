from __future__ import annotations

import base64
import struct
import time
import uuid
from dataclasses import dataclass
from typing import Any

from .models import Candidate, EmbeddingRequest, ProviderSpec
from .providers.base import ProviderError
from .registry import model_is_current
from .router import FreeRouter

EMBEDDING_MODELS = {"embed/auto", "embed/text", "embed/multimodal"}
TRANSCRIPTION_MODELS = {
    "transcribe/auto",
    "transcribe/fast",
    "transcribe/accurate",
}


def _estimate_input_tokens(value: Any) -> int:
    if isinstance(value, str):
        return max(1, len(value) // 4)
    if isinstance(value, list):
        return max(1, sum(_estimate_input_tokens(item) for item in value))
    if isinstance(value, dict):
        if value.get("type") in {"image_url", "input_audio", "audio"}:
            return 256
        return max(1, sum(_estimate_input_tokens(item) for item in value.values()))
    return max(1, len(str(value)) // 4)


def embedding_requirements(value: Any) -> set[str]:
    requirements = {"embeddings"}

    def inspect(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                inspect(child)
            return
        if not isinstance(item, dict):
            return

        kind = item.get("type")
        if kind == "image_url":
            requirements.add("vision")
        elif kind in {"input_audio", "audio"}:
            requirements.add("audio")

        for child in item.values():
            if isinstance(child, (list, dict)):
                inspect(child)

    inspect(value)
    return requirements


def _float_embedding_to_base64(values: list[Any]) -> str:
    floats = [float(value) for value in values]
    raw = struct.pack(f"<{len(floats)}f", *floats)
    return base64.b64encode(raw).decode("ascii")


def normalize_embedding_encoding(
    body: dict[str, Any],
    encoding_format: str,
) -> dict[str, Any]:
    if encoding_format != "base64":
        return body

    for item in body.get("data") or []:
        embedding = item.get("embedding")
        if isinstance(embedding, list):
            item["embedding"] = _float_embedding_to_base64(embedding)
    return body


@dataclass
class RoutedEmbedding:
    body: dict[str, Any]
    provider: str
    model: str
    fallback_count: int
    route_reason: str


@dataclass
class RoutedTranscription:
    content: bytes
    content_type: str
    provider: str
    model: str
    fallback_count: int
    route_reason: str


class ModalityRouter:
    def __init__(self, chat_router: FreeRouter):
        self.chat_router = chat_router
        self.registry = chat_router.registry
        self.quota = chat_router.quota

    def _direct_adapter(self, provider: ProviderSpec):
        return self.chat_router.adapters.get(
            provider.adapter,
            self.chat_router.adapters["openai_compatible"],
        )

    def _candidate_score(
        self,
        provider: ProviderSpec,
        model_id: str,
        quality: float,
        estimated_tokens: int,
        *,
        speed_weight: float,
    ) -> tuple[float, str]:
        quota_score = self.quota.headroom(provider, estimated_tokens)
        provider_health = self.quota.health(provider.id)
        model_health = self.quota.model_health(provider.id, model_id)
        health_score = min(provider_health, model_health)
        runtime = self.quota.snapshot(provider)
        latency = runtime.get("latency_ema_ms")
        speed_score = (
            0.85
            if latency is None
            else max(0.35, min(1.0, 1500 / max(150, float(latency))))
        )
        confidence = {"high": 1.0, "medium": 0.93, "low": 0.80}[provider.confidence]
        certification = self.chat_router._certification_factor(provider.id)
        quality_weight = 0.38 if speed_weight < 0.3 else 0.24
        quota_weight = 0.27
        health_weight = max(0.10, 1 - quality_weight - quota_weight - speed_weight)
        score = (
            provider.priority
            * confidence
            * certification
            * (
                quality_weight * quality
                + quota_weight * quota_score
                + health_weight * health_score
                + speed_weight * speed_score
            )
        )
        reason = (
            f"quality={quality:.2f},quota={quota_score:.2f},"
            f"health={health_score:.2f},speed={speed_score:.2f}"
        )
        return score, reason

    def embedding_candidates(
        self,
        request: EmbeddingRequest,
        *,
        allow_trial: bool,
        allow_promo: bool,
    ) -> list[Candidate]:
        requirements = embedding_requirements(request.input)
        estimated = _estimate_input_tokens(request.input)
        candidates: list[Candidate] = []

        for provider in self.registry.allowed_providers(
            allow_trial=allow_trial,
            allow_promo=allow_promo,
        ):
            if not self.chat_router._provider_has_key(provider):
                continue
            if "${CLOUDFLARE_ACCOUNT_ID}" in provider.base_url and not (
                self.chat_router.adapters["openai_compatible"]._value(
                    "CLOUDFLARE_ACCOUNT_ID"
                )
            ):
                continue
            if not self.quota.available(provider, estimated):
                continue
            if self.chat_router._certification_factor(provider.id) <= 0:
                continue

            for model in provider.models:
                if not model.enabled or not model.free or not model_is_current(model):
                    continue
                if not self.quota.model_available(provider.id, model.id):
                    continue
                if not model.capabilities.embeddings:
                    continue
                if "vision" in requirements and not model.capabilities.vision:
                    continue
                if "audio" in requirements and not model.capabilities.audio:
                    continue
                if (
                    request.model not in EMBEDDING_MODELS
                    and request.model not in {model.id, f"{provider.id}/{model.id}"}
                ):
                    continue
                if request.model == "embed/multimodal" and not (
                    model.capabilities.vision or model.capabilities.audio
                ):
                    continue

                score, reason = self._candidate_score(
                    provider,
                    model.id,
                    model.quality,
                    estimated,
                    speed_weight=0.12,
                )
                candidates.append(
                    Candidate(
                        provider_id=provider.id,
                        model_id=model.id,
                        score=score,
                        reason=reason,
                    )
                )

        return sorted(candidates, key=lambda item: item.score, reverse=True)

    async def embeddings(
        self,
        request: EmbeddingRequest,
        *,
        allow_trial: bool,
        allow_promo: bool,
    ) -> RoutedEmbedding:
        estimated = _estimate_input_tokens(request.input)
        candidates = self.embedding_candidates(
            request,
            allow_trial=allow_trial,
            allow_promo=allow_promo,
        )
        if not candidates:
            raise RuntimeError(
                "No eligible configured free embedding provider/model is currently available"
            )

        request_id = f"embed-{uuid.uuid4().hex[:20]}"
        errors: list[str] = []

        for index, candidate in enumerate(candidates[:8]):
            provider = self.registry.get(candidate.provider_id)
            adapter = self._direct_adapter(provider)
            method = getattr(adapter, "embeddings", None)
            if method is None:
                continue

            started = time.perf_counter()
            try:
                body, headers = await method(
                    provider,
                    candidate.model_id,
                    request,
                )
                latency = (time.perf_counter() - started) * 1000
                self.quota.reconcile_headers(provider.id, headers)
                usage = body.get("usage") or {}
                total = int(
                    usage.get("total_tokens")
                    or usage.get("prompt_tokens")
                    or estimated
                )
                self.quota.record_success(
                    provider.id,
                    model_id=candidate.model_id,
                    request_id=request_id,
                    prompt_tokens=int(usage.get("prompt_tokens") or total),
                    total_tokens=total,
                    latency_ms=latency,
                    fallback_count=index,
                )
                body = normalize_embedding_encoding(body, request.encoding_format)
                body.setdefault("model", candidate.model_id)
                body["router"] = {
                    "provider": provider.id,
                    "model": candidate.model_id,
                    "fallback_count": index,
                    "route_reason": candidate.reason,
                    "request_id": request_id,
                }
                return RoutedEmbedding(
                    body=body,
                    provider=provider.id,
                    model=candidate.model_id,
                    fallback_count=index,
                    route_reason=candidate.reason,
                )
            except ProviderError as exc:
                latency = (time.perf_counter() - started) * 1000
                self.quota.record_failure(
                    provider.id,
                    model_id=candidate.model_id,
                    request_id=request_id,
                    status_code=exc.status_code,
                    latency_ms=latency,
                    fallback_count=index,
                    error=str(exc),
                )
                errors.append(
                    f"{provider.id}/{candidate.model_id}: {exc.status_code or 'network'}"
                )

        raise RuntimeError(
            "All eligible embedding providers failed: " + "; ".join(errors[-8:])
        )

    def transcription_candidates(
        self,
        requested_model: str,
        *,
        allow_trial: bool,
        allow_promo: bool,
    ) -> list[Candidate]:
        candidates: list[Candidate] = []

        for provider in self.registry.allowed_providers(
            allow_trial=allow_trial,
            allow_promo=allow_promo,
        ):
            if not self.chat_router._provider_has_key(provider):
                continue
            if not self.quota.available(provider):
                continue
            if self.chat_router._certification_factor(provider.id) <= 0:
                continue

            for model in provider.models:
                if not model.enabled or not model.free or not model_is_current(model):
                    continue
                if not model.capabilities.transcription:
                    continue
                if not self.quota.model_available(provider.id, model.id):
                    continue
                if (
                    requested_model not in TRANSCRIPTION_MODELS
                    and requested_model not in {model.id, f"{provider.id}/{model.id}"}
                ):
                    continue

                quality = model.quality
                speed_weight = 0.42 if requested_model == "transcribe/fast" else 0.16
                if requested_model == "transcribe/accurate":
                    quality = min(1.0, quality * 1.08)
                score, reason = self._candidate_score(
                    provider,
                    model.id,
                    quality,
                    0,
                    speed_weight=speed_weight,
                )
                candidates.append(
                    Candidate(
                        provider_id=provider.id,
                        model_id=model.id,
                        score=score,
                        reason=reason,
                    )
                )

        return sorted(candidates, key=lambda item: item.score, reverse=True)

    async def transcription(
        self,
        *,
        requested_model: str,
        filename: str,
        data: bytes,
        content_type: str,
        language: str | None,
        prompt: str | None,
        response_format: str,
        temperature: float | None,
        allow_trial: bool,
        allow_promo: bool,
    ) -> RoutedTranscription:
        candidates = self.transcription_candidates(
            requested_model,
            allow_trial=allow_trial,
            allow_promo=allow_promo,
        )
        if not candidates:
            raise RuntimeError(
                "No eligible configured free transcription provider/model is currently available"
            )

        request_id = f"transcribe-{uuid.uuid4().hex[:20]}"
        errors: list[str] = []

        for index, candidate in enumerate(candidates[:8]):
            provider = self.registry.get(candidate.provider_id)
            adapter = self._direct_adapter(provider)
            method = getattr(adapter, "transcription", None)
            if method is None:
                continue

            started = time.perf_counter()
            try:
                body, headers, response_content_type = await method(
                    provider,
                    candidate.model_id,
                    filename=filename,
                    data=data,
                    content_type=content_type,
                    language=language,
                    prompt=prompt,
                    response_format=response_format,
                    temperature=temperature,
                )
                latency = (time.perf_counter() - started) * 1000
                self.quota.reconcile_headers(provider.id, headers)
                self.quota.record_success(
                    provider.id,
                    model_id=candidate.model_id,
                    request_id=request_id,
                    latency_ms=latency,
                    fallback_count=index,
                )
                return RoutedTranscription(
                    content=body,
                    content_type=response_content_type,
                    provider=provider.id,
                    model=candidate.model_id,
                    fallback_count=index,
                    route_reason=candidate.reason,
                )
            except ProviderError as exc:
                latency = (time.perf_counter() - started) * 1000
                self.quota.record_failure(
                    provider.id,
                    model_id=candidate.model_id,
                    request_id=request_id,
                    status_code=exc.status_code,
                    latency_ms=latency,
                    fallback_count=index,
                    error=str(exc),
                )
                errors.append(
                    f"{provider.id}/{candidate.model_id}: {exc.status_code or 'network'}"
                )

        raise RuntimeError(
            "All eligible transcription providers failed: " + "; ".join(errors[-8:])
        )
