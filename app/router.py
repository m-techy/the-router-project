from __future__ import annotations

import os
import re
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from .models import Candidate, CertificationState, ChatCompletionRequest, ProviderSpec, TierType
from .providers import BifrostAdapter, GeminiHybridAdapter, OpenAICompatibleAdapter
from .providers.base import ProviderAdapter, ProviderError
from .providers.sdk import validate_adapter
from .quota import QuotaManager
from .registry import ProviderRegistry, model_is_current
from .route_profiles import ROUTE_PROFILE_PREFIX, RouteProfile, load_route_profiles

VIRTUAL_MODELS = {
    "free/auto",
    "free/fast",
    "free/smart",
    "free/code",
    "free/vision",
    "free/reasoning",
    "free/long",
    "promo/auto",
    "trial/auto",
}


def estimate_tokens(request: ChatCompletionRequest) -> int:
    text = ""
    for message in request.messages:
        text += message.content if isinstance(message.content, str) else str(message.content)
    return max(1, len(text) // 4)


def request_requirements(request: ChatCompletionRequest) -> set[str]:
    requirements = {"chat"}
    if request.tools:
        requirements.add("tools")
    if request.response_format:
        requirements.add("json_mode")

    payload = str([m.content for m in request.messages])
    if re.search(r"data:image|image_url|\bimage\b|\bphoto\b|\bvision\b", payload, re.I):
        requirements.add("vision")
    if re.search(r"\b(code|python|typescript|javascript|bug|refactor|sql|regex|programming)\b", payload, re.I):
        requirements.add("coding")
    if re.search(r"\b(reason|prove|derive|analy[sz]e|logic|math|theorem|step[- ]by[- ]step)\b", payload, re.I):
        requirements.add("reasoning")

    if request.model == "free/vision":
        requirements.add("vision")
    if request.model == "free/code":
        requirements.add("coding")
    if request.model == "free/reasoning":
        requirements.add("reasoning")
    return requirements


def usage_from_body(body: dict[str, Any]) -> tuple[int, int, int]:
    usage = body.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion))
    return prompt, completion, total


@dataclass
class RoutedResponse:
    body: dict[str, Any]
    provider: str
    model: str
    fallback_count: int
    route_reason: str


