from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .certification import certify_provider
from .models import ChatCompletionRequest
from .quota import QuotaManager
from .quota_telemetry import QuotaTelemetry
from .registry import ProviderRegistry, model_is_current
from .router import FreeRouter, VIRTUAL_MODELS, request_requirements
from .setup import SetupValue, configured_value, known_setup_keys, provider_setup_status
from .state import StateStore

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path(
    os.getenv("ROUTER_PROVIDER_REGISTRY", str(ROOT / "config" / "providers.yaml"))
)
IS_VERCEL = bool(os.getenv("VERCEL"))
DEFAULT_DB_PATH = "/tmp/router.db" if IS_VERCEL else str(ROOT / "data" / "router.db")
DB_PATH = Path(os.getenv("ROUTER_DB_PATH", DEFAULT_DB_PATH))
STATIC_DIR = ROOT / "app" / "static"

registry = ProviderRegistry(REGISTRY_PATH)
store = StateStore(DB_PATH)
quota = QuotaManager(store)
router = FreeRouter(
    registry,
    quota,
    timeout=float(os.getenv("ROUTER_REQUEST_TIMEOUT", "120")),
)
quota_telemetry = QuotaTelemetry(router.client, store.get_secret)


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def configured(provider) -> bool:
    if provider.auth in {"none", "optional_bearer"} or provider.env_key is None:
        return True
    return configured_value(store, provider.env_key)


def route_flags(model: str) -> tuple[bool, bool]:
    allow_trial = env_bool("ROUTER_ALLOW_TRIAL") or model == "trial/auto"
    allow_promo = env_bool("ROUTER_ALLOW_PROMO") or model == "promo/auto"
    return allow_trial, allow_promo


def require_admin(authorization: str | None) -> None:
    admin_key = os.getenv("ROUTER_ADMIN_KEY")
    if admin_key and authorization != f"Bearer {admin_key}":
        raise HTTPException(status_code=401, detail="Admin authorization required")


def public_base_url(request: Request) -> str:
    override = os.getenv("ROUTER_PUBLIC_URL", "").strip().rstrip("/")
    return override or str(request.base_url).rstrip("/")


def setup_status() -> dict[str, Any]:
    enabled = [provider for provider in registry.providers if provider.enabled]
    ready = [provider for provider in enabled if configured(provider)]
    persistent = [p for p in ready if p.tier.value == "persistent_free"]
    no_key = [
        p
        for p in enabled
        if p.auth in {"none", "optional_bearer"} or p.env_key is None
    ]
    missing = [
        {
            "provider": p.id,
            "name": p.name,
            "env_key": p.env_key,
            "tier": p.tier.value,
            "signup_url": p.signup_url,
            "docs_url": p.docs_url,
        }
        for p in enabled
        if not configured(p) and p.env_key
    ]
    return {
        "ready": bool(ready),
        "providers_total": len(enabled),
        "providers_ready": len(ready),
        "persistent_ready": len(persistent),
        "no_key_ready": len([p for p in no_key if configured(p)]),
        "missing": missing,
        "recommended_next": missing[:5],
        "trial_enabled": env_bool("ROUTER_ALLOW_TRIAL"),
        "promo_enabled": env_bool("ROUTER_ALLOW_PROMO"),
        "transport": router.transport_mode,
        "mode": "vercel-site" if IS_VERCEL else "local-platform",
        "writable_setup": not IS_VERCEL,
        "hosted_api_enabled": env_bool("ROUTER_ENABLE_HOSTED_API"),
        "provider_setup": provider_setup_status(registry, store),
    }


def client_snippets(base_url: str) -> dict[str, str]:
    api_base = f"{base_url}/v1"
    return {
        "python": (
            "from openai import OpenAI\n\n"
            f'client = OpenAI(base_url="{api_base}", api_key="local")\n'
            'r = client.chat.completions.create(\n'
            '    model="free/auto",\n'
            '    messages=[{"role": "user", "content": "Hello"}],\n'
            ')\n'
            "print(r.choices[0].message.content)"
        ),
        "javascript": (
            'import OpenAI from "openai";\n\n'
            f'const client = new OpenAI({{ baseURL: "{api_base}", apiKey: "local" }});\n'
            "const r = await client.chat.completions.create({\n"
            '  model: "free/auto",\n'
            '  messages: [{ role: "user", content: "Hello" }],\n'
            "});\n"
            "console.log(r.choices[0].message.content);"
        ),
        "curl": (
            f"curl {api_base}/chat/completions \\\n"
            '  -H "Content-Type: application/json" \\\n'
            '  -d \'{"model":"free/auto","messages":[{"role":"user","content":"Hello"}]}\''
        ),
    }


