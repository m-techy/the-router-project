from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .certification import certify_provider
from .models import ChatCompletionRequest
from .quota import QuotaManager
from .registry import ProviderRegistry
from .router import FreeRouter, VIRTUAL_MODELS, request_requirements
from .state import StateStore

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path(
    os.getenv("ROUTER_PROVIDER_REGISTRY", str(ROOT / "config" / "providers.yaml"))
)
DB_PATH = Path(os.getenv("ROUTER_DB_PATH", str(ROOT / "data" / "router.db")))
STATIC_DIR = ROOT / "app" / "static"

registry = ProviderRegistry(REGISTRY_PATH)
store = StateStore(DB_PATH)
quota = QuotaManager(store)
router = FreeRouter(
    registry,
    quota,
    timeout=float(os.getenv("ROUTER_REQUEST_TIMEOUT", "120")),
)


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def configured(provider) -> bool:
    if provider.auth in {"none", "optional_bearer"} or provider.env_key is None:
        return True
    return bool(os.getenv(provider.env_key))


def route_flags(model: str) -> tuple[bool, bool]:
    allow_trial = env_bool("ROUTER_ALLOW_TRIAL") or model == "trial/auto"
    allow_promo = env_bool("ROUTER_ALLOW_PROMO") or model == "promo/auto"
    return allow_trial, allow_promo


def require_admin(authorization: str | None) -> None:
    admin_key = os.getenv("ROUTER_ADMIN_KEY")
    if admin_key and authorization != f"Bearer {admin_key}":
        raise HTTPException(status_code=401, detail="Admin authorization required")


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
    version="0.2.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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
    }


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
                    model.model_dump()
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
            if model.free and model.enabled:
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
        if provider.enabled:
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
