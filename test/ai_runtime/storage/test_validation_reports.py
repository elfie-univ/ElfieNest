from pathlib import Path

import pytest

from ai_runtime.storage.data_home import get_report_database_path
from ai_runtime.storage.validation_reports import (
    InvalidReportIdentityError,
    ReportRepository,
    read_latest_model_validation,
    read_latest_provider_validation,
    write_model_validation_report,
    write_provider_validation_report,
)


def test_provider_validation_is_appended_to_sqlite_without_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    observation_id = write_provider_validation_report(
        "openai_api_0001",
        status="failed",
        checked_at="2026-07-29T01:02:03+00:00",
        latency_ms=12.5,
        error="authentication rejected",
        trigger="single",
    )

    latest = read_latest_provider_validation("openai_api_0001")
    assert observation_id > 0
    assert latest == {
        "version": 1,
        "kind": "provider_validation",
        "provider_id": "openai_api_0001",
        "trigger": "single",
        "checked_at": "2026-07-29T01:02:03+00:00",
        "status": "failed",
        "latency_ms": 12.5,
        "error": "authentication rejected",
    }
    assert get_report_database_path().exists()
    assert list((tmp_path / "reports").glob("**/*.yaml")) == []


def test_model_validation_uses_connection_and_endpoint_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    write_model_validation_report(
        "openai_api_0001",
        "organization/model:latest",
        status="passed",
        checked_at="2026-07-29T01:02:03+00:00",
        latency_ms=22.0,
        latency_class="fast",
        error=None,
        trigger="benchmark",
    )

    assert read_latest_model_validation(
        "openai_api_0001", "organization/model:latest"
    ) == {
        "version": 1,
        "kind": "model_validation",
        "provider_id": "openai_api_0001",
        "model_id": "organization/model:latest",
        "trigger": "benchmark",
        "checked_at": "2026-07-29T01:02:03+00:00",
        "status": "passed",
        "latency_ms": 22.0,
        "latency_class": "fast",
        "error": None,
    }


def test_repository_projects_latest_as_of_and_complete_run(
    tmp_path: Path,
) -> None:
    repository = ReportRepository(tmp_path / "ai-runtime.sqlite")
    first_run = repository.start_run(
        scope="all_models",
        trigger="batch",
        started_at="2026-07-29T01:00:00+00:00",
    )
    repository.append_observation(
        run_id=first_run,
        subject_kind="model",
        subject_id="openai_api_0001/gpt-test",
        observed_at="2026-07-29T01:01:00+00:00",
        status="passed",
        latency_ms=10.0,
    )
    repository.append_observation(
        run_id=first_run,
        subject_kind="model",
        subject_id="anthropic_api_0001/claude-test",
        observed_at="2026-07-29T01:02:00+00:00",
        status="passed",
        latency_ms=20.0,
    )
    repository.finish_run(
        first_run,
        status="complete",
        finished_at="2026-07-29T01:03:00+00:00",
    )

    second_run = repository.start_run(
        scope="single_model",
        trigger="single",
        started_at="2026-07-29T02:00:00+00:00",
    )
    repository.append_observation(
        run_id=second_run,
        subject_kind="model",
        subject_id="openai_api_0001/gpt-test",
        observed_at="2026-07-29T02:01:00+00:00",
        status="failed",
        latency_ms=30.0,
        error_category="quota",
    )
    repository.finish_run(
        second_run,
        status="partial",
        finished_at="2026-07-29T02:02:00+00:00",
    )

    latest = repository.current(subject_kind="model")
    assert [(row.subject_id, row.status) for row in latest] == [
        ("anthropic_api_0001/claude-test", "passed"),
        ("openai_api_0001/gpt-test", "failed"),
    ]
    historical = repository.as_of(
        "2026-07-29T01:30:00+00:00", subject_kind="model"
    )
    assert [(row.subject_id, row.status) for row in historical] == [
        ("anthropic_api_0001/claude-test", "passed"),
        ("openai_api_0001/gpt-test", "passed"),
    ]
    assert len(repository.observations_for_run(first_run)) == 2


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
