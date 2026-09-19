from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .certification import certify_provider
from .modalities import EMBEDDING_MODELS, TRANSCRIPTION_MODELS, ModalityRouter
from .models import ChatCompletionRequest, EmbeddingRequest
from .project_keys import (
    ProjectCreate,
    authenticate_project,
    bearer_token,
    create_project_key,
    project_limit_state,
)
from .quota import QuotaManager
from .quota_telemetry import QuotaTelemetry
from .registry import ProviderRegistry, model_is_current
from .router import FreeRouter, VIRTUAL_MODELS, request_requirements
from .route_profiles import (
    RouteProfile,
    delete_route_profile,
    load_route_profiles,
    route_model_id,
    save_route_profile,
)
from .setup import SetupValue, configured_value, known_setup_keys, provider_setup_status
from .state_backend import create_state_store, state_backend_info

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path(
    os.getenv("ROUTER_PROVIDER_REGISTRY", str(ROOT / "config" / "providers.yaml"))
)
IS_VERCEL = bool(os.getenv("VERCEL"))
DEFAULT_DB_PATH = "/tmp/router.db" if IS_VERCEL else str(ROOT / "data" / "router.db")
DB_PATH = Path(os.getenv("ROUTER_DB_PATH", DEFAULT_DB_PATH))
STATIC_DIR = ROOT / "app" / "static"

registry = ProviderRegistry(REGISTRY_PATH)
store = create_state_store(DB_PATH)
quota = QuotaManager(store)
router = FreeRouter(
    registry,
    quota,
    timeout=float(os.getenv("ROUTER_REQUEST_TIMEOUT", "120")),
)
modalities = ModalityRouter(router)
quota_telemetry = QuotaTelemetry(router.client, store.get_secret)


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def configured(provider) -> bool:
    if provider.auth in {"none", "optional_bearer"} or provider.env_key is None:
        return True
    return configured_value(store, provider.env_key)


def route_flags(model: str) -> tuple[bool, bool]:
    profile_trial, profile_promo = router.route_permissions(model)
    allow_trial = (
        env_bool("ROUTER_ALLOW_TRIAL")
        or model == "trial/auto"
        or profile_trial
    )
    allow_promo = (
        env_bool("ROUTER_ALLOW_PROMO")
        or model == "promo/auto"
        or profile_promo
    )
    return allow_trial, allow_promo


def hosted_control_plane_ready() -> bool:
    info = state_backend_info(store)
    return bool(
        info["serverless_safe"]
        and store.vault_status().get("enabled")
        and os.getenv("ROUTER_ADMIN_KEY")
    )


def hosted_routing_ready() -> bool:
    return bool(
        hosted_control_plane_ready()
        and env_bool("ROUTER_ENABLE_HOSTED_API")
        and env_bool("ROUTER_REQUIRE_PROJECT_KEYS")
        and len(store.list_projects()) > 0
    )


def require_admin(authorization: str | None) -> None:
    admin_key = os.getenv("ROUTER_ADMIN_KEY")
    if IS_VERCEL and not admin_key:
        raise HTTPException(
            status_code=503,
            detail="Hosted admin operations require ROUTER_ADMIN_KEY.",
        )
    if admin_key and authorization != f"Bearer {admin_key}":
        raise HTTPException(status_code=401, detail="Admin authorization required")


def require_writable_control_plane() -> None:
    if IS_VERCEL and not hosted_control_plane_ready():
        raise HTTPException(
            status_code=409,
            detail=(
                "Hosted writes require a serverless-safe Postgres state backend, "
                "ROUTER_VAULT_KEY, and ROUTER_ADMIN_KEY."
            ),
        )


def require_routing_runtime() -> None:
    if IS_VERCEL and not hosted_routing_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "Hosted routing is fail-closed. Configure Postgres state, ROUTER_VAULT_KEY, "
                "ROUTER_ADMIN_KEY, ROUTER_REQUIRE_PROJECT_KEYS=true, at least one project key, "
                "and ROUTER_ENABLE_HOSTED_API=true."
            ),
        )


class ConfigImport(BaseModel):
    version: int = 1
    settings: dict[str, Any] = Field(default_factory=dict)


def project_access(authorization: str | None) -> dict[str, Any] | None:
    project = authenticate_project(store, authorization)
    token = bearer_token(authorization)
    required = env_bool("ROUTER_REQUIRE_PROJECT_KEYS")

    if project is None:
        if required or (token and token.startswith("rtr_")):
            raise HTTPException(status_code=401, detail="Valid router project key required")
        return None

    limits = project_limit_state(store, project)
    if limits["request_limit_exhausted"]:
        raise HTTPException(status_code=429, detail="Project daily request limit reached")
    if limits["token_limit_exhausted"]:
        raise HTTPException(status_code=429, detail="Project daily token limit reached")
    return project


