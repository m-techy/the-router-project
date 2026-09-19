# The Router

**One OpenAI-compatible API over the legitimate free AI capacity you already have.**

The Router is a personal-first AI gateway for hobby projects, prototypes, agents, and side projects that should not need a permanent LLM bill. It combines recurring free tiers, zero-price models, provider health, quota estimates, live rate-limit headers, automatic fallback, a setup dashboard, and request traces behind a single local endpoint.

> Default policy: **spend $0**. Trials and temporary promotions are isolated from the normal pool and require explicit opt-in.

## What you get

- OpenAI-compatible `POST /v1/chat/completions`, `POST /v1/responses`, `POST /v1/embeddings`, `POST /v1/audio/transcriptions`, and `POST /v1/images/generations`
- chat routes: `free/auto`, `free/fast`, `free/smart`, `free/code`, `free/reasoning`, `free/vision`, `free/long`
- embedding routes: `embed/auto`, `embed/text`, `embed/multimodal`
- transcription routes: `transcribe/auto`, `transcribe/fast`, `transcribe/accurate`
- image routes: `image/auto`, `image/fast`, `image/quality`
- persistent custom chat routes such as `route/my-app`
- automatic provider/model fallback before a response begins
- capability-aware routing for tools, JSON, vision, coding, reasoning, and context size
- persistent SQLite usage ledger, request traces, and provider health state
- quota-aware scoring with provider rate-limit header reconciliation
- provider certification states: `active`, `retry_later`, `configured`, `quarantine`
- browser control plane with first-run setup, provider inventory, custom route profiles, System Doctor, playground, usage, and fallback traces
- recurring-free, promotional, and trial pools kept separate
- upstream watchlist so we inspect existing fixes before writing our own
- safe `free-coding-models` catalog reconciliation without executing upstream JavaScript
- optional Bifrost transport for mature provider normalization while keeping the default install lightweight
- Gemini hybrid transport: OpenAI compatibility first, native Gemini REST fallback for compatibility gaps
- optional Fernet-encrypted local credential vault
- per-project router API keys with daily request/token limits
- live local SSE usage stream and safe config export/import
- session-only browser admin unlock and project-key-aware Playground/snippets

## Run locally

The lightweight native launcher is the default for personal use. Docker is optional.

