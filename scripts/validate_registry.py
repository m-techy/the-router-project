#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

from app.registry import ProviderRegistry
from app.models import TierType

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "providers.yaml"
CANDIDATES = ROOT / "config" / "candidates.yaml"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _https_url(value: str | None, label: str, errors: list[str]) -> None:
    if not value:
        return
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append(f"{label} must be an absolute https URL: {value}")


def validate_registry(
    registry_path: Path = REGISTRY,
    candidates_path: Path = CANDIDATES,
) -> list[str]:
    errors: list[str] = []
    registry = ProviderRegistry(registry_path)

    try:
        dt.date.fromisoformat(registry.data.updated_at)
    except ValueError:
        errors.append("registry updated_at must be YYYY-MM-DD")

    provider_ids: set[str] = set()
    for provider in registry.providers:
        if provider.id in provider_ids:
            errors.append(f"duplicate provider id: {provider.id}")
        provider_ids.add(provider.id)

        if not SLUG_RE.fullmatch(provider.id):
            errors.append(f"provider id is not a lowercase slug: {provider.id}")

        _https_url(provider.base_url.replace("${CLOUDFLARE_ACCOUNT_ID}", "account"), f"{provider.id}.base_url", errors)
        _https_url(provider.docs_url, f"{provider.id}.docs_url", errors)
        _https_url(provider.signup_url, f"{provider.id}.signup_url", errors)

        if provider.tier == TierType.PERSISTENT_FREE:
            if not provider.verification:
                errors.append(f"{provider.id}: persistent-free provider needs verification evidence")
            if not provider.models:
                errors.append(f"{provider.id}: persistent-free provider needs at least one reviewed model")

        model_ids: set[str] = set()
        for model in provider.models:
            if model.id in model_ids:
                errors.append(f"{provider.id}: duplicate model id {model.id}")
            model_ids.add(model.id)

            caps = model.capabilities
            if not any(
                (
                    caps.chat,
                    caps.embeddings,
                    caps.transcription,
                    caps.image_generation,
                )
            ):
                errors.append(
                    f"{provider.id}/{model.id}: model has no routable capability"
                )
            if not model.free and provider.tier == TierType.PERSISTENT_FREE:
                errors.append(
                    f"{provider.id}/{model.id}: paid model must not live in persistent-free registry pool"
                )

    if candidates_path.exists():
        raw = yaml.safe_load(candidates_path.read_text(encoding="utf-8")) or {}
        candidates = raw.get("candidates") or []
        seen_candidates: set[str] = set()
        for item in candidates:
            candidate_id = str(item.get("id") or "")
            if not candidate_id:
                errors.append("candidate entry is missing id")
                continue
            if candidate_id in seen_candidates:
                errors.append(f"duplicate candidate id: {candidate_id}")
            seen_candidates.add(candidate_id)
            if candidate_id in provider_ids:
                errors.append(
                    f"candidate {candidate_id} is already in providers.yaml; remove stale candidate"
                )
            if not item.get("status"):
                errors.append(f"candidate {candidate_id} is missing status")
            if not item.get("reason"):
                errors.append(f"candidate {candidate_id} is missing review reason")

    return errors


def main() -> int:
    errors = validate_registry()
    if errors:
        print("Provider registry validation failed:", file=sys.stderr)
        for error in errors:
            print(f" - {error}", file=sys.stderr)
        return 1

    registry = ProviderRegistry(REGISTRY)
    model_count = sum(len(provider.models) for provider in registry.providers)
    print(
        f"Registry OK: {len(registry.providers)} providers, "
        f"{model_count} reviewed models, updated {registry.data.updated_at}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
