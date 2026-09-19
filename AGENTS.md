# AGENTS.md — The Router Project

This file is the operating contract for coding agents working in this repository.

## Mission

Build a plug-and-play AI router that lets personal/hobby projects consume legitimate **recurring free API capacity first** across as many providers as practical, behind one OpenAI-compatible API. The project may later support a hosted product, but self-hosted personal use is the primary requirement.

## Non-negotiable invariants

1. **$0 by default.** `free/auto` must never silently route to a paid model or consume a paid balance.
2. **Persistent free != trial.** Signup credits, expiring credits, launch promos, and temporary free models belong in `trial` or `promotional` and require explicit opt-in.
3. **Do not evade provider limits.** Never create/rotate identities or assume multiple keys multiply a quota when the provider scopes limits to account/project/org/IP.
4. **One external contract.** The primary client API is OpenAI-compatible. Provider-specific quirks belong behind adapters/normalizers.
5. **Upstream first.** Before implementing a provider workaround, inspect `config/upstreams.yaml` and the relevant upstream recent changes.
6. **License boundaries matter.** Bifrost Apache-2.0 and MIT code can be reused with attribution. New-API AGPL code is reference-only unless the whole licensing strategy is intentionally revisited. Do not copy unknown-license code.
7. **No unverified free claims.** Community catalogs can discover candidates, but recurring-free status must have official/live evidence before enabling a provider in the persistent pool.
8. **Secrets never enter git.** Keys may come from environment variables or the local SQLite setup store. The local store is not encrypted at rest yet; logs/dashboard must never display raw provider credentials, and environment variables are preferred for shared/remote deployments.
9. **Discovery never auto-promotes.** Catalog sync/reconciliation may create reports and candidates, but only a reviewed registry edit can make a model routable.

## Architecture

- `app/main.py` — FastAPI facade, setup APIs, dashboard APIs, OpenAI endpoint
- `app/router.py` — candidate filtering, scoring, fallback, route metadata
- `app/quota.py` — quota estimates, provider-header reconciliation, provider/model cooldowns
- `app/quota_telemetry.py` — active provider account/quota telemetry where a current official endpoint exists
- `app/normalization.py` — strict-provider request schema normalization
- `app/discovery.py` — review-only model/pricing discovery helpers
- `app/state.py` — SQLite usage ledger, request traces, runtime persistence, settings
- `app/certification.py` — active / retry_later / configured / quarantine probes
- `app/fcm_catalog.py` — safe text parser + reconciliation for free-coding-models
- `app/providers/` — provider transports/adapters
- `config/providers.yaml` — reviewed active provider/model registry
- `config/upstreams.yaml` — projects to inspect before solving known gateway/provider problems
- `scripts/fcm_discovery.py` — snapshots upstream reference files only
- `scripts/reconcile_fcm.py` — review-only catalog diff; never edits the registry
- `app/static/` — dashboard, setup flow, playground, usage/request traces

## Provider addition workflow

1. Discover candidate from official docs, free-coding-models, upstream gateway fixes, or a provider announcement.
2. Determine tier: `persistent_free`, `promotional`, `trial`, or `paid`.
3. Record quota scope accurately.
4. Confirm API shape and OpenAI compatibility.
5. Add only explicitly free models.
6. Add a tiny certification probe.
7. Add/adjust tests.
8. Update README only when the provider is represented in config.

## Routing priorities

Capabilities are hard filters before scoring. Scoring may use model quality, quota headroom, observed health, latency, verification confidence, certification state, and virtual-model intent. Hidden paid fallback is forbidden.

Streaming may fail over only before the first downstream byte.

## Data plane strategy

The built-in direct transport keeps personal installation lightweight. `ROUTER_TRANSPORT=bifrost` is optional for mature provider normalization/retry behavior.

## Development commands

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ruff check app tests scripts
pytest -q
uvicorn app.main:app --reload --port 4010
```

Refresh the upstream free-model reference without executing it:

```bash
python scripts/fcm_discovery.py
python scripts/reconcile_fcm.py
```

## Definition of done

- tests pass
- no secrets committed
- default routing remains zero-cost-only
- provider tier/quota scope is accurate
- dashboard/API still loads
- discovery output cannot silently change the routing pool
- upstream/license implications were considered
