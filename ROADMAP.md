# Roadmap

## v0.2 — foundation
- [x] OpenAI-compatible chat completions
- [x] recurring-free / promotional / trial isolation
- [x] capability-aware dynamic routing
- [x] pre-first-byte streaming fallback
- [x] SQLite request ledger and persistent quota/health reconstruction
- [x] provider response-header quota reconciliation
- [x] certification states and manual probes
- [x] dashboard + playground
- [x] no-key provider pools
- [x] upstream watchlist + scheduled change detection
- [x] optional Bifrost transport
- [x] China/APAC providers represented in the registry

## v0.3 — capacity, correctness, and usable platform
- [x] safe free-coding-models catalog parsing without executing upstream JavaScript
- [x] review-only reconciliation report for upstream additions/removals
- [x] first-run readiness/setup dashboard
- [x] copyable Python, JavaScript, and cURL client snippets
- [x] request trace view with fallback chain
- [x] provider signup/docs links in the dashboard
- [x] provider-specific /models discovery with zero-price filtering where pricing metadata exists
- [x] authoritative quota fetcher framework; OpenRouter active telemetry added, retired SiliconFlow endpoint intentionally excluded
- [x] model-level cooldown/health instead of provider-only runtime state
- [x] schema normalizers for known Z.AI/Mistral/NVIDIA/tool-call edge cases
- [x] native Gemini adapter fallback when OpenAI compatibility loses required functionality
- [x] Cloudflare free-allocation/reset metadata retained; live neuron balance intentionally not fabricated because no supported authoritative usage endpoint is documented
- [x] automatic promotional expiry enforcement when upstream expiry metadata exists
- [x] provider/model change review screen in the dashboard

## v0.4 — more modalities
- [x] /v1/embeddings
- [x] /v1/audio/transcriptions
- [x] multimodal request normalization tests
- [x] image-generation capability registry
- [x] task-aware virtual routes per modality

## v0.5 — platform UX
- [x] encrypted local key vault option
- [x] live event stream
- [x] per-project local router keys and usage limits
- [x] export/import config with secrets excluded by default
- [x] provider configuration writes through the local dashboard without exposing secrets

## v0.6 — distribution & ecosystem
- [x] one-command installers for Linux/macOS/Windows
- [x] cryptographically attested provider registry releases
- [x] stable provider adapter SDK v1
- [x] community contribution workflow for free-provider verification
- [x] registry validation enforced in CI

## v0.7 — hosted state foundation
- [x] selectable SQLite/PostgreSQL state backend
- [x] durable PostgreSQL usage, quota, health, settings, secrets, and project state
- [x] encrypted provider credentials on the hosted state backend
- [x] fail-closed hosted routing readiness checks
- [x] real PostgreSQL integration coverage in CI

## v0.8 — control plane + compatibility
- [x] System Doctor readiness/safety diagnostics
- [x] persistent custom `route/*` profiles with provider/context/fallback policy
- [x] stateless OpenAI Responses API compatibility
- [x] quota-aware `/v1/images/generations` with reviewed Cloudflare FLUX capacity
- [x] conservative Cloudflare daily-neuron accounting
- [x] streamed token accounting for provider quotas and project limits
- [x] session-only dashboard admin unlock
- [x] project-key-aware Playground and generated client snippets
- [x] dashboard interaction contract regression tests

## v0.9 — decision intelligence
- [ ] Jev typed decision-model integration spike via Vercel AI Gateway for routing and evaluation, not chat generation
- [ ] classify intent, modality, tool need, complexity, and escalation need in a single decision pass
- [ ] confidence-aware routing policy with deterministic fallback to the existing router when Jev is unavailable or below threshold
- [ ] post-response evaluator path for accept / retry / escalate decisions without exposing Jev as a user-facing model
- [ ] benchmark Jev against the current router for routing accuracy, latency, and cost before enabling it broadly
- [ ] keep Jev promotional/paid usage isolated from `free/auto`; never consume non-recurring-free capacity without explicit opt-in
- [ ] expose Jev decision traces and confidence in request diagnostics without leaking prompts, secrets, or provider credentials

## v1.0 — hosted without sacrificing self-hosting
- [ ] hosted control-plane UI while preserving the public project site
- [ ] hosted-safe live events / realtime usage updates
- [ ] connection pooling and operational telemetry guidance for sustained hosted load
- [ ] explicit hosted deployment smoke test against a production database integration
