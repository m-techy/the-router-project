# Run The Router locally

You do **not** need Vercel to use The Router.

The Router has two local run methods:

1. **Native Python — recommended for personal use.** Lowest overhead.
2. **Docker — optional.** Better isolation and reproducibility.

For a fresh machine, the one-command installers clone/update the project and then use the same native launcher:

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/m-techy/the-router-project/main/install.sh | bash
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/m-techy/the-router-project/main/install.ps1 | iex
```

"Local" means the router process runs on your computer. Cloud AI providers still require internet access.

## Method 1 — native Python

### Windows

Install Python 3.11 or newer once.

Then double-click:

```text
start.bat
```

or run:

```powershell
.\start.bat
```

The launcher automatically:

1. finds Python 3.11+,
2. creates `.venv` if it does not exist,
3. fingerprints `pyproject.toml`,
4. installs dependencies only when that fingerprint changes,
5. creates the local `data/` directory,
6. starts Uvicorn on `127.0.0.1:4010`,
7. opens the dashboard after the health endpoint responds.

Subsequent launches skip dependency installation unless the project dependencies changed.

Stop the router with **Ctrl+C** in the terminal.

### macOS / Linux

```bash
./start.sh
```

If executable permission was lost after downloading an archive:

```bash
chmod +x start.sh
./start.sh
```

The behavior is the same as Windows: a reusable `.venv`, lightweight FastAPI process, local SQLite state, and automatic browser opening when supported.

## Method 2 — Docker

Use Docker when you prefer isolation, repeatable deployment, or optional sidecars.

### Windows

```powershell
.\start-docker.bat
```

### macOS / Linux

```bash
./start-docker.sh
```

Or use Docker Compose directly:

```bash
docker compose up -d --build
```

Stop Docker mode with:

```bash
docker compose down
```

The Docker volume preserves router state between container restarts.

To intentionally delete Docker-persisted router state and locally stored credentials:

```bash
docker compose down -v
```

## Dashboard and API

Both methods expose the same addresses:

```text
Dashboard: http://localhost:4010
OpenAI API: http://localhost:4010/v1
Health:    http://localhost:4010/health
```

## First-time setup

Open **Setup** in the dashboard.

Some pools are no-key or optional-key. For more capacity, add whichever recurring-free providers you have access to, such as Groq, Gemini, Cerebras, OpenRouter, Mistral, Z.AI, SiliconFlow, and NVIDIA.

Where available, Setup links directly to provider signup and documentation pages.

Environment variables take precedence over credentials saved in the local setup store.

## Test the router

Open **Playground** and choose:

```text
free/auto
```

Run a short prompt, then open **Usage & traces** to see which provider/model handled it and whether fallback occurred.

## Python project example

```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:4010/v1",
    api_key="local",
)

response = client.chat.completions.create(
    model="free/auto",
    messages=[
        {"role": "user", "content": "Explain vector databases simply."}
    ],
)

print(response.choices[0].message.content)
```

## JavaScript / TypeScript example

```bash
npm install openai
```

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:4010/v1",
  apiKey: "local",
});

const response = await client.chat.completions.create({
  model: "free/auto",
  messages: [{ role: "user", content: "Hello" }],
});

console.log(response.choices[0].message.content);
```

## Virtual routes

- `free/auto` — balanced default
- `free/fast` — prioritize observed latency
- `free/smart` — prioritize model quality
- `free/code` — coding-capable models
- `free/reasoning` — reasoning-capable models
- `free/vision` — vision-capable models
- `free/long` — long-context models
- `promo/auto` — explicitly allow promotional providers
- `trial/auto` — explicitly allow trial/expiring providers

The `free/*` routes do not silently use trial/promotional pools.

## Embeddings and transcription

The same local API now exposes modality-aware routes:

```text
POST /v1/embeddings
POST /v1/audio/transcriptions
```

Embedding aliases:

- `embed/auto` — choose the strongest eligible free embedding model
- `embed/text` — text embeddings
- `embed/multimodal` — require a multimodal embedding model

Transcription aliases:

- `transcribe/auto` — balanced Whisper route
- `transcribe/fast` — prioritize observed latency
- `transcribe/accurate` — prioritize model quality

## Optional encrypted credential vault

By default, locally saved provider credentials remain compatible with earlier Router versions.

To encrypt values stored in SQLite, generate a vault key:

```bash
python -m app.vault generate-key
```

Set the returned value as:

```text
ROUTER_VAULT_KEY=<generated-key>
```

Restart The Router. Existing plaintext provider credentials are migrated to Fernet ciphertext as they are read.

Keep the vault key outside the SQLite database. If you lose it, encrypted local credentials cannot be recovered. Environment variables are still supported and still take precedence.

## Per-project router keys

Open **Projects** in the dashboard and create a key for each app.

A project can optionally have:

- a daily request limit
- a daily token limit

The plaintext key is shown once. The database stores only its hash and prefix.

Use the returned key exactly like an OpenAI API key:

```python
client = OpenAI(
    base_url="http://localhost:4010/v1",
    api_key="rtr_...",
)
```

Legacy `api_key="local"` access remains enabled by default.

To require a valid project key on routed API calls:

```text
ROUTER_REQUIRE_PROJECT_KEYS=true
```

## Live usage events

The local dashboard listens to:

```text
GET /api/events
```

This is an SSE stream backed by the persistent usage ledger. Reconnects resume from the last event ID rather than replaying the full history.

## Export and import

Setup can export router configuration as JSON and import it later.

Provider credential **values are never included** in this export. The file contains normal router settings and a list of which credential keys are configured, not the secrets themselves.

## Update the local install

```bash
git pull
```

Then run your normal launcher again. Native mode detects dependency changes automatically; Docker mode rebuilds with the updated source.

## Troubleshooting native mode

Check whether another process already owns port 4010.

Windows:

```powershell
netstat -ano | findstr :4010
```

macOS/Linux:

```bash
lsof -i :4010
```

You can also start manually:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 4010
```

On Windows:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 4010
```

## Troubleshooting Docker mode

```bash
docker compose ps
docker compose logs -f router
```

If an individual provider is failing, use **Providers → Probe** or inspect **Usage & traces**. Model-level cooldowns prevent one failing model from unnecessarily disabling every model on the same provider.