async def periodic_probe() -> None:
    minutes = int(os.getenv("ROUTER_PROBE_INTERVAL_MINUTES", "0"))
    if minutes <= 0:
        return
    while True:
        await asyncio.sleep(minutes * 60)
        for provider in registry.providers:
            if provider.enabled and configured(provider):
                try:
                    await certify_provider(router, provider)
                except Exception:
                    pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    interval = int(os.getenv("ROUTER_PROBE_INTERVAL_MINUTES", "0"))
    probe_task = asyncio.create_task(periodic_probe()) if interval > 0 else None
    yield
    if probe_task:
        probe_task.cancel()
    await router.close()
    store.close()


app = FastAPI(
    title="The Router",
    description="Free-tier-aware multi-provider AI router",
    version="0.3.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> FileResponse:
    page = "hosted.html" if IS_VERCEL else "index.html"
    return FileResponse(STATIC_DIR / page)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "version": app.version,
        "providers": len(registry.providers),
        "configured_providers": sum(1 for p in registry.providers if configured(p)),
        "registry_updated_at": registry.data.updated_at,
        "db": str(DB_PATH),
        "transport": router.transport_mode,
        "mode": "vercel-site" if IS_VERCEL else "local-platform",
        "hosted_api_enabled": env_bool("ROUTER_ENABLE_HOSTED_API"),
    }


@app.get("/api/setup/status")
async def setup_status_endpoint() -> dict[str, Any]:
    return setup_status()


@app.get("/api/setup/snippets")
async def setup_snippets(request: Request) -> dict[str, Any]:
    return {
        "base_url": f"{public_base_url(request)}/v1",
        "snippets": client_snippets(public_base_url(request)),
        "virtual_models": sorted(VIRTUAL_MODELS),
    }