def begin_project_request(project: dict[str, Any] | None) -> None:
    if project:
        store.record_project_usage(str(project["id"]), requests=1, tokens=0)


def record_project_tokens(project: dict[str, Any] | None, body: dict[str, Any]) -> None:
    if not project:
        return
    usage = body.get("usage") or {}
    total = int(
        usage.get("total_tokens")
        or usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or 0
    )
    if total > 0:
        store.record_project_usage(str(project["id"]), requests=0, tokens=total)


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
        "mode": (
            "hosted-platform"
            if IS_VERCEL and hosted_control_plane_ready()
            else ("vercel-site" if IS_VERCEL else "local-platform")
        ),
        "writable_setup": (not IS_VERCEL) or hosted_control_plane_ready(),
        "hosted_api_enabled": hosted_routing_ready(),
        "state": state_backend_info(store),
        "provider_setup": provider_setup_status(registry, store),
        "vault": store.vault_status(),
        "projects": {
            "count": len(store.list_projects()),
            "enforced": env_bool("ROUTER_REQUIRE_PROJECT_KEYS"),
        },
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
    version="0.7.0",
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
        "db": str(DB_PATH) if getattr(store, "backend_name", "") == "sqlite" else None,
        "state": state_backend_info(store),
        "transport": router.transport_mode,
        "mode": (
            "hosted-platform"
            if IS_VERCEL and hosted_control_plane_ready()
            else ("vercel-site" if IS_VERCEL else "local-platform")
        ),
        "hosted_control_plane_ready": hosted_control_plane_ready() if IS_VERCEL else True,
        "hosted_api_enabled": hosted_routing_ready() if IS_VERCEL else True,
    }


@app.get("/api/setup/status")
async def setup_status_endpoint() -> dict[str, Any]:
    return setup_status()


@app.get("/api/setup/snippets")
async def setup_snippets(request: Request) -> dict[str, Any]:
    return {
        "base_url": f"{public_base_url(request)}/v1",
        "snippets": client_snippets(public_base_url(request)),
        "virtual_models": sorted(VIRTUAL_MODELS | EMBEDDING_MODELS | TRANSCRIPTION_MODELS),
    }