### One-command install

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/m-techy/the-router-project/main/install.sh | bash
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/m-techy/the-router-project/main/install.ps1 | iex
```

The installer clones or fast-forward updates `~/.the-router` / `$HOME\.the-router`, verifies Python 3.11+, then launches the normal lightweight native runner. Set `ROUTER_INSTALL_NO_START=1` if you only want to install/update without starting.

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

Provider credentials saved through Setup stay in the local SQLite data store. Set `ROUTER_VAULT_KEY` to encrypt locally stored values at rest; environment variables still take precedence and remain a good choice for managed deployments.

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

### Responses compatibility

Stateless Responses-style requests can use the same base URL:

```python
response = client.responses.create(
    model="free/auto",
    instructions="Be concise.",
    input="Explain vector databases in two sentences.",
)
print(response.output_text)
```

The compatibility layer maps text, messages, function tools, function-call history, JSON response formats, and text streaming onto the Router's existing multi-provider chat engine. Features that require server-side OpenAI state are deliberately rejected: `previous_response_id`, Conversations, background jobs, and `store=true`. Streaming with function-tool deltas is also rejected for now instead of returning an incomplete event stream.

### Image generation

```python
image = client.images.generate(
    model="image/auto",
    prompt="A tiny robot repairing a telescope at night",
)
print(image.data[0].b64_json)
```

The initial reviewed image pool routes to Cloudflare Workers AI FLUX.1 Schnell. The Router returns base64 JPEG output and tracks a conservative daily-neuron reservation so the Cloudflare free allocation remains part of the zero-cost boundary. Unsupported size, transparent-background, URL-output, and multi-image requests fail explicitly.

## Web platform

The browser UI is the primary control plane, not an optional demo. It provides first-run provider setup, generated SDK snippets, an in-app usage guide, quota/health visibility, certification probes, model inventory, route previews, an interactive playground, persistent request traces, and a review queue for upstream model changes.

Provider credential values are never returned to the browser after they are saved. Locally saved credentials can be Fernet-encrypted at rest by setting `ROUTER_VAULT_KEY`; without that option they remain compatible plaintext local storage.

## v0.5 local platform controls

The local platform can optionally encrypt credentials at rest:

```bash
python -m app.vault generate-key
```

Set the generated value as `ROUTER_VAULT_KEY` before launch. Existing plaintext local credentials migrate to encrypted values as they are read.

The **Projects** dashboard view can issue local `rtr_...` API keys with independent daily request/token limits. Only a hash is stored and the plaintext key is shown once. Legacy `api_key="local"` remains accepted unless `ROUTER_REQUIRE_PROJECT_KEYS=true`.

The dashboard also consumes `GET /api/events`, a resumable local SSE stream over the persistent usage ledger.

Config export/import deliberately excludes secret values. Export files contain normal router settings plus the names of configured credential keys, never the credentials themselves.

## v0.6 distribution & ecosystem

The Router now exposes a stable provider adapter SDK v1 through `app.providers.sdk`. Custom adapters can be registered at runtime with `router.register_adapter(...)`, and `GET /api/adapters` reports the active adapter SDK/capability inventory.

Provider contributions are gated by `python scripts/validate_registry.py`, the provider verification issue form, and the pull-request checklist in `CONTRIBUTING.md`.

Registry releases are built as deterministic `provider-registry.zip` bundles containing canonical JSON, a manifest, and SHA-256 checksums. Release workflows generate GitHub/Sigstore provenance attestations. After downloading a bundle:

```bash
gh attestation verify provider-registry.zip -R m-techy/the-router-project
unzip provider-registry.zip
sha256sum -c providers.sha256
```

See `docs/REGISTRY_RELEASES.md` for the release/verification model.

## v0.7 hosted-state foundation

Local SQLite remains the default. For a durable serverless deployment, set:

```text
ROUTER_STATE_BACKEND=postgres
DATABASE_URL=<pooled postgres url>
```

The PostgreSQL backend persists the same usage, quota, health, settings, encrypted credentials, project keys, and project usage state as the local SQLite store.

On Vercel, hosted inference remains fail-closed until **all** security gates are satisfied: serverless-safe Postgres, `ROUTER_VAULT_KEY`, `ROUTER_ADMIN_KEY`, `ROUTER_REQUIRE_PROJECT_KEYS=true`, at least one issued router project key, and `ROUTER_ENABLE_HOSTED_API=true`.

Use `GET /api/hosted/readiness` to see each gate without exposing secret values.

## v0.8 control plane + compatibility

The dashboard now includes **Routes** and **Doctor**.

Custom routes are persisted as normal Router settings and show up in `/v1/models`. A profile such as `route/my-app` can choose a base strategy, allow/deny providers, require a minimum context window, cap fallback depth, and explicitly opt into promotional or trial capacity.

`GET /api/doctor` performs a no-inference readiness pass over provider capacity, fallback redundancy, credential encryption state, registry freshness, `free/auto` availability, project isolation, custom routes, and hosted safety.

If `ROUTER_ADMIN_KEY` is configured, the browser control plane can be unlocked for the current tab. The value is held only in session storage. A newly created project key is also attached to the Playground for the current tab so requests can be attributed to that project.

## Vercel

This repository can be connected to Vercel. The root page intentionally remains the **public project/docs site** by default.

You can keep it docs-only forever, or deliberately enable the authenticated Postgres-backed router described above. Browser/admin writes on Vercel are also fail-closed unless durable state, vault encryption, and an admin key are configured.

The repository's `vercel.json` disables Vercel deployments for the `dev` branch, so development commits do not create preview builds. Production continues to deploy from `main`.

See `docs/DEPLOYMENT.md` for the safe activation sequence.

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
python scripts/validate_registry.py
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
| `POST /v1/responses` | Stateless Responses-compatible text/function routing |
| `POST /v1/images/generations` | Quota-aware image generation through `image/*` routes |
| `POST /v1/embeddings` | Quota-aware embeddings through `embed/*` routes |
| `POST /v1/audio/transcriptions` | Routed audio transcription through `transcribe/*` routes |
| `GET /v1/models` | Virtual routes + reviewed provider/model IDs |
| `GET /v1/providers` | Provider state/capabilities/quota metadata |
| `GET /v1/quota` | Current local + provider-reported quota state |
| `GET /api/setup/status` | Plug-and-play readiness / missing provider keys |
| `GET /api/adapters` | Adapter SDK version and registered modality capabilities |
| `GET /api/hosted/readiness` | Hosted state/auth/encryption readiness gates |
| `GET /api/doctor` | No-inference readiness and safety diagnostics |
| `GET/POST /api/routes` | List/create persistent custom chat route profiles |
| `DELETE /api/routes/{slug}` | Delete a custom route profile |
| `GET /api/vault/status` | Local credential-vault status without exposing secrets |
| `GET/POST /api/projects` | List or create hashed local router project keys |
| `DELETE /api/projects/{id}` | Revoke a local project key |
| `GET /api/events` | Resumable local SSE usage event stream |
| `GET /api/config/export` | Export normal router settings with secret values excluded |
| `POST /api/config/import` | Import non-secret router settings |
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