@app.post("/api/setup/value")
async def setup_value(
    item: SetupValue,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    if IS_VERCEL:
        raise HTTPException(
            status_code=409,
            detail="Browser setup is disabled on Vercel. Configure provider keys as Vercel environment variables.",
        )
    allowed = known_setup_keys(registry)
    if item.key not in allowed:
        raise HTTPException(status_code=400, detail="Unknown setup key")
    store.set_secret(item.key, item.value.strip())
    return {
        "ok": True,
        "key": item.key,
        "configured": True,
        "source": "local",
    }


@app.delete("/api/setup/value/{key}")
async def delete_setup_value(
    key: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    if IS_VERCEL:
        raise HTTPException(
            status_code=409,
            detail="Browser setup is disabled on Vercel.",
        )
    if key not in known_setup_keys(registry):
        raise HTTPException(status_code=400, detail="Unknown setup key")
    store.delete_secret(key)
    return {"ok": True, "key": key}


@app.get("/v1/providers")
@app.get("/api/providers")
async def providers() -> dict[str, Any]:
    runtime = {row["provider_id"]: row for row in store.all_runtime()}
    items = []
    for provider in registry.providers:
        rt = runtime.get(provider.id, {})
        items.append(
            {
                "id": provider.id,
                "name": provider.name,
                "tier": provider.tier.value,
                "configured": configured(provider),
                "env_key": provider.env_key,
                "confidence": provider.confidence,
                "verification": provider.verification,
                "docs_url": provider.docs_url,
                "signup_url": provider.signup_url,
                "models": [
                    {
                        **model.model_dump(),
                        "current": model_is_current(model),
                    }
                    for model in provider.models
                    if model.enabled and model.free
                ],
                "quota": provider.quota.model_dump(exclude_none=True),
                "runtime": quota.snapshot(provider),
                "certification": {
                    "state": rt.get("certification_state", "unknown"),
                    "note": rt.get("certification_note"),
                    "last_probe_at": rt.get("last_probe_at"),
                    "last_probe_ok": rt.get("last_probe_ok"),
                },
                "notes": provider.notes,
            }
        )
    return {"providers": items, "updated_at": registry.data.updated_at}


@app.get("/v1/quota")
@app.get("/api/quota")
async def quota_status() -> dict[str, Any]:
    return {"providers": [quota.snapshot(provider) for provider in registry.providers]}


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    data = [
        {"id": model, "object": "model", "owned_by": "the-router"}
        for model in sorted(VIRTUAL_MODELS)
    ]
    for provider in registry.providers:
        for model in provider.models:
            if model.free and model.enabled and model_is_current(model):
                data.append(
                    {
                        "id": f"{provider.id}/{model.id}",
                        "object": "model",
                        "owned_by": provider.id,
                    }
                )
    return {"object": "list", "data": data}


@app.get("/api/usage/summary")
async def usage_summary(hours: int = 24) -> dict[str, Any]:
    hours = min(max(hours, 1), 24 * 90)
    return store.usage_summary(time.time() - hours * 3600)


@app.get("/api/usage/recent")
async def usage_recent(limit: int = 50) -> dict[str, Any]:
    return {"events": store.recent_usage(min(max(limit, 1), 500))}


@app.get("/api/usage/trace/{request_id}")
async def usage_trace(request_id: str) -> dict[str, Any]:
    events = store.request_trace(request_id)
    if not events:
        raise HTTPException(status_code=404, detail="Unknown request id")
    return {"request_id": request_id, "events": events}


@app.post("/api/route/preview")
async def route_preview(request: ChatCompletionRequest) -> dict[str, Any]:
    allow_trial, allow_promo = route_flags(request.model)
    return {
        "requirements": sorted(request_requirements(request)),
        "candidates": router.preview(
            request,
            allow_trial=allow_trial,
            allow_promo=allow_promo,
        ),
    }


@app.post("/api/providers/{provider_id}/quota/refresh")
async def refresh_provider_quota(
    provider_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    try:
        registry.get(provider_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown provider") from exc

    try:
        telemetry = await quota_telemetry.refresh(provider_id)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Provider quota endpoint returned {exc.response.status_code}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Provider quota refresh failed") from exc

    if telemetry is None:
        raise HTTPException(
            status_code=404,
            detail="No active quota telemetry endpoint is configured for this provider",
        )

    quota.merge_provider_telemetry(provider_id, telemetry)
    return {"provider": provider_id, "telemetry": telemetry}


@app.post("/api/providers/{provider_id}/certify")
async def certify(
    provider_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    try:
        provider = registry.get(provider_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown provider") from exc
    return await certify_provider(router, provider)


@app.post("/api/providers/certify-all")
async def certify_all(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    results = []
    for provider in registry.providers:
        if provider.enabled and configured(provider):
            results.append(await certify_provider(router, provider))
    return {"results": results}


@app.post("/api/admin/reload")
async def reload_registry(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    data = registry.reload()
    return {
        "ok": True,
        "updated_at": data.updated_at,
        "providers": len(data.providers),
    }


@app.get("/api/config/env")
async def env_requirements() -> dict[str, Any]:
    return {
        "providers": [
            {
                "provider": provider.id,
                "env_key": provider.env_key,
                "configured": configured(provider),
                "no_key_required": provider.auth in {"none", "optional_bearer"}
                or provider.env_key is None,
            }
            for provider in registry.providers
        ]
    }


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    response: Response,
):
    if IS_VERCEL and not env_bool("ROUTER_ENABLE_HOSTED_API"):
        raise HTTPException(
            status_code=503,
            detail=(
                "Hosted router API is disabled on this Vercel deployment. "
                "Use the local one-command platform, or enable hosted mode only after configuring "
                "provider credentials and a durable remote state backend."
            ),
        )
    allow_trial, allow_promo = route_flags(request.model)

    if request.stream:
        try:
            iterator, provider, model, fallback_count, reason = await router.stream(
                request,
                allow_trial=allow_trial,
                allow_promo=allow_promo,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        return StreamingResponse(
            iterator,
            media_type="text/event-stream",
            headers={
                "x-router-provider": provider,
                "x-router-model": model,
                "x-router-fallback-count": str(fallback_count),
                "x-router-reason": reason,
            },
        )

    try:
        routed = await router.chat(
            request,
            allow_trial=allow_trial,
            allow_promo=allow_promo,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    response.headers["x-router-provider"] = routed.provider
    response.headers["x-router-model"] = routed.model
    response.headers["x-router-fallback-count"] = str(routed.fallback_count)
    response.headers["x-router-reason"] = routed.route_reason
    return routed.body
