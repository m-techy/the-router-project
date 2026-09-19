# Upstream strategy

The Router is intentionally upstream-aware. Provider gateways repeatedly hit the same model-ID, header, quota, schema and retry problems, so we review proven fixes before inventing our own.

## Primary references

- **vava-nessa/free-coding-models** — primary discovery and live free-model intelligence source.
- **maximhq/bifrost** — Apache-2.0 data plane and optional transport.
- **BerriAI/litellm** — MIT core provider/proxy compatibility reference.
- **QuantumNous/new-api** — China-focused gateway reference; AGPL-3.0, reference-only by default.
- **songquanpeng/one-api** — MIT China-provider gateway reference.
- **DevvGwardo/free-llm-router** — free-capacity routing reference.
- **alienz-dev/llm-router** — health/circuit-breaker/probing reference.
- **spacepirate15/quantum-free-router** — certification lifecycle reference.
- **DeepakSilaych/free-api-gateway** — usage ledger/key-pool reference.

## Rules

1. Community catalogs are discovery sources, not billing authorities.
2. Verify recurring-free status before `persistent_free` activation.
3. Time-limited credits belong in `trial` or `promotional`.
4. Never evade provider quotas or terms.
5. Respect license boundaries.
6. Check watched upstreams before provider-specific workarounds.
