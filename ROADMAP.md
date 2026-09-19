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
- [ ] native Gemini adapter fallback when OpenAI compatibility loses required functionality
- [ ] better Cloudflare neuron telemetry
- [x] automatic promotional expiry enforcement when upstream expiry metadata exists
- [x] provider/model change review screen in the dashboard

## v0.4 — more modalities
- [ ] /v1/embeddings
- [ ] /v1/audio/transcriptions
- [ ] multimodal request normalization tests
- [ ] image-generation capability registry
- [ ] task-aware virtual routes per modality

## v0.5 — platform UX
- [ ] encrypted local key vault option
- [ ] live event stream
- [ ] per-project local router keys and usage limits
- [ ] export/import config with secrets excluded by default
- [x] provider configuration writes through the local dashboard without exposing secrets

## v1.0
- [ ] one-command installers for Linux/macOS/Windows
- [ ] signed provider registry releases
- [ ] stable provider adapter SDK
- [ ] community contribution workflow for free-provider verification
- [ ] optional hosted control plane while preserving self-hosting
