from pathlib import Path

import pytest

from ai_runtime.storage.config_store import read_yaml_mapping
from ai_runtime.storage.validation_reports import (
    InvalidReportIdentityError,
    read_latest_provider_validation,
    write_model_validation_report,
    write_provider_validation_report,
)


def test_provider_validation_report_keeps_latest_and_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    history_path = write_provider_validation_report(
        "openai",
        status="failed",
        checked_at="2026-07-29T01:02:03+00:00",
        latency_ms=12.5,
        error="authentication rejected",
        trigger="single",
    )

    latest = read_latest_provider_validation("openai")
    assert latest == {
        "version": 1,
        "kind": "provider_validation",
        "provider_id": "openai",
        "trigger": "single",
        "checked_at": "2026-07-29T01:02:03+00:00",
        "status": "failed",
        "latency_ms": 12.5,
        "error": "authentication rejected",
    }
    assert history_path.parent.name == "history"
    assert read_yaml_mapping(history_path) == latest
    assert read_yaml_mapping(history_path.parent.parent / "latest.yaml") == latest
    assert oct(history_path.stat().st_mode & 0o777) == "0o600"


def test_model_validation_report_uses_opaque_model_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    history_path = write_model_validation_report(
        "openai",
        "organization/model:latest",
        status="passed",
        checked_at="2026-07-29T01:02:03+00:00",
        latency_ms=22.0,
        latency_class="fast",
        error=None,
        trigger="benchmark",
    )

    report = read_yaml_mapping(history_path)
    assert report["provider_id"] == "openai"
    assert report["model_id"] == "organization/model:latest"
    assert report["status"] == "passed"
    assert "/" not in history_path.parent.parent.name
    assert read_yaml_mapping(history_path.parent.parent / "latest.yaml") == report


@pytest.mark.parametrize("provider_id", ["../openai", "OPENAI", "openai-provider"])
def test_validation_report_rejects_unsafe_provider_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider_id: str
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    with pytest.raises(InvalidReportIdentityError):
        write_provider_validation_report(
            provider_id,
            status="passed",
            checked_at="2026-07-29T01:02:03+00:00",
            latency_ms=1.0,
            error=None,
            trigger="single",
        )
