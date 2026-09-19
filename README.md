# The Router

**One OpenAI-compatible API over the legitimate free AI capacity you already have.**

The Router is a personal-first AI gateway for hobby projects, prototypes, agents, and side projects that should not need a permanent LLM bill. It combines recurring free tiers, zero-price models, provider health, quota estimates, live rate-limit headers, automatic fallback, a setup dashboard, and request traces behind a single local endpoint.

> Default policy: **spend $0**. Trials and temporary promotions are isolated from the normal pool and require explicit opt-in.

## What you get

- OpenAI-compatible `POST /v1/chat/completions`, `POST /v1/embeddings`, and `POST /v1/audio/transcriptions`
- chat routes: `free/auto`, `free/fast`, `free/smart`, `free/code`, `free/reasoning`, `free/vision`, `free/long`
- embedding routes: `embed/auto`, `embed/text`, `embed/multimodal`
- transcription routes: `transcribe/auto`, `transcribe/fast`, `transcribe/accurate`
- automatic provider/model fallback before a response begins
- capability-aware routing for tools, JSON, vision, coding, reasoning, and context size
- persistent SQLite usage ledger, request traces, and provider health state
- quota-aware scoring with provider rate-limit header reconciliation
- provider certification states: `active`, `retry_later`, `configured`, `quarantine`
- browser dashboard with first-run setup, provider inventory, playground, usage, and fallback traces
- recurring-free, promotional, and trial pools kept separate
- upstream watchlist so we inspect existing fixes before writing our own
- safe `free-coding-models` catalog reconciliation without executing upstream JavaScript
- optional Bifrost transport for mature provider normalization while keeping the default install lightweight
- Gemini hybrid transport: OpenAI compatibility first, native Gemini REST fallback for compatibility gaps

## Run locally

The lightweight native launcher is the default for personal use. Docker is optional.

### Method 1 — native Python (recommended)

Windows:

```powershell
.\start.bat
```

macOS / Linux:

```bash
./start.sh
```

The launcher:

- checks for Python 3.11+
- creates `.venv` once
- installs dependencies only when `pyproject.toml` changes
- starts FastAPI + SQLite directly
- opens `http://localhost:4010` when the router becomes healthy

This is the lightest everyday mode.

### Method 2 — Docker

Windows:

```powershell
.\start-docker.bat
```

macOS / Linux:

```bash
./start-docker.sh
```

Or directly:

```bash
docker compose up -d --build
```

Docker is useful when you want isolation, a reproducible environment, or optional sidecars such as Bifrost.

Full local guide: [docs/LOCAL.md](docs/LOCAL.md)

The web console contains:

- **Setup** — add/remove provider credentials from the browser.
- **Guide** — install, routing, integration, and zero-cost behavior explained.
- **Providers** — model inventory, live quota telemetry where supported, health, and certification.
- **Playground** — preview routes and test prompts.
- **Usage & traces** — persistent request history and fallback chains.
- **Catalog review** — inspect upstream free-model additions/removals before promotion.

Provider credentials saved through Setup stay in the local SQLite data store. The local store is not encrypted at rest yet; environment variables still take precedence and are preferred for shared/remote deployments.

OpenAI base URL:

```text
http://localhost:4010/v1
```

Python example:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:4010/v1",
    api_key="local",
)

response = client.chat.completions.create(
    model="free/auto",
    messages=[{"role": "user", "content": "Summarize this article"}],
)

print(response.choices[0].message.content)
```

Your app does not need to know whether the request actually ran on Groq, Gemini, Cerebras, Z.AI, Kilo, OVH, or another configured pool.

### Embeddings

OpenAI SDKs can use the same base URL:

```python
embedding = client.embeddings.create(
    model="embed/auto",
    input=["first document", "second document"],
)
print(len(embedding.data[0].embedding))
```

For Gemini multimodal embeddings, The Router also accepts structured parts through the raw endpoint and can route inline text, image data URLs, and base64 audio to `embed/multimodal`. Text-only embedding models are automatically excluded when the input needs vision or audio.

### Audio transcription

```python
with open("meeting.wav", "rb") as audio:
    transcript = client.audio.transcriptions.create(
        model="transcribe/auto",
        file=audio,
    )

