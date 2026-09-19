# Deployment

The Router has two deployment modes with deliberately different responsibilities.

## 1. Local platform — recommended

This is the full router.

```bash
docker compose up --build
```

Open `http://localhost:4010` and use the Setup page to add provider credentials.

Local mode provides:

- durable SQLite usage, quota, health and trace state through the Docker volume
- local provider credential persistence
- provider certification probes
- dashboard + setup wizard + playground
- OpenAI-compatible API on `http://localhost:4010/v1`
- optional Bifrost profile

No `.env` file is required. If an `.env` file exists, Docker Compose loads it and environment values take precedence over browser-saved credentials.

## 2. Vercel site mode

Vercel is currently used as the public project/documentation surface.

The app detects Vercel through the platform-provided `VERCEL` environment variable and serves `app/static/hosted.html` at the root.

The chat routing endpoint returns a deliberate 503 unless `ROUTER_ENABLE_HOSTED_API=true`.

Why? The self-hosted runtime currently depends on:

- SQLite request/quota history
- SQLite provider health/cooldown state
- a local provider credential store

A Vercel Function filesystem is not our durable multi-request database. Running with temporary state would make quota accounting and cooldown behavior unreliable.

## Future hosted router

Before enabling hosted routing in production, add a durable state implementation such as:

- Postgres for usage/history/configuration
- Redis-compatible storage for short-lived rate-limit counters and cooldowns
- an encrypted hosted secret store for provider credentials

Then make the state backend selectable:

```text
ROUTER_STATE_BACKEND=sqlite   # self-hosted default
ROUTER_STATE_BACKEND=postgres # hosted
```

The router engine should not care which persistence backend is active.

## Vercel Git behavior

`vercel.json` contains:

```json
{
  "git": {
    "deploymentEnabled": {
      "dev": false
    }
  }
}
```

Development work goes to `dev`. Vercel does not build that branch. Merge to `main` only after CI passes to trigger a single production deployment.

## Vercel FastAPI entrypoint

`pyproject.toml` explicitly declares:

```toml
[tool.vercel]
entrypoint = "app.main:app"
```

The Vercel function is also given a 60-second maximum duration in `vercel.json`.

## Hosted credentials

Do **not** use the browser credential-storage endpoint on Vercel. It is intentionally disabled.

If hosted API mode is implemented later, credentials must come from Vercel environment variables or a dedicated encrypted remote vault.