class FreeRouter:
    def __init__(self, registry: ProviderRegistry, quota: QuotaManager, timeout: float = 120):
        self.registry = registry
        self.quota = quota
        self.client = httpx.AsyncClient(timeout=timeout)
        self.adapters = {
            "openai_compatible": OpenAICompatibleAdapter(self.client, self.quota.store.get_secret),
            "gemini_hybrid": GeminiHybridAdapter(self.client, self.quota.store.get_secret),
            "bifrost": BifrostAdapter(self.client),
        }
        self.transport_mode = os.getenv("ROUTER_TRANSPORT", "direct").lower()

    def route_profile(self, model: str) -> RouteProfile | None:
        if not model.startswith(ROUTE_PROFILE_PREFIX):
            return None
        slug = model[len(ROUTE_PROFILE_PREFIX) :]
        profile = load_route_profiles(self.quota.store).get(slug)
        return profile if profile and profile.enabled else None

    def route_permissions(self, model: str) -> tuple[bool, bool]:
        profile = self.route_profile(model)
        if not profile:
            return False, False
        return profile.allow_trial, profile.allow_promo

    def max_attempts(self, model: str) -> int:
        profile = self.route_profile(model)
        return profile.max_fallbacks if profile else 8

    def resolved_requirements(self, request: ChatCompletionRequest) -> set[str]:
        profile = self.route_profile(request.model)
        effective = (
            request.model_copy(update={"model": profile.base_route})
            if profile
            else request
        )
        return request_requirements(effective)

    async def close(self) -> None:
        await self.client.aclose()

    def register_adapter(
        self,
        name: str,
        adapter: ProviderAdapter,
        *,
        replace: bool = False,
    ) -> None:
        validate_adapter(name, adapter)
        if name in self.adapters and not replace:
            raise ValueError(f"Adapter '{name}' is already registered")
        self.adapters[name] = adapter

    def adapter_inventory(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "sdk_version": getattr(adapter, "sdk_version", None),
                "capabilities": {
                    "chat": adapter.supports("chat"),
                    "stream": adapter.supports("stream"),
                    "embeddings": adapter.supports("embeddings"),
                    "transcription": adapter.supports("transcription"),
                },
            }
            for name, adapter in sorted(self.adapters.items())
        }

    def _adapter(self, provider: ProviderSpec):
        if self.transport_mode == "bifrost":
            return self.adapters["bifrost"]
        return self.adapters.get(provider.adapter, self.adapters["openai_compatible"])

    def _provider_has_key(self, provider: ProviderSpec) -> bool:
        if provider.auth in {"none", "optional_bearer"} or provider.env_key is None:
            return True
        return bool(os.getenv(provider.env_key) or self.quota.store.get_secret(provider.env_key))

    def _certification_factor(self, provider_id: str) -> float:
        runtime = self.quota.store.get_runtime(provider_id) or {}
        state = runtime.get("certification_state") or CertificationState.UNKNOWN.value
        if state == CertificationState.QUARANTINE.value:
            return 0.0
        if state == CertificationState.RETRY_LATER.value:
            return 0.55
        if state == CertificationState.ACTIVE.value:
            return 1.05
        return 1.0

    def candidates(
        self,
        request: ChatCompletionRequest,
        *,
        allow_trial: bool,
        allow_promo: bool,
    ) -> list[Candidate]:
        estimated = estimate_tokens(request)
        profile = self.route_profile(request.model)
        effective_request = (
            request.model_copy(update={"model": profile.base_route})
            if profile
            else request
        )
        requirements = request_requirements(effective_request)
        requested = effective_request.model
        candidates: list[Candidate] = []

        for provider in self.registry.allowed_providers(
            allow_trial=allow_trial,
            allow_promo=allow_promo,
        ):
            if profile:
                if profile.providers_allow and provider.id not in profile.providers_allow:
                    continue
                if provider.id in profile.providers_deny:
                    continue
            if not self._provider_has_key(provider):
                continue
            if "${CLOUDFLARE_ACCOUNT_ID}" in provider.base_url and not (os.getenv("CLOUDFLARE_ACCOUNT_ID") or self.quota.store.get_secret("CLOUDFLARE_ACCOUNT_ID")):
                continue
            if not self.quota.available(provider, estimated):
                continue

            certification = self._certification_factor(provider.id)
            if certification <= 0:
                continue

            for model in provider.models:
                if not model.enabled or not model.free:
                    continue
                if not model_is_current(model):
                    continue
                if not self.quota.model_available(provider.id, model.id):
                    continue
                if requested not in VIRTUAL_MODELS and requested not in {model.id, f"{provider.id}/{model.id}"}:
                    continue

                caps = model.capabilities
                if any(not getattr(caps, required, False) for required in requirements):
                    continue
                if requested == "free/long" and (model.context or 0) < 200_000:
                    continue
                if profile and profile.min_context and (model.context or 0) < profile.min_context:
                    continue

                quota_score = self.quota.headroom(provider, estimated)
                provider_health = self.quota.health(provider.id)
                model_health = self.quota.model_health(provider.id, model.id)
                health_score = min(provider_health, model_health)
                quality_score = model.quality
                latency = self.quota.snapshot(provider).get("latency_ema_ms")
                speed_score = 0.85 if latency is None else max(0.35, min(1.0, 1500 / max(150, latency)))

                if requested == "free/fast":
                    weights = (0.20, 0.25, 0.20, 0.35)
                elif requested in {"free/smart", "free/reasoning"}:
                    weights = (0.50, 0.20, 0.20, 0.10)
                elif requested == "free/code":
                    quality_score = min(1.0, quality_score * 1.08)
                    weights = (0.44, 0.23, 0.23, 0.10)
                else:
                    weights = (0.34, 0.31, 0.25, 0.10)

                confidence = {"high": 1.0, "medium": 0.93, "low": 0.80}[provider.confidence]
                tier_bias = 1.0 if provider.tier == TierType.PERSISTENT_FREE else 0.78
                score = provider.priority * confidence * tier_bias * certification * (
                    weights[0] * quality_score
                    + weights[1] * quota_score
                    + weights[2] * health_score
                    + weights[3] * speed_score
                )
                candidates.append(
                    Candidate(
                        provider_id=provider.id,
                        model_id=model.id,
                        score=score,
                        reason=(
                            f"quality={quality_score:.2f},quota={quota_score:.2f},"
                            f"health={health_score:.2f},model_health={model_health:.2f},speed={speed_score:.2f}"
                        ),
                    )
                )

        return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)

    def preview(
        self,
        request: ChatCompletionRequest,
        *,
        allow_trial: bool,
        allow_promo: bool,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return [
            candidate.model_dump()
            for candidate in self.candidates(
                request,
                allow_trial=allow_trial,
                allow_promo=allow_promo,
            )[:limit]
        ]

    async def chat(
        self,
        request: ChatCompletionRequest,
        *,
        allow_trial: bool,
        allow_promo: bool,
    ) -> RoutedResponse:
        candidates = self.candidates(request, allow_trial=allow_trial, allow_promo=allow_promo)
        if not candidates:
            raise RuntimeError("No eligible configured free provider/model is currently available")

        request_id = f"router-{uuid.uuid4().hex[:20]}"
        errors: list[str] = []

        for index, candidate in enumerate(candidates[: self.max_attempts(request.model)]):
            provider = self.registry.get(candidate.provider_id)
            started = time.perf_counter()
            try:
                body, headers = await self._adapter(provider).chat(provider, candidate.model_id, request)
                latency = (time.perf_counter() - started) * 1000
                self.quota.reconcile_headers(provider.id, headers)
                prompt, completion, total = usage_from_body(body)
                self.quota.record_success(
                    provider.id,
                    model_id=candidate.model_id,
                    request_id=request_id,
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    total_tokens=total,
                    latency_ms=latency,
                    fallback_count=index,
                )

                body.setdefault("router", {})
                body["router"].update(
                    {
                        "provider": provider.id,
                        "model": candidate.model_id,
                        "fallback_count": index,
                        "route_reason": candidate.reason,
                        "request_id": request_id,
                    }
                )
                return RoutedResponse(
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
                errors.append(f"{provider.id}/{candidate.model_id}: {exc.status_code or 'network'}")

        raise RuntimeError("All eligible providers failed: " + "; ".join(errors[-8:]))

    async def stream(
        self,
        request: ChatCompletionRequest,
        *,
        allow_trial: bool,
        allow_promo: bool,
    ) -> tuple[AsyncIterator[bytes], str, str, int, str]:
        candidates = self.candidates(request, allow_trial=allow_trial, allow_promo=allow_promo)
        if not candidates:
            raise RuntimeError("No eligible configured free provider/model is currently available")

        request_id = f"router-{uuid.uuid4().hex[:20]}"
        errors: list[str] = []

        for index, candidate in enumerate(candidates[: self.max_attempts(request.model)]):
            provider = self.registry.get(candidate.provider_id)
            started = time.perf_counter()
            try:
                iterator = self._adapter(provider).stream(provider, candidate.model_id, request)
                first = await anext(iterator)
                first_latency = (time.perf_counter() - started) * 1000

                async def wrapped(
                    first_chunk: bytes = first,
                    upstream: AsyncIterator[bytes] = iterator,
                    selected_provider: ProviderSpec = provider,
                    selected_candidate: Candidate = candidate,
                    fallback_count: int = index,
                    latency_ms: float = first_latency,
                ) -> AsyncIterator[bytes]:
                    completed = False
                    try:
                        yield first_chunk
                        async for chunk in upstream:
                            yield chunk
                        completed = True
                    finally:
                        if completed:
                            self.quota.record_success(
                                selected_provider.id,
                                model_id=selected_candidate.model_id,
                                request_id=request_id,
                                total_tokens=0,
                                latency_ms=latency_ms,
                                fallback_count=fallback_count,
                            )

                return wrapped(), provider.id, candidate.model_id, index, candidate.reason
            except (ProviderError, StopAsyncIteration) as exc:
                latency = (time.perf_counter() - started) * 1000
                status = exc.status_code if isinstance(exc, ProviderError) else None
                self.quota.record_failure(
                    provider.id,
                    model_id=candidate.model_id,
                    request_id=request_id,
                    status_code=status,
                    latency_ms=latency,
                    fallback_count=index,
                    error=str(exc),
                )
                errors.append(f"{provider.id}/{candidate.model_id}: {status or 'stream'}")

        raise RuntimeError(
            "All eligible providers failed before streaming began: " + "; ".join(errors[-8:])
        )
