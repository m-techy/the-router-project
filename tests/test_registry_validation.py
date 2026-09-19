from pathlib import Path

from scripts.validate_registry import validate_registry


def test_reviewed_registry_passes_contribution_validation():
    assert validate_registry() == []


def test_validator_rejects_stale_candidate(tmp_path):
    candidates = tmp_path / "candidates.yaml"
    candidates.write_text(
        """
updated_at: "2026-09-20"
candidates:
  - id: groq
    region: global
    status: review
    reason: already active
""".strip()
        + "\n",
        encoding="utf-8",
    )

    errors = validate_registry(
        Path("config/providers.yaml"),
        candidates,
    )
    assert any("already in providers.yaml" in error for error in errors)
