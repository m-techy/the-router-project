#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import yaml

from app.discovery import model_entries

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "providers.yaml"
OUT = ROOT / "runtime" / "discovered-models.json"


def resolve(text: str) -> str:
    for key, value in os.environ.items():
        text = text.replace("${" + key + "}", value)
    return text


def main() -> None:
    cfg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    results: dict[str, dict] = {}

    for provider in cfg["providers"]:
        provider_id = provider["id"]
        base = resolve(provider["base_url"]).rstrip("/")
        if "${" in base:
            results[provider_id] = {
                "error": "unresolved base_url environment variable",
                "review_only": True,
            }
            continue

        env_key = provider.get("env_key")
        key = os.getenv(env_key or "")
        auth = provider.get("auth", "bearer")
        if auth == "bearer" and env_key and not key:
            results[provider_id] = {
                "error": f"missing {env_key}",
                "review_only": True,
            }
            continue

        headers = {
            "Accept": "application/json",
            "User-Agent": "the-router-model-discovery",
        }
        if key and auth in {"bearer", "optional_bearer"}:
            headers["Authorization"] = f"Bearer {key}"

        try:
            request = urllib.request.Request(base + "/models", headers=headers)
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
            entries = model_entries(payload)
            results[provider_id] = {
                "count": len(entries),
                "explicit_zero_price": [e["id"] for e in entries if e["zero_price"] is True],
                "explicit_paid": [e["id"] for e in entries if e["zero_price"] is False],
                "pricing_unknown": [e["id"] for e in entries if e["zero_price"] is None],
                "models": entries,
                "review_only": True,
            }
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            results[provider_id] = {"error": str(exc), "review_only": True}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    print("Discovery is review-only. Explicit zero price is evidence, not auto-promotion.")


if __name__ == "__main__":
    main()