print(transcript.text)
```

`transcribe/fast` favors observed latency; `transcribe/accurate` gives more weight to model quality. The initial v0.4 pool uses Groq's reviewed Whisper models.

## Web platform

The browser UI is the primary control plane, not an optional demo. It provides first-run provider setup, generated SDK snippets, an in-app usage guide, quota/health visibility, certification probes, model inventory, route previews, an interactive playground, persistent request traces, and a review queue for upstream model changes.

Provider credential values are never returned to the browser after they are saved. Locally saved credentials live in the SQLite-backed router data volume and are **not encrypted at rest yet**; use environment variables for shared or remote deployments.

## Vercel

This repository can also be connected to Vercel. On Vercel, The Router intentionally serves a **public project/docs site** by default.

FastAPI and streaming can run on Vercel, but the current full router uses a local SQLite usage/quota ledger and local credential store. Those are not a durable state layer for serverless Functions, so the hosted routing API is disabled by default.

A future hosted mode should use a durable remote backend such as Postgres/Redis before enabling `ROUTER_ENABLE_HOSTED_API=true`.

The repository's `vercel.json` disables Vercel deployments for the `dev` branch, so development commits do not create preview builds. Production continues to deploy from `main`.

See `docs/DEPLOYMENT.md` for the deployment split.

## Provider coverage

### Persistent / recurring free

Groq, Cerebras, Google AI Studio / Gemini, Cloudflare Workers AI, OpenRouter free models, Vercel AI Gateway reviewed zero-price models, Mistral, Codestral, Z.AI / Zhipu GLM Flash, SiliconFlow zero-price models, NVIDIA NIM, SambaNova, Kilo Gateway, LLM7, OVHcloud AI Endpoints sandbox, Requesty, Routeway, OrcaRouter, and Ollama Cloud.

### Promotional / opt-in

OpenCode Zen, Pollinations Pollen-backed access, Hugging Face Inference Providers' small monthly credit pool, and temporary developer campaigns such as Volcengine Ark / Doubao offers.

### Trial / expiring / not baseline

Alibaba DashScope / Model Studio's current time-limited allocation and Scaleway until recurrence is verified.

The registry is deliberately conservative. A provider being listed does **not** mean every model it exposes is free; only reviewed free models belong in the routing pool.

## Routing policy

A provider/model is considered only if:
1. its tier is allowed,
2. the provider is configured or supports no-key access,
3. the model satisfies request capabilities,
4. quota signals indicate capacity, and
5. it is not quarantined or cooling down.

Candidates are scored using model quality, quota headroom, observed reliability, observed latency, verification confidence, certification state, and route intent.

Response headers expose the selected route:

```text
x-router-provider
x-router-model
x-router-fallback-count
x-router-reason
```

Streaming requests may fail over **before the first byte only**. The Router does not splice partial generations from different models.

## Persistent quota, health, and traces

Request/health state is persisted in SQLite, so restarting the router does not erase recent daily/monthly usage history. Provider rate-limit headers such as `x-ratelimit-remaining-*` are captured when available.

Every fallback attempt shares a router request ID, which lets the dashboard reconstruct:

```text
Groq → 429
Cerebras → 5xx
Gemini → 200
```

The Router never assumes multiple API keys multiply capacity when quotas are actually account/project/organization scoped.

## Upstream-first maintenance

We explicitly track:

- `vava-nessa/free-coding-models` — primary free-provider/model discovery + live-health reference
- `maximhq/bifrost` — Apache-2.0 data-plane/provider-normalization reference
- `BerriAI/litellm` — provider/proxy compatibility reference
- `QuantumNous/new-api` — China-provider/protocol reference (AGPL, reference-only by default)
- `songquanpeng/one-api` — MIT China-provider compatibility reference
- `DevvGwardo/free-llm-router`
- `alienz-dev/llm-router`
- `spacepirate15/quantum-free-router`
- `DeepakSilaych/free-api-gateway`

See `docs/UPSTREAMS.md` and `config/upstreams.yaml`. A scheduled GitHub Action checks for upstream changes so their fixes can be reviewed first.

## Safe free-coding-models sync

We use `free-coding-models` aggressively as a discovery reference, but never let it modify the active routing pool automatically.

```bash
python scripts/fcm_discovery.py
python scripts/reconcile_fcm.py
```

The first command snapshots upstream reference files. The second parses `sources.js` as text and writes a review-only diff showing:
- new upstream models not yet reviewed here
- reviewed models that disappeared upstream
- per-provider catalog counts

No upstream JavaScript is executed and `providers.yaml` is never edited by the reconciliation script.

## Bifrost mode

The default direct transport keeps personal installation small. If you run Bifrost, The Router can stay the free-capacity control plane while Bifrost handles provider wire formats:

```bash
ROUTER_TRANSPORT=bifrost
ROUTER_BIFROST_URL=http://bifrost:8080
docker compose --profile bifrost up --build
```

Bifrost provider credentials still need to be configured separately.

## Maintenance

```bash
python scripts/fcm_discovery.py
python scripts/reconcile_fcm.py
python scripts/discover_models.py
python scripts/check_upstreams.py
```

Discovery does not auto-promote an unknown model into `free/auto`.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ruff check app tests scripts
pytest -q
uvicorn app.main:app --reload --port 4010
```

## API surface

| Endpoint | Purpose |
|---|---|
| `POST /v1/chat/completions` | OpenAI-compatible routed completion |
| `POST /v1/embeddings` | Quota-aware embeddings through `embed/*` routes |
| `POST /v1/audio/transcriptions` | Routed audio transcription through `transcribe/*` routes |
| `GET /v1/models` | Virtual routes + reviewed provider/model IDs |
| `GET /v1/providers` | Provider state/capabilities/quota metadata |
| `GET /v1/quota` | Current local + provider-reported quota state |
| `GET /api/setup/status` | Plug-and-play readiness / missing provider keys |
| `GET /api/setup/snippets` | Copyable Python/JS/cURL client configs |
| `POST /api/route/preview` | Score candidates without inference |
| `POST /api/providers/{id}/certify` | Tiny live provider probe |
| `POST /api/providers/{id}/quota/refresh` | Refresh supported active quota/account telemetry |
| `GET /api/catalog/reconciliation` | Review-only upstream model additions/removals |
| `POST /api/setup/value` | Save a known provider setup value locally (self-hosted mode) |
| `GET /api/usage/summary` | Aggregated persistent usage |
| `GET /api/usage/recent` | Recent request ledger |
| `GET /api/usage/trace/{request_id}` | Full fallback chain for one routed request |
| `POST /api/admin/reload` | Reload provider registry |
| `GET /health` | Router health |
| `GET /` | Dashboard, setup, playground, usage/traces |

See `ROADMAP.md` for active work.

## Terms and safety

The Router aggregates quotas legitimately assigned to you. It must not create accounts, rotate identities, or otherwise evade provider restrictions. Provider terms, data-use policies, geography restrictions, and content policies still apply.

## License

MIT. Upstream projects retain their own licenses; see `docs/UPSTREAMS.md`.
