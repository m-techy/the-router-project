from __future__ import annotations

import time
from typing import Any

from .models import CertificationState, ChatCompletionRequest, ChatMessage, ProviderSpec
from .providers.base import ProviderError
from .router import FreeRouter


async def certify_provider(router: FreeRouter, provider: ProviderSpec) -> dict[str, Any]:
    if not router._provider_has_key(provider):
        router.quota.store.upsert_runtime(
            provider.id,
            certification_state=CertificationState.CONFIGURED.value,
            certification_note=f"Missing {provider.env_key}",
            last_probe_at=time.time(),
            last_probe_ok=0,
        )
        return {"provider": provider.id, "state": "configured", "ok": False, "note": f"Missing {provider.env_key}"}

    model = next((m for m in provider.models if m.enabled and m.free), None)
    if model is None:
        return {"provider": provider.id, "state": "quarantine", "ok": False, "note": "No enabled free model"}

    request = ChatCompletionRequest(
        model=f"{provider.id}/{model.id}",
        messages=[ChatMessage(role="user", content="Reply with exactly: ok")],
        max_tokens=4,
        temperature=0,
    )
    started = time.perf_counter()
    try:
        body, headers = await router._adapter(provider).chat(provider, model.id, request)
        latency = (time.perf_counter() - started) * 1000
        router.quota.reconcile_headers(provider.id, headers)
        state = CertificationState.ACTIVE
        note = f"Probe succeeded in {latency:.0f} ms"
        ok = True
        result = {"sample": str(body.get("choices", [{}])[0])[:300]}
    except ProviderError as exc:
        latency = (time.perf_counter() - started) * 1000
        state = CertificationState.RETRY_LATER if exc.status_code == 429 or exc.status_code is None or (exc.status_code and exc.status_code >= 500) else CertificationState.QUARANTINE
        note = f"Probe failed ({exc.status_code or 'network'}): {str(exc)[:300]}"
        ok = False
        result = {}

    router.quota.store.upsert_runtime(
        provider.id,
        certification_state=state.value,
        certification_note=note,
        last_probe_at=time.time(),
        last_probe_ok=1 if ok else 0,
        latency_ema_ms=latency,
    )
    return {"provider": provider.id, "model": model.id, "state": state.value, "ok": ok, "note": note, **result}