@app.post("/api/setup/value")
async def setup_value(
    item: SetupValue,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    require_writable_control_plane()
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
    require_writable_control_plane()
    if key not in known_setup_keys(registry):
        raise HTTPException(status_code=400, detail="Unknown setup key")
    store.delete_secret(key)
    return {"ok": True, "key": key}


@app.get("/api/hosted/readiness")
async def hosted_readiness() -> dict[str, Any]:
    info = state_backend_info(store)
    checks = {
        "vercel": IS_VERCEL,
        "serverless_safe_state": info["serverless_safe"],
        "vault_key": bool(store.vault_status().get("enabled")),
        "admin_key": bool(os.getenv("ROUTER_ADMIN_KEY")),
        "project_keys_enforced": env_bool("ROUTER_REQUIRE_PROJECT_KEYS"),
        "project_count": len(store.list_projects()),
        "hosted_api_flag": env_bool("ROUTER_ENABLE_HOSTED_API"),
    }
    return {
        "state": info,
        "control_plane_ready": hosted_control_plane_ready() if IS_VERCEL else True,
        "routing_ready": hosted_routing_ready() if IS_VERCEL else True,
        "checks": checks,
    }


@app.get("/api/vault/status")
async def vault_status() -> dict[str, Any]:
    return store.vault_status()


@app.get("/api/projects")
async def projects(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    items = []
    for project in store.list_projects():
        item = dict(project)
        item["usage_today"] = store.project_usage_today(str(project["id"]))
        items.append(item)
    return {
        "projects": items,
        "enforced": env_bool("ROUTER_REQUIRE_PROJECT_KEYS"),
    }


@app.post("/api/projects")
async def create_project(
    item: ProjectCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    require_writable_control_plane()
    created = create_project_key(store, item)
    return {
        **created,
        "warning": "The project key is returned once. Store it securely.",
    }


@app.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    require_writable_control_plane()
    if not store.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Unknown project")
    return {"ok": True, "id": project_id}


@app.get("/api/config/export")
async def export_config(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    return {
        "version": 1,
        "settings": store.all_settings(),
        "configured_secret_keys": store.secret_keys(),
        "secrets_included": False,
        "vault": store.vault_status(),
    }


@app.post("/api/config/import")
async def import_config(
    item: ConfigImport,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    require_writable_control_plane()
    if item.version != 1:
        raise HTTPException(status_code=400, detail="Unsupported config export version")
    if len(item.settings) > 500:
        raise HTTPException(status_code=400, detail="Too many settings")
    for key, value in item.settings.items():
        store.set_setting(str(key), value)
    return {
        "ok": True,
        "settings_imported": len(item.settings),
        "secrets_imported": 0,
    }


@app.get("/api/events")
async def live_events(
    request: Request,
    after_id: int = 0,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    if IS_VERCEL:
        raise HTTPException(
            status_code=409,
            detail="Live local event streaming is disabled on Vercel.",
        )

    async def event_stream():
        resume_id = 0
        if last_event_id:
            try:
                resume_id = int(last_event_id)
            except ValueError:
                resume_id = 0
        cursor = max(0, after_id, resume_id)
        idle_ticks = 0
        while not await request.is_disconnected():
            rows = store.usage_after_id(cursor, limit=100)
            if rows:
                idle_ticks = 0
                for row in rows:
                    cursor = max(cursor, int(row["id"]))
                    payload = json.dumps(row, separators=(",", ":"), default=str)
                    yield f"id: {cursor}\nevent: usage\ndata: {payload}\n\n"
            else:
                idle_ticks += 1
                if idle_ticks >= 15:
                    idle_ticks = 0
                    yield ": heartbeat\n\n"
                await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/api/adapters")
async def adapters() -> dict[str, Any]:
    return {"sdk_version": "1.0", "adapters": router.adapter_inventory()}


@app.get("/api/routes")
async def route_profiles() -> dict[str, Any]:
    profiles = load_route_profiles(store)
    return {
        "routes": [
            {
                **profile.model_dump(),
                "model": route_model_id(profile.slug),
            }
            for profile in profiles.values()
        ]
    }


@app.post("/api/routes")
async def create_or_update_route(
    profile: RouteProfile,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    require_writable_control_plane()

    provider_ids = {provider.id for provider in registry.providers}
    unknown = sorted(
        (set(profile.providers_allow) | set(profile.providers_deny)) - provider_ids
    )
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown providers in route profile: {', '.join(unknown)}",
        )
    overlap = sorted(set(profile.providers_allow) & set(profile.providers_deny))
    if overlap:
        raise HTTPException(
            status_code=400,
            detail=f"Provider cannot be both allowed and denied: {', '.join(overlap)}",
        )

    save_route_profile(store, profile)
    return {
        "ok": True,
        "route": profile.model_dump(),
        "model": route_model_id(profile.slug),
    }


@app.delete("/api/routes/{slug}")
async def remove_route_profile(
    slug: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    require_writable_control_plane()
    if not delete_route_profile(store, slug):
        raise HTTPException(status_code=404, detail="Unknown route profile")
    return {"ok": True, "slug": slug}


@app.get("/api/doctor")
async def doctor() -> dict[str, Any]:
    setup = setup_status()
    vault = store.vault_status()
    profiles = load_route_profiles(store)
    checks: list[dict[str, Any]] = []

    def add(
        check_id: str,
        status: str,
        title: str,
        detail: str,
        action_view: str | None = None,
    ) -> None:
        checks.append(
            {
                "id": check_id,
                "status": status,
                "title": title,
                "detail": detail,
                "action_view": action_view,
            }
        )

    configured_count = int(setup.get("providers_ready") or 0)
    persistent_count = int(setup.get("persistent_ready") or 0)
    add(
        "providers",
        "pass" if configured_count else "warn",
        "Provider capacity",
        (
            f"{configured_count} provider pools are ready."
            if configured_count
            else "No provider pool is ready for routing yet."
        ),
        None if configured_count else "setup",
    )
    add(
        "redundancy",
        "pass" if persistent_count >= 2 else "warn",
        "Fallback redundancy",
        (
            f"{persistent_count} recurring-free pools are ready."
            if persistent_count >= 2
            else "Configure at least two recurring-free pools for meaningful fallback."
        ),
        "setup" if persistent_count < 2 else None,
    )

    stored = int(vault.get("stored_secrets") or 0)
    encrypted = int(vault.get("encrypted_secrets") or 0)
    add(
        "vault",
        "pass" if not stored or encrypted == stored else "warn",
        "Credential storage",
        (
            "No local credentials are stored."
            if not stored
            else (
                f"All {stored} stored credentials are encrypted."
                if encrypted == stored
                else f"{stored - encrypted} stored credential(s) are not encrypted at rest."
            )
        ),
        "setup" if stored and encrypted != stored else None,
    )

    try:
        updated = dt.date.fromisoformat(registry.data.updated_at)
        age = (dt.datetime.now(dt.timezone.utc).date() - updated).days
    except ValueError:
        age = 999
    add(
        "registry",
        "pass" if age <= 14 else "warn",
        "Provider registry freshness",
        (
            f"Registry was reviewed {age} day(s) ago."
            if age <= 14
            else f"Registry is {age} day(s) old; free-tier/model status should be reviewed."
        ),
        "catalog" if age > 14 else None,
    )

    preview_request = ChatCompletionRequest(
        model="free/auto",
        messages=[{"role": "user", "content": "health check"}],
        max_tokens=1,
    )
    candidates = router.preview(
        preview_request,
        allow_trial=False,
        allow_promo=False,
        limit=5,
    )
    add(
        "routing",
        "pass" if candidates else "warn",
        "Default route",
        (
            f"free/auto currently has {len(candidates)} eligible candidate(s)."
            if candidates
            else "free/auto has no eligible configured candidate right now."
        ),
        "providers" if not candidates else None,
    )

    add(
        "projects",
        "pass" if setup.get("projects", {}).get("count") else "info",
        "Project isolation",
        (
            f"{setup.get('projects', {}).get('count', 0)} project key(s) exist."
            if setup.get("projects", {}).get("count")
            else "Project keys are optional locally; create one when an app needs its own limits."
        ),
        "projects",
    )
    add(
        "routes",
        "pass" if profiles else "info",
        "Custom routing",
        (
            f"{len(profiles)} custom route profile(s) are configured."
            if profiles
            else "No custom routes yet; free/* presets remain available."
        ),
        "routes",
    )

    if IS_VERCEL:
        ready = hosted_routing_ready()
        add(
            "hosted",
            "pass" if ready else "info",
            "Hosted routing",
            "Hosted inference is ready." if ready else "Hosted routing remains safely disabled.",
            None,
        )

    score = sum(1 for item in checks if item["status"] == "pass")
    warnings = sum(1 for item in checks if item["status"] == "warn")
    return {
        "ok": warnings == 0,
        "score": score,
        "checks_total": len(checks),
        "warnings": warnings,
        "checks": checks,
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
    route_models = {
        route_model_id(slug)
        for slug, profile in load_route_profiles(store).items()
        if profile.enabled
    }
    data = [
        {"id": model, "object": "model", "owned_by": "the-router"}
        for model in sorted(
            VIRTUAL_MODELS | EMBEDDING_MODELS | TRANSCRIPTION_MODELS | route_models
        )
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


@app.get("/api/catalog/reconciliation")
async def catalog_reconciliation() -> dict[str, Any]:
    path = Path(
        os.getenv(
            "ROUTER_FCM_RECONCILIATION",
            str(ROOT / "runtime" / "fcm-reconciliation.json"),
        )
    )
    if not path.exists():
        return {
            "available": False,
            "message": (
                "No local catalog reconciliation report yet. "
                "Run scripts/fcm_discovery.py and scripts/reconcile_fcm.py."
            ),
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Catalog reconciliation report is invalid") from exc
    return {"available": True, **data}


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
        "requirements": sorted(router.resolved_requirements(request)),
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


@app.post("/v1/embeddings")
async def embeddings(
    request: EmbeddingRequest,
    response: Response,
    authorization: str | None = Header(default=None),
):
    require_routing_runtime()

    project = project_access(authorization)
    begin_project_request(project)
    allow_trial, allow_promo = route_flags(request.model)
    try:
        routed = await modalities.embeddings(
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
    record_project_tokens(project, routed.body)
    return routed.body


@app.post("/v1/audio/transcriptions")
async def audio_transcriptions(
    file: UploadFile = File(...),
    model: str = Form("transcribe/auto"),
    language: str | None = Form(default=None),
    prompt: str | None = Form(default=None),
    response_format: str = Form(default="json"),
    temperature: float | None = Form(default=None),
    authorization: str | None = Header(default=None),
):
    require_routing_runtime()

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    project = project_access(authorization)
    begin_project_request(project)
    allow_trial, allow_promo = route_flags(model)
    try:
        routed = await modalities.transcription(
            requested_model=model,
            filename=file.filename or "audio.bin",
            data=content,
            content_type=file.content_type or "application/octet-stream",
            language=language,
            prompt=prompt,
            response_format=response_format,
            temperature=temperature,
            allow_trial=allow_trial,
            allow_promo=allow_promo,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return Response(
        content=routed.content,
        media_type=routed.content_type.split(";", 1)[0],
        headers={
            "x-router-provider": routed.provider,
            "x-router-model": routed.model,
            "x-router-fallback-count": str(routed.fallback_count),
            "x-router-reason": routed.route_reason,
        },
    )


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    response: Response,
    authorization: str | None = Header(default=None),
):
    require_routing_runtime()
    project = project_access(authorization)
    begin_project_request(project)
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
    record_project_tokens(project, routed.body)
    return routed.body
