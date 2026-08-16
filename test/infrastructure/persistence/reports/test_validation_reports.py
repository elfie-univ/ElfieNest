import sqlite3
from pathlib import Path

import pytest

from infrastructure.persistence.layout.data_home import get_report_database_path
from infrastructure.persistence.report_storage import ReportStorageAdapter
from infrastructure.persistence.reports.validation_reports import (
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


def test_report_storage_adapter_keeps_injected_repository_as_fact_source(
    tmp_path: Path,
) -> None:
    repository = ReportRepository(tmp_path / "injected-report.sqlite")
    reports = ReportStorageAdapter(repository)

    reports.write_model_validation_report(
        "openai_api_0001",
        "injected-model",
        status="passed",
        checked_at="2026-07-29T01:02:03+00:00",
        latency_ms=5.0,
        latency_class="fast",
        error=None,
        trigger="full",
    )

    assert (
        reports.read_latest_model_validation("openai_api_0001", "injected-model")[
            "status"
        ]
        == "passed"
    )
    assert (tmp_path / "injected-report.sqlite").exists()


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
    historical = repository.as_of("2026-07-29T01:30:00+00:00", subject_kind="model")
    assert [(row.subject_id, row.status) for row in historical] == [
        ("anthropic_api_0001/claude-test", "passed"),
        ("openai_api_0001/gpt-test", "passed"),
    ]
    assert len(repository.observations_for_run(first_run)) == 2


def test_repository_normalizes_offsets_before_latest_and_as_of_queries(
    tmp_path: Path,
) -> None:
    repository = ReportRepository(tmp_path / "ai-runtime.sqlite")
    run_id = repository.start_run(
        scope="single_model",
        trigger="manual",
        started_at="2026-07-29T09:00:00+08:00",
    )
    repository.append_observation(
        run_id=run_id,
        subject_kind="model",
        subject_id="openai_api_0001/gpt-test",
        observed_at="2026-07-29T10:00:00+08:00",
        status="passed",
    )
    repository.append_observation(
        run_id=run_id,
        subject_kind="model",
        subject_id="openai_api_0001/gpt-test",
        observed_at="2026-07-29T03:00:00+00:00",
        status="failed",
    )

    latest = repository.latest("model", "openai_api_0001/gpt-test")
    historical = repository.as_of(
        "2026-07-29T02:30:00+00:00",
        subject_kind="model",
    )

    assert latest is not None
    assert latest.status == "failed"
    assert latest.observed_at == "2026-07-29T03:00:00+00:00"
    assert len(historical) == 1
    assert historical[0].status == "passed"
    assert historical[0].observed_at == "2026-07-29T02:00:00+00:00"


def test_finished_run_rejects_new_observations(tmp_path: Path) -> None:
    repository = ReportRepository(tmp_path / "ai-runtime.sqlite")
    run_id = repository.start_run(scope="single_model", trigger="manual")
    repository.finish_run(run_id, status="complete")

    with pytest.raises(ValueError, match="已经结束"):
        repository.append_observation(
            run_id=run_id,
            subject_kind="model",
            subject_id="openai_api_0001/gpt-test",
            status="passed",
        )


def test_validation_observations_are_sqlite_immutable(tmp_path: Path) -> None:
    database = tmp_path / "ai-runtime.sqlite"
    repository = ReportRepository(database)
    run_id = repository.start_run(scope="single_model", trigger="manual")
    observation_id = repository.append_observation(
        run_id=run_id,
        subject_kind="model",
        subject_id="openai_api_0001/gpt-test",
        status="passed",
    )

    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE validation_observations SET status = 'failed' "
                "WHERE observation_id = ?",
                (observation_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "DELETE FROM validation_observations WHERE observation_id = ?",
                (observation_id,),
            )


def test_retention_rolls_up_then_removes_only_finished_old_observations(
    tmp_path: Path,
) -> None:
    repository = ReportRepository(tmp_path / "retention.sqlite")
    old_run = repository.start_run(
        scope="single_model",
        trigger="scheduled",
        started_at="2026-07-01T00:00:00+00:00",
    )
    repository.append_observation(
        run_id=old_run,
        subject_kind="model",
        subject_id="cloud/main",
        observed_at="2026-07-01T01:00:00+00:00",
        status="passed",
        latency_ms=10.0,
    )
    repository.append_observation(
        run_id=old_run,
        subject_kind="model",
        subject_id="cloud/main",
        observed_at="2026-07-01T02:00:00+00:00",
        status="failed",
        latency_ms=30.0,
    )
    repository.finish_run(
        old_run,
        status="partial",
        finished_at="2026-07-01T03:00:00+00:00",
    )
    current_run = repository.start_run(
        scope="single_model",
        trigger="scheduled",
        started_at="2026-08-16T00:00:00+00:00",
    )
    repository.append_observation(
        run_id=current_run,
        subject_kind="model",
        subject_id="cloud/main",
        observed_at="2026-08-16T01:00:00+00:00",
        status="passed",
    )

    assert repository.compact_observations("2026-08-01T00:00:00+00:00") == 2
    rollups = repository.validation_rollups(subject_id="cloud/main")
    assert len(rollups) == 1
    assert rollups[0].observation_count == 2
    assert rollups[0].passed_count == 1
    assert rollups[0].failed_count == 1
    assert repository.latest("model", "cloud/main") is not None
    assert repository.latest("model", "cloud/main").observed_at == (
        "2026-08-16T01:00:00+00:00"
    )


def test_validation_lease_is_exclusive_and_expires(tmp_path: Path) -> None:
    repository = ReportRepository(tmp_path / "leases.sqlite")

    assert repository.try_acquire_validation_lease(
        "model:cloud/main:validation",
        "worker-a",
        lease_seconds=60,
        now="2026-08-16T00:00:00+00:00",
    )
    assert not repository.try_acquire_validation_lease(
        "model:cloud/main:validation",
        "worker-b",
        lease_seconds=60,
        now="2026-08-16T00:00:30+00:00",
    )
    assert repository.release_validation_lease(
        "model:cloud/main:validation", "worker-a"
    )
    assert repository.try_acquire_validation_lease(
        "model:cloud/main:validation",
        "worker-b",
        lease_seconds=60,
        now="2026-08-16T00:00:31+00:00",
    )

    assert not repository.try_acquire_validation_lease(
        "model:cloud/main:validation",
        "worker-a",
        lease_seconds=60,
        now="2026-08-16T00:00:45+00:00",
    )
    assert repository.try_acquire_validation_lease(
        "model:cloud/main:validation",
        "worker-a",
        lease_seconds=60,
        now="2026-08-16T00:02:00+00:00",
    )
def test_exports_and_legacy_reports_never_affect_queries(tmp_path: Path) -> None:
    database = tmp_path / "reports" / "ai-runtime.sqlite"
    repository = ReportRepository(database)
    run_id = repository.start_run(scope="single_model", trigger="manual")
    repository.append_observation(
        run_id=run_id,
        subject_kind="model",
        subject_id="openai_api_0001/gpt-test",
        status="passed",
        observed_at="2026-07-29T01:00:00+00:00",
    )
    export_directory = database.parent / "exports"
    export_directory.mkdir()
    (export_directory / "latest.yaml").write_text(
        "status: failed\nsubject_id: openai_api_0001/gpt-test\n",
        encoding="utf-8",
    )
    (tmp_path / "latest-report.yaml").write_text(
        "status: failed\nsubject_id: openai_api_0001/gpt-test\n",
        encoding="utf-8",
    )

    latest = repository.latest("model", "openai_api_0001/gpt-test")

    assert latest is not None
    assert latest.status == "passed"


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
