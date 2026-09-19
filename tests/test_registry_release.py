import hashlib
import json
import zipfile
from pathlib import Path

from scripts.build_registry_release import build


def test_registry_release_bundle_is_self_consistent(tmp_path, monkeypatch):
    import scripts.build_registry_release as release

    monkeypatch.setattr(release, "OUT_DIR", tmp_path)
    monkeypatch.setattr(release, "JSON_OUT", tmp_path / "providers.json")
    monkeypatch.setattr(release, "MANIFEST_OUT", tmp_path / "manifest.json")
    monkeypatch.setattr(release, "CHECKSUM_OUT", tmp_path / "providers.sha256")
    monkeypatch.setattr(release, "BUNDLE_OUT", tmp_path / "provider-registry.zip")
    monkeypatch.setenv("ROUTER_SOURCE_COMMIT", "abc123")

    result = build()

    provider_bytes = (tmp_path / "providers.json").read_bytes()
    expected = hashlib.sha256(provider_bytes).hexdigest()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert result["providers_sha256"] == expected
    assert manifest["providers_sha256"] == expected
    assert manifest["source_commit"] == "abc123"

    checksum = (tmp_path / "providers.sha256").read_text(encoding="utf-8")
    assert checksum == f"{expected}  providers.json\n"

    with zipfile.ZipFile(tmp_path / "provider-registry.zip") as bundle:
        assert sorted(bundle.namelist()) == [
            "manifest.json",
            "providers.json",
            "providers.sha256",
        ]
        assert bundle.read("providers.json") == provider_bytes


def test_registry_release_zip_is_reproducible(tmp_path, monkeypatch):
    import scripts.build_registry_release as release

    monkeypatch.setenv("ROUTER_SOURCE_COMMIT", "same-commit")

    def run(directory: Path) -> bytes:
        monkeypatch.setattr(release, "OUT_DIR", directory)
        monkeypatch.setattr(release, "JSON_OUT", directory / "providers.json")
        monkeypatch.setattr(release, "MANIFEST_OUT", directory / "manifest.json")
        monkeypatch.setattr(release, "CHECKSUM_OUT", directory / "providers.sha256")
        monkeypatch.setattr(release, "BUNDLE_OUT", directory / "provider-registry.zip")
        build()
        return (directory / "provider-registry.zip").read_bytes()

    assert run(tmp_path / "first") == run(tmp_path / "second")
