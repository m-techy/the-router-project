# Deployment

The Router keeps local use as the default while supporting an opt-in durable hosted data plane.

## 1. Local platform — recommended

Native mode remains the lightest everyday setup:

```bash
./start.sh
```

Docker remains available when you want isolation:

```bash
docker compose up --build
```

Local mode defaults to:

```text
ROUTER_STATE_BACKEND=sqlite
```

SQLite persists usage, quota, health, configuration, encrypted-or-plaintext local credentials, and project keys on your machine or Docker volume.

## 2. Vercel public-site mode — default

When Vercel provides the `VERCEL` environment variable, the root page remains the public project/docs site.

Hosted inference is **fail-closed** by default. Merely setting `ROUTER_ENABLE_HOSTED_API=true` is not enough.

Check readiness at:

```text
GET /api/hosted/readiness
```

## 3. Durable hosted router — opt-in

The Router supports a PostgreSQL state backend:

```text
ROUTER_STATE_BACKEND=postgres
DATABASE_URL=<pooled PostgreSQL connection URL>
```

`POSTGRES_URL` and `POSTGRES_URL_NON_POOLING` are also recognized when `DATABASE_URL` is absent.

For Vercel/serverless use, prefer the pooled/serverless connection URL supplied by your PostgreSQL provider.

The Postgres backend stores the same logical state as local SQLite:

- request usage and fallback traces
- provider/model cooldown and health state
- provider-reported quota snapshots
- settings
- provider credentials
- router project keys and per-project usage

Schema creation is idempotent on startup.

## Hosted security gates

A Vercel deployment reports routing ready only when all of these are true:

```text
ROUTER_STATE_BACKEND=postgres
DATABASE_URL=<durable postgres>
ROUTER_VAULT_KEY=<encryption key>
ROUTER_ADMIN_KEY=<admin API key>
ROUTER_REQUIRE_PROJECT_KEYS=true
at least one router project key exists
ROUTER_ENABLE_HOSTED_API=true
```

Postgres alone is not enough. The Router requires encryption and project authentication before it will spend provider quota from a hosted endpoint.

Generate a vault key locally:

```bash
python -m app.vault generate-key
```

Use a long random value for `ROUTER_ADMIN_KEY`.

## Safe activation sequence

### Step 1 — attach PostgreSQL

Configure:

```text
ROUTER_STATE_BACKEND=postgres
DATABASE_URL=...
ROUTER_VAULT_KEY=...
ROUTER_ADMIN_KEY=...
ROUTER_REQUIRE_PROJECT_KEYS=true
ROUTER_ENABLE_HOSTED_API=false
```

Deploy.

### Step 2 — verify control-plane readiness

```bash
curl https://YOUR_HOST/api/hosted/readiness
```

`control_plane_ready` should be true.

### Step 3 — configure provider credentials

Provider keys may stay in deployment environment variables.

Or store a reviewed setup key in encrypted Postgres state:

```bash
curl -X POST https://YOUR_HOST/api/setup/value \
  -H "Authorization: Bearer $ROUTER_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"key":"GROQ_API_KEY","value":"..."}'
```

Secret values are never returned by setup/status endpoints.

### Step 4 — create a router project key

```bash
curl -X POST https://YOUR_HOST/api/projects \
  -H "Authorization: Bearer $ROUTER_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"my-app","daily_request_limit":500}'
```

Copy the returned `rtr_...` key immediately. Only its hash/prefix are stored.

### Step 5 — enable inference

Set:

```text
ROUTER_ENABLE_HOSTED_API=true
```

Redeploy and check `/api/hosted/readiness` again.

Your client then uses:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://YOUR_HOST/v1",
    api_key="rtr_...",
)
```

## Hosted admin behavior

On Vercel, admin endpoints fail closed when `ROUTER_ADMIN_KEY` is missing.

Credential/config/project mutations also require the serverless-safe Postgres backend plus `ROUTER_VAULT_KEY`.

The public root page does not expose the admin control plane.

## Current hosted limitations

The local SSE endpoint `/api/events` remains disabled on Vercel. A hosted-safe realtime/event mechanism is still a v1.0 item.

Provider HTTP streaming can run through the inference API, subject to the deployment platform's function limits.

## Vercel Git behavior

`vercel.json` disables deployments from `dev`:

```json
{
  "git": {
    "deploymentEnabled": {
      "dev": false
    }
  }
}
```

Development work goes to `dev`; merge to `main` only after CI passes.

## Vercel FastAPI entrypoint

`pyproject.toml` declares:

```toml
[tool.vercel]
entrypoint = "app.main:app"
```

The public Vercel project can therefore remain documentation-only, or become an authenticated hosted router when every readiness gate above is deliberately configured.
