from __future__ import annotations

import re
from typing import Any

ARRAY_TO_PROVIDER = {
    "nvidiaNim": "nvidia",
    "groq": "groq",
    "cerebras": "cerebras",
    "sambanova": "sambanova",
    "openrouter": "openrouter",
    "mistral": "mistral",
    "codestral": "codestral",
    "scaleway": "scaleway",
    "googleai": "google",
    "zai": "zai",
    "qwen": "dashscope",
    "cloudflare": "cloudflare-ai",
    "ovhcloud": "ovhcloud",
    "opencodeZen": "opencode-zen",
    "kilo": "kilo",
    "llm7": "llm7",
    "routeway": "routeway",
    "ollamaCloud": "ollama-cloud",
    "siliconflow": "siliconflow",
    "requesty": "requesty",
    "orcarouter": "orcarouter",
    "vercelGateway": "vercel-ai-gateway",
    "pollinations": "pollinations",
}

EXPORT_RE = re.compile(r"^export const\s+(?P<name>[A-Za-z0-9_]+)\s*=\s*\[\s*$")
MODEL_RE = re.compile(
    r"""^\s*\[
    \s*['"](?P<id>[^'"]+)['"]\s*,
    \s*['"](?P<label>[^'"]+)['"]\s*,
    \s*['"](?P<tier>[^'"]+)['"]\s*,
    \s*['"](?P<score>[^'"]+)['"]\s*,
    \s*['"](?P<context>[^'"]+)['"]
    """,
    re.VERBOSE,
)


def parse_context(value: str) -> int | None:
    text = value.strip().lower()
    if not text or text == "-":
        return None
    multiplier = 1
    if text.endswith("k"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return None


def parse_score(value: str) -> float | None:
    text = value.strip().rstrip("%")
    if not text or text == "-":
        return None
    try:
        return float(text) / 100
    except ValueError:
        return None


def parse_fcm_sources(text: str) -> dict[str, list[dict[str, Any]]]:
    """Parse the upstream sources.js catalog without evaluating JavaScript."""
    parsed: dict[str, list[dict[str, Any]]] = {}
    current: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        export = EXPORT_RE.match(line)
        if export:
            symbol = export.group("name")
            current = ARRAY_TO_PROVIDER.get(symbol)
            if current:
                parsed.setdefault(current, [])
            continue

        if current and line.startswith("]"):
            current = None
            continue

        if not current or line.startswith("//"):
            continue

        match = MODEL_RE.match(raw_line)
        if not match:
            continue

        parsed[current].append(
            {
                "id": match.group("id"),
                "label": match.group("label"),
                "tier": match.group("tier"),
                "quality": parse_score(match.group("score")),
                "context": parse_context(match.group("context")),
            }
        )

    return parsed


def reconcile_catalog(
    parsed: dict[str, list[dict[str, Any]]],
    reviewed: dict[str, set[str]],
) -> dict[str, Any]:
    providers: dict[str, Any] = {}
    for provider_id in sorted(set(parsed) | set(reviewed)):
        upstream_models = {item["id"] for item in parsed.get(provider_id, [])}
        reviewed_models = reviewed.get(provider_id, set())
        providers[provider_id] = {
            "upstream_count": len(upstream_models),
            "reviewed_count": len(reviewed_models),
            "candidate_additions": sorted(upstream_models - reviewed_models),
            "missing_upstream": sorted(reviewed_models - upstream_models),
        }

    return {
        "providers": providers,
        "candidate_additions": sum(
            len(item["candidate_additions"]) for item in providers.values()
        ),
        "missing_upstream": sum(
            len(item["missing_upstream"]) for item in providers.values()
        ),
    }
