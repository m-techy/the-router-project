## What changed?

<!-- Describe the provider, adapter, registry, or routing change. -->

## Provider evidence checklist

If this PR changes `config/providers.yaml`:

- [ ] Official API docs are linked in `docs_url`.
- [ ] Free-tier recurrence is verified and accurately classified.
- [ ] Quota scope is recorded (key/account/project/organization/provider/IP).
- [ ] Exact reviewed model IDs are used.
- [ ] Promotional/trial capacity remains outside `free/*`.
- [ ] No secrets, account IDs, cookies, or credentials are committed.
- [ ] `python scripts/validate_registry.py` passes.
- [ ] New adapter behavior has focused tests.
- [ ] Existing upstream fixes/references were checked before adding custom behavior.

## Adapter SDK

If this PR adds a custom adapter:

- [ ] It targets `app.providers.sdk.SDK_VERSION`.
- [ ] Chat + streaming are implemented.
- [ ] Optional modalities are declared through `AdapterCapabilities`.
- [ ] The adapter never retries a partially-started stream on another provider.

## Test evidence

<!-- Paste commands/results, not credentials. -->
