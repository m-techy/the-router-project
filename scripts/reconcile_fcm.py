#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.fcm_catalog import parse_fcm_sources, reconcile_catalog
from app.registry import ProviderRegistry

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "runtime" / "fcm-sources.js"
DEFAULT_OUT = ROOT / "runtime" / "fcm-reconciliation.json"
REGISTRY = ROOT / "config" / "providers.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare free-coding-models with The Router's reviewed provider registry."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.source.exists():
        raise SystemExit(
            f"{args.source} does not exist. Run: python scripts/fcm_discovery.py"
        )

    parsed = parse_fcm_sources(args.source.read_text(encoding="utf-8"))
    registry = ProviderRegistry(REGISTRY)
    reviewed = {
        provider.id: {model.id for model in provider.models if model.enabled and model.free}
        for provider in registry.providers
    }
    report = reconcile_catalog(parsed, reviewed)
    report["source"] = str(args.source)
    report["registry"] = str(REGISTRY)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {args.output}")
    print("Candidate additions are review-only. This script never edits providers.yaml.")


if __name__ == "__main__":
    main()
