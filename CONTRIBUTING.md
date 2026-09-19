# Contributing provider support

The Router separates **discovery**, **verification**, and **promotion**.

A provider can be interesting without being safe for `free/*`. Persistent-free routing is reserved for reviewed capacity that is recurring and can be verified from current provider evidence.

## Before opening a PR

1. Open a **Provider verification** issue when the provider or free tier is new.
2. Prefer official provider documentation for pricing, limits, model IDs, and API behavior.
3. Use community catalogs such as `free-coding-models` for discovery and live-change hints, not as the only source of truth.
4. Check `docs/UPSTREAMS.md` before implementing a provider quirk from scratch.
5. Never include credentials or private account details in issues, fixtures, logs, or screenshots.

## Registry changes

Run:

```bash
python scripts/validate_registry.py
pytest -q
```

The validator rejects stale candidate entries, duplicate provider/model IDs, insecure provider URLs, malformed persistent-free entries, and models with no routable capability.

Classification rules:

- `persistent_free`: recurring capacity safe for the default zero-cost pool.
- `promotional`: temporary, conditional, credit-backed, or otherwise opt-in.
- `trial`: expiring starter allocation.
- paid/unknown capacity must not silently enter normal routing.

## Adapter SDK

Import the supported development surface from:

```python
from app.providers.sdk import (
    SDK_VERSION,
    AdapterCapabilities,
    ProviderAdapter,
    ProviderError,
)
```

Every adapter implements `chat` and `stream`. Optional operations are advertised explicitly:

```python
class ExampleAdapter(ProviderAdapter):
    capabilities = AdapterCapabilities(
        embeddings=True,
        transcription=False,
    )
```

The router can register an adapter programmatically:

```python
router.register_adapter("example", ExampleAdapter(...))
```

Adapter names are stable registry identifiers. Do not overload an existing name with incompatible semantics.

## Promotion flow

Unknown upstream additions stay review-only until a maintainer verifies the free entitlement and model behavior. Discovery scripts never rewrite `providers.yaml` automatically.
