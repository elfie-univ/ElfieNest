from pathlib import Path


def test_legacy_generation_fallback_modules_are_removed():
    project_root = Path(__file__).resolve().parents[3]
    assert not (project_root / "ai_runtime").exists()
