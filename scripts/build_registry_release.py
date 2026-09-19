#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "providers.yaml"
OUT_DIR = ROOT / "dist"
JSON_OUT = OUT_DIR / "providers.json"
MANIFEST_OUT = OUT_DIR / "manifest.json"
CHECKSUM_OUT = OUT_DIR / "providers.sha256"
BUNDLE_OUT = OUT_DIR / "provider-registry.zip"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build() -> dict[str, object]:
    raw = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    providers = raw.get("providers") or []
    payload = {
        "schema_version": 1,
        "updated_at": raw.get("updated_at"),
        "providers": providers,
    }
    provider_bytes = canonical_json(payload)
    provider_sha = sha256_bytes(provider_bytes)

    manifest = {
        "schema_version": 1,
        "registry_updated_at": raw.get("updated_at"),
        "provider_count": len(providers),
        "model_count": sum(len(provider.get("models") or []) for provider in providers),
        "providers_sha256": provider_sha,
        "source_repository": "m-techy/the-router-project",
        "source_commit": os.getenv("GITHUB_SHA") or os.getenv("ROUTER_SOURCE_COMMIT"),
    }
    manifest_bytes = canonical_json(manifest)
    checksum_bytes = f"{provider_sha}  providers.json\n".encode("utf-8")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_bytes(provider_bytes)
    MANIFEST_OUT.write_bytes(manifest_bytes)
    CHECKSUM_OUT.write_bytes(checksum_bytes)

    files = {
        "providers.json": provider_bytes,
        "manifest.json": manifest_bytes,
        "providers.sha256": checksum_bytes,
    }
    with zipfile.ZipFile(BUNDLE_OUT, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in sorted(files):
            info = zipfile.ZipInfo(filename=name, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, files[name])

    bundle_sha = sha256_bytes(BUNDLE_OUT.read_bytes())
    result = {
        **manifest,
        "bundle": str(BUNDLE_OUT.relative_to(ROOT)),
        "bundle_sha256": bundle_sha,
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    build()
