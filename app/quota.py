from __future__ import annotations

import datetime as dt
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from .models import ProviderSpec
from .state import StateStore


@dataclass
class RuntimeQuota:
    minute_requests: deque[float] = field(default_factory=deque)
    day_requests: deque[float] = field(default_factory=deque)
    month_requests: deque[float] = field(default_factory=deque)
    day_tokens: int = 0
    month_tokens: int = 0
    blocked_until: float = 0.0
    failures: int = 0
    successes: int = 0
    latency_ema_ms: float | None = None
    provider_quota: dict[str, Any] = field(default_factory=dict)


class QuotaManager:
    def __init__(self, store: StateStore) -> None:
        self.store = store
        self._state: dict[str, RuntimeQuota] = defaultdict(RuntimeQuota)
        self._loaded: set[str] = set()

    def _month_start(self) -> float:
        now = dt.datetime.now(dt.timezone.utc)
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()

    def _utc_day_key(self) -> str:
        return dt.datetime.now(dt.timezone.utc).date().isoformat()

    def _day_neurons(self, state: RuntimeQuota) -> float:
        day = self._utc_day_key()
        if state.provider_quota.get("local_neurons_date") != day:
            state.provider_quota["local_neurons_date"] = day
            state.provider_quota["local_neurons_used"] = 0.0
        return float(state.provider_quota.get("local_neurons_used") or 0.0)

    def record_neurons(self, provider_id: str, neurons: float) -> None:
        if neurons <= 0:
            return
        state = self._ensure_loaded(provider_id)
        used = self._day_neurons(state) + float(neurons)
        state.provider_quota["local_neurons_used"] = round(used, 4)
        self.store.upsert_runtime(
            provider_id,
            provider_quota_json=state.provider_quota,
        )

    def _ensure_loaded(self, provider_id: str) -> RuntimeQuota:
        state = self._state[provider_id]
        if provider_id in self._loaded:
            return state
        now = time.time()
        rows = self.store.usage_since(provider_id, min(now - 86400, self._month_start()))
        for row in rows:
            ts = float(row["ts"])
            if ts >= now - 60:
                state.minute_requests.append(ts)
            if ts >= now - 86400:
                state.day_requests.append(ts)
                state.day_tokens += int(row.get("total_tokens") or 0)
            if ts >= self._month_start():
                state.month_requests.append(ts)
                state.month_tokens += int(row.get("total_tokens") or 0)
        runtime = self.store.get_runtime(provider_id)
        if runtime:
            state.blocked_until = float(runtime.get("blocked_until") or 0)
            state.successes = int(runtime.get("successes") or 0)
            state.failures = int(runtime.get("failures") or 0)
            state.latency_ema_ms = runtime.get("latency_ema_ms")
            raw = runtime.get("provider_quota_json")
            if raw:
                try:
                    state.provider_quota = json.loads(raw)
                except Exception:
                    state.provider_quota = {}
        self._loaded.add(provider_id)
        return state

    def _prune(self, state: RuntimeQuota) -> None:
        now = time.time()
        while state.minute_requests and now - state.minute_requests[0] >= 60:
            state.minute_requests.popleft()
        while state.day_requests and now - state.day_requests[0] >= 86400:
            state.day_requests.popleft()
        month_start = self._month_start()
        while state.month_requests and state.month_requests[0] < month_start:
            state.month_requests.popleft()

    def available(
        self,
        provider: ProviderSpec,
        estimated_tokens: int = 0,
        estimated_neurons: float = 0.0,
    ) -> bool:
        state = self._ensure_loaded(provider.id)
        self._prune(state)
        if time.time() < state.blocked_until:
            return False
        q = provider.quota
        if q.rpm is not None and len(state.minute_requests) >= q.rpm:
            return False
        if q.rpd is not None and len(state.day_requests) >= q.rpd:
            return False
        if q.tpd is not None and state.day_tokens + estimated_tokens > q.tpd:
            return False
        if q.monthly_requests is not None and len(state.month_requests) >= q.monthly_requests:
            return False
        if q.monthly_tokens is not None and state.month_tokens + estimated_tokens > q.monthly_tokens:
            return False
        if (
            q.neurons_per_day is not None
            and self._day_neurons(state) + estimated_neurons > q.neurons_per_day
        ):
            return False
        remaining = state.provider_quota.get("requests_remaining")
        if remaining is not None and remaining <= 0:
            return False
        token_remaining = state.provider_quota.get("tokens_remaining")
        if token_remaining is not None and token_remaining < estimated_tokens:
            return False
        return True

    def headroom(
        self,
        provider: ProviderSpec,
        estimated_tokens: int = 0,
        estimated_neurons: float = 0.0,
    ) -> float:
        state = self._ensure_loaded(provider.id)
        self._prune(state)
        ratios: list[float] = []
        q = provider.quota
        if q.rpm:
            ratios.append(max(0.0, 1 - len(state.minute_requests) / q.rpm))
        if q.rpd:
            ratios.append(max(0.0, 1 - len(state.day_requests) / q.rpd))
        if q.tpd:
            ratios.append(max(0.0, 1 - (state.day_tokens + estimated_tokens) / q.tpd))
        if q.monthly_requests:
            ratios.append(max(0.0, 1 - len(state.month_requests) / q.monthly_requests))
        if q.monthly_tokens:
            ratios.append(max(0.0, 1 - (state.month_tokens + estimated_tokens) / q.monthly_tokens))
        if q.neurons_per_day:
            ratios.append(
                max(
                    0.0,
                    1
                    - (self._day_neurons(state) + estimated_neurons)
                    / q.neurons_per_day,
                )
            )

        limit = state.provider_quota.get("requests_limit")
        remaining = state.provider_quota.get("requests_remaining")
        if isinstance(limit, (int, float)) and limit > 0 and isinstance(remaining, (int, float)):
            ratios.append(max(0.0, min(1.0, remaining / limit)))

        token_limit = state.provider_quota.get("tokens_limit")
        token_remaining = state.provider_quota.get("tokens_remaining")
        if isinstance(token_limit, (int, float)) and token_limit > 0 and isinstance(token_remaining, (int, float)):
            ratios.append(max(0.0, min(1.0, token_remaining / token_limit)))

        return min(ratios) if ratios else 0.65

    def model_available(self, provider_id: str, model_id: str) -> bool:
        runtime = self.store.get_model_runtime(provider_id, model_id)
        if not runtime:
            return True
        return time.time() >= float(runtime.get("blocked_until") or 0)

    def model_health(self, provider_id: str, model_id: str) -> float:
        runtime = self.store.get_model_runtime(provider_id, model_id)
        if not runtime:
            return 0.95
        if time.time() < float(runtime.get("blocked_until") or 0):
            return 0.0
        successes = int(runtime.get("successes") or 0)
        failures = int(runtime.get("failures") or 0)
        total = successes + failures
        reliability = successes / total if total else 0.95
        latency = runtime.get("latency_ema_ms")
        latency_factor = 1.0
        if latency is not None:
            latency_factor = max(0.4, min(1.0, 2200 / max(220, float(latency))))
        return reliability * latency_factor

    def _record_model_success(
        self,
        provider_id: str,
        model_id: str,
        latency_ms: float | None,
    ) -> None:
        runtime = self.store.get_model_runtime(provider_id, model_id) or {}
        successes = int(runtime.get("successes") or 0) + 1
        failures = max(0, int(runtime.get("failures") or 0) - 1)
        previous_latency = runtime.get("latency_ema_ms")
        latency = previous_latency
        if latency_ms is not None:
            latency = (
                latency_ms
                if previous_latency is None
                else 0.8 * float(previous_latency) + 0.2 * latency_ms
            )
        self.store.upsert_model_runtime(
            provider_id,
            model_id,
            successes=successes,
            failures=failures,
            latency_ema_ms=latency,
            blocked_until=0,
        )

    def _record_model_failure(
        self,
        provider_id: str,
        model_id: str,
        status_code: int | None,
        latency_ms: float | None,
    ) -> None:
        runtime = self.store.get_model_runtime(provider_id, model_id) or {}
        failures = int(runtime.get("failures") or 0) + 1
        successes = int(runtime.get("successes") or 0)
        blocked_until = float(runtime.get("blocked_until") or 0)
        now = time.time()

        if status_code in {404, 410}:
            blocked_until = max(blocked_until, now + 3600)
        elif status_code == 429:
            blocked_until = max(blocked_until, now + 60)
        elif status_code in {401, 403}:
            blocked_until = max(blocked_until, now + 900)
        elif status_code is None or (status_code and status_code >= 500):
            blocked_until = max(
                blocked_until,
                now + min(300, 15 * (2 ** min(failures, 4))),
            )

        previous_latency = runtime.get("latency_ema_ms")
        latency = previous_latency
        if latency_ms is not None:
            latency = (
                latency_ms
                if previous_latency is None
                else 0.8 * float(previous_latency) + 0.2 * latency_ms
            )
        self.store.upsert_model_runtime(
            provider_id,
            model_id,
            successes=successes,
            failures=failures,
            latency_ema_ms=latency,
            blocked_until=blocked_until,
        )

    def health(self, provider_id: str) -> float:
        state = self._ensure_loaded(provider_id)
        total = state.successes + state.failures
        reliability = state.successes / total if total else 0.92
        if time.time() < state.blocked_until:
            return 0.0
        latency_factor = 1.0
        if state.latency_ema_ms is not None:
            latency_factor = max(0.35, min(1.0, 2500 / max(250, state.latency_ema_ms)))
        return reliability * latency_factor

    def reconcile_headers(self, provider_id: str, headers: Any) -> None:
        state = self._ensure_loaded(provider_id)
        lower = {str(k).lower(): str(v) for k, v in headers.items()}
        mappings = {
            "requests_remaining": ["x-ratelimit-remaining-requests", "ratelimit-remaining"],
            "requests_limit": ["x-ratelimit-limit-requests", "ratelimit-limit"],
            "tokens_remaining": ["x-ratelimit-remaining-tokens"],
            "tokens_limit": ["x-ratelimit-limit-tokens"],
            "requests_reset": ["x-ratelimit-reset-requests", "ratelimit-reset"],
            "tokens_reset": ["x-ratelimit-reset-tokens"],
        }
        changed = False
        for dest, names in mappings.items():
            for name in names:
                if name in lower:
                    value: Any = lower[name]
                    try:
                        value = int(float(value))
                    except ValueError:
                        pass
                    state.provider_quota[dest] = value
                    changed = True
                    break
        if changed:
            self.store.upsert_runtime(provider_id, provider_quota_json=state.provider_quota)

    def merge_provider_telemetry(self, provider_id: str, values: dict[str, Any]) -> None:
        state = self._ensure_loaded(provider_id)
        state.provider_quota.update(values)
        self.store.upsert_runtime(
            provider_id,
            provider_quota_json=state.provider_quota,
        )

    def record_success(
        self,
        provider_id: str,
        *,
        model_id: str = "unknown",
        request_id: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        latency_ms: float | None = None,
        fallback_count: int = 0,
        status_code: int = 200,
    ) -> None:
        state = self._ensure_loaded(provider_id)
        now = time.time()
        state.minute_requests.append(now)
        state.day_requests.append(now)
        state.month_requests.append(now)
        state.day_tokens += max(0, total_tokens)
        state.month_tokens += max(0, total_tokens)
        state.successes += 1
        state.failures = max(0, state.failures - 1)
        if latency_ms is not None:
            state.latency_ema_ms = latency_ms if state.latency_ema_ms is None else 0.8 * state.latency_ema_ms + 0.2 * latency_ms

        self._record_model_success(provider_id, model_id, latency_ms)

        self.store.record_usage(
            ts=now,
            request_id=request_id,
            provider_id=provider_id,
            model_id=model_id,
            success=1,
            status_code=status_code,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            fallback_count=fallback_count,
            error=None,
        )
        self.store.upsert_runtime(
            provider_id,
            successes=state.successes,
            failures=state.failures,
            latency_ema_ms=state.latency_ema_ms,
            blocked_until=state.blocked_until,
        )

    def record_failure(
        self,
        provider_id: str,
        *,
        model_id: str = "unknown",
        request_id: str | None = None,
        status_code: int | None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        latency_ms: float | None = None,
        fallback_count: int = 0,
        error: str | None = None,
    ) -> None:
        state = self._ensure_loaded(provider_id)
        state.failures += 1
        now = time.time()
        state.minute_requests.append(now)
        state.day_requests.append(now)
        state.month_requests.append(now)
        state.day_tokens += max(0, total_tokens)
        state.month_tokens += max(0, total_tokens)
        if status_code == 429:
            state.blocked_until = max(state.blocked_until, now + 60)
        elif status_code in {401, 403}:
            state.blocked_until = max(state.blocked_until, now + 900)
        elif status_code is None or status_code >= 500:
            state.blocked_until = max(state.blocked_until, now + min(300, 15 * (2 ** min(state.failures, 4))))

        self._record_model_failure(provider_id, model_id, status_code, latency_ms)

        self.store.record_usage(
            ts=now,
            request_id=request_id,
            provider_id=provider_id,
            model_id=model_id,
            success=0,
            status_code=status_code,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            fallback_count=fallback_count,
            error=(error or "")[:1000],
        )
        self.store.upsert_runtime(
            provider_id,
            failures=state.failures,
            successes=state.successes,
            latency_ema_ms=state.latency_ema_ms,
            blocked_until=state.blocked_until,
        )

    def snapshot(self, provider: ProviderSpec) -> dict[str, Any]:
        state = self._ensure_loaded(provider.id)
        self._prune(state)
        return {
            "provider": provider.id,
            "available": self.available(provider),
            "headroom": round(self.headroom(provider), 4),
            "minute_requests": len(state.minute_requests),
            "day_requests": len(state.day_requests),
            "day_tokens": state.day_tokens,
            "day_neurons": round(self._day_neurons(state), 4),
            "monthly_requests": len(state.month_requests),
            "monthly_tokens": state.month_tokens,
            "blocked_until": state.blocked_until,
            "successes": state.successes,
            "failures": state.failures,
            "latency_ema_ms": state.latency_ema_ms,
            "provider_quota": state.provider_quota,
        }
