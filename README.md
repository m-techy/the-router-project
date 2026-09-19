# The Router

**One OpenAI-compatible API over the legitimate free AI capacity you already have.**

The Router is a personal-first AI gateway for hobby projects, prototypes, agents, and side projects that should not need a permanent LLM bill. It combines recurring free tiers, zero-price models, provider health, quota estimates, live rate-limit headers, and automatic fallback behind a single local endpoint.

> Default policy: **spend $0**. Trials and temporary promotions are isolated from the normal pool and require explicit opt-in.

## What you get

- OpenAI-compatible `POST /v1/chat/completions`
- virtual routes: `free/auto`, `free/fast`, `free/smart`, `free/code`, `free/reasoning`, `free/vision`, `free/long`
- automatic provider/model fallback before a response begins
- capability-aware routing for tools, JSON, vision, coding, reasoning, and context size
- persistent SQLite usage ledger and health state
- quota-aware scoring with provider rate-limit header reconciliation
- provider certification states: `active`, `retry_later`, `configured`, `quarantine`
- browser dashboard + playground on the same port
- recurring-free, promotional, and trial pools kept separate
- upstream watchlist so we check existing gateway fixes before writing our own
- optional Bifrost transport for mature provider normalization while keeping the default install lightweight

## 60-second start

```bash
git clone https://github.com/m-techy/the-router-project.git
cd the-router-project
cp .env.example .env
# Add whichever provider keys you already have. No-key providers also work.
docker compose up --build
```

Open:

- Dashboard + playground: `http://localhost:4010`
- OpenAI base URL: `http://localhost:4010/v1`
- Health: `http://localhost:4010/health`

Then use the normal OpenAI SDK:

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

## Dashboard

The built-in dashboard is part of the core product. It shows configured providers, free/trial/promo pools, quota headroom, certification state, model inventory, recent routes, a persistent usage ledger, route previews, and an interactive playground. Provider keys are never displayed in the UI.

## Provider coverage

### Persistent / recurring free

Groq, Cerebras, Google AI Studio / Gemini, Cloudflare Workers AI, OpenRouter free models, Mistral, Codestral, Z.AI / Zhipu GLM Flash, SiliconFlow zero-price models, NVIDIA NIM, SambaNova, Kilo Gateway, LLM7, OVHcloud AI Endpoints sandbox, Requesty, Routeway, OrcaRouter, and Ollama Cloud.

### Promotional / opt-in

OpenCode Zen and temporary developer campaigns such as Volcengine Ark / Doubao offers.

### Trial / expiring / not baseline

Alibaba DashScope / Model Studio's current 90-day allocation and Scaleway until recurrence is verified.

The registry is deliberately conservative. A provider being listed does **not** mean every model it exposes is free; only reviewed free models belong in the routing pool.

## Routing policy

A provider/model is considered only if its tier is allowed, the provider is configured or supports no-key access, the model satisfies request capabilities, quota signals indicate capacity, and it is not quarantined/cooling down.

Candidates are scored using model quality, quota headroom, observed reliability, observed latency, verification confidence, certification state, and route intent.

Response headers expose the selected route:

```text
x-router-provider
x-router-model
x-router-fallback-count
x-router-reason
```

Streaming requests may fail over **before the first byte only**. The Router does not splice partial generations from different models.

## Persistent quota and health

Request/health state is persisted in SQLite, so restart does not erase recent daily/monthly usage history. Provider rate-limit headers such as `x-ratelimit-remaining-*` are captured when available.

The Router never assumes multiple API keys multiply capacity when quotas are actually account/project/organization scoped.

## Upstream-first maintenance

We explicitly track:

- `vava-nessa/free-coding-models` — primary free-provider/model discovery + live-health reference
- `maximhq/bifrost` — Apache-2.0 data-plane/provider-normalization reference
- `BerriAI/litellm` — MIT core provider/proxy compatibility reference
- `QuantumNous/new-api` — China-provider/protocol reference (AGPL, reference-only by default)
- `songquanpeng/one-api` — MIT China-provider compatibility reference
- `DevvGwardo/free-llm-router`
- `alienz-dev/llm-router`
- `spacepirate15/quantum-free-router`
- `DeepakSilaych/free-api-gateway`

See `docs/UPSTREAMS.md` and `config/upstreams.yaml`. A scheduled GitHub Action checks for upstream changes so their fixes can be reviewed first.

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
| `GET /v1/models` | Virtual routes + reviewed provider/model IDs |
| `GET /v1/providers` | Provider state/capabilities/quota metadata |
| `GET /v1/quota` | Current local + provider-reported quota state |
| `POST /api/route/preview` | Score candidates without inference |
| `POST /api/providers/{id}/certify` | Tiny live provider probe |
| `GET /api/usage/summary` | Aggregated persistent usage |
| `GET /api/usage/recent` | Recent request ledger |
| `POST /api/admin/reload` | Reload provider registry |
| `GET /health` | Router health |
| `GET /` | Dashboard + playground |

See `ROADMAP.md` for active work.

## Terms and safety

The Router aggregates quotas legitimately assigned to you. It must not create accounts, rotate identities, or otherwise evade provider restrictions. Provider terms, data-use policies, geography restrictions, and content policies still apply.

## License

MIT. Upstream projects retain their own licenses; see `docs/UPSTREAMS.md`.
