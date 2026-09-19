# Provider registry releases

The reviewed provider registry is distributed as a deterministic release bundle rather than asking consumers to trust a mutable branch file.

## Bundle contents

`provider-registry.zip` contains:

- `providers.json` — canonical JSON generated from `config/providers.yaml`
- `manifest.json` — registry date, provider/model counts, source commit, and the provider JSON digest
- `providers.sha256` — SHA-256 checksum for `providers.json`

The zip itself is reproducible for the same registry content and source commit.

## Build locally

```bash
python scripts/validate_registry.py
python scripts/build_registry_release.py
```

Generated files live under `dist/` and are ignored by git.

## GitHub provenance attestation

The `Registry Release` workflow uses GitHub artifact attestations. GitHub signs the build provenance with a short-lived Sigstore-issued certificate and associates the attestation with this repository.

For tagged releases such as `registry-v0.6.0`, the workflow also publishes the bundle and manifest files as GitHub Release assets.

Verify a downloaded bundle with GitHub CLI:

```bash
gh attestation verify provider-registry.zip -R m-techy/the-router-project
```

This verifies the artifact's provenance and signer identity. It does not mean every upstream provider is trustworthy; it proves that the artifact came from this repository's release workflow.

## Verify bundle contents

After provenance verification:

```bash
unzip provider-registry.zip
sha256sum -c providers.sha256
```

On PowerShell:

```powershell
$expected = (Get-Content providers.sha256).Split(" ")[0]
$actual = (Get-FileHash providers.json -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $expected) { throw "Registry checksum mismatch" }
```

You can also compare `manifest.json.source_commit` with the repository commit associated with the release.

## Promotion policy

A signed/attested bundle proves provenance, not that a newly discovered model should be trusted automatically. Promotion into `free/*` still requires the contribution/verification checks in `CONTRIBUTING.md`.
