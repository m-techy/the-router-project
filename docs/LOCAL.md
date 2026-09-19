# Run The Router locally

You do **not** need Vercel to use The Router.

Local/self-hosted mode is the primary runtime because it keeps provider credentials, quota state, health/cooldowns, and request traces on your machine.

> "Local" means the router runs on your computer. Cloud providers still require internet access. A future local-model adapter can provide fully air-gapped inference.

## Windows — easiest path

Prerequisite: install and start Docker Desktop.

Then either double-click:

```text
start.bat
```

or open PowerShell in the repository and run:

```powershell
.\start.bat
```

The script will:

1. verify Docker is available,
2. build the router image,
3. start it in the background,
4. wait for the health endpoint,
5. open `http://localhost:4010`.

## macOS / Linux

Prerequisite: Docker Desktop or Docker Engine.

```bash
sh start.sh
```

Or use Docker Compose directly:

```bash
docker compose up -d --build
```

Open:

```text
http://localhost:4010
```

## First-time setup

Open **Setup** in the sidebar.

You can begin even before adding every provider. Some pools support no-key or optional-key access.

For higher capacity:

1. add Groq,
2. add Gemini / Google AI Studio,
3. add Cerebras,
4. add OpenRouter,
5. add Mistral,
6. add Z.AI / SiliconFlow / NVIDIA and other available pools.

The Setup page links to supported provider signup/docs pages where they are known.

Environment variables still take precedence over values saved from the browser.

## Test the router

Open **Playground** and select:

```text
free/auto
```

Ask a short question.

Then open **Usage & traces** to see which provider/model actually handled it and whether any fallback occurred.

## Use it from a Python project

Install the OpenAI SDK in your hobby project:

```bash
pip install openai
```

Then:

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

## JavaScript / TypeScript

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

## Useful routes

- `free/auto` — balanced default
- `free/fast` — prioritize latency
- `free/smart` — prioritize model quality
- `free/code` — coding-capable models
- `free/reasoning` — reasoning-capable models
- `free/vision` — vision-capable models
- `free/long` — long-context models
- `promo/auto` — explicitly allow promotional providers
- `trial/auto` — explicitly allow trial/expiring providers

The `free/*` family does not silently opt into trial/promotional pools.

## Stop the router

```bash
docker compose down
```

Your SQLite state and locally saved credentials remain in the Docker volume.

To remove the persisted volume as well:

```bash
docker compose down -v
```

That deletes local router state and locally stored credentials.

## Update later

```bash
git pull
docker compose up -d --build
```

## Troubleshooting

Check container state:

```bash
docker compose ps
```

Check logs:

```bash
docker compose logs -f router
```

Check health:

```text
http://localhost:4010/health
```

If a provider is failing, use **Providers → Probe** or inspect **Usage & traces**. A failed model can cool down without disabling every other model on that provider.
