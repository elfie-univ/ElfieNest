import json
import os

from infrastructure.models.validation.validation_models import (
    CheckResult,
    CheckStatus,
    ValidationReport,
    ValidationSuite,
)
from infrastructure.persistence.validation_artifacts import save_validation_report


def test_validation_report_summarizes_and_saves_without_secrets(tmp_path):
    suite = ValidationSuite(
        "provider:openai",
        (
            CheckResult(
                "provider.openai.health",
                CheckStatus.PASSED,
                "ok",
                provider="openai",
            ),
        ),
    )
    report = ValidationReport((suite,))

    path = save_validation_report(report, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["passed"] is True
    assert payload["suites"][0]["summary"]["passed"] == 1
    assert "api_key" not in path.read_text(encoding="utf-8")


def test_failed_check_marks_suite_and_report_failed():
    suite = ValidationSuite(
        "failed",
        (CheckResult("failure", CheckStatus.FAILED, "boom"),),
    )

    assert suite.passed is False
    assert ValidationReport((suite,)).passed is False


def test_validation_report_defaults_to_runtime_validation_directory(
    monkeypatch,
    tmp_path,
):
    # Given
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    report = ValidationReport(())

    # When
    path = save_validation_report(report)

    # Then
    assert path.parent == tmp_path / "reports" / "runtime-validations"
    if os.name != "nt":
        assert path.parent.stat().st_mode & 0o777 == 0o700
        assert path.stat().st_mode & 0o777 == 0o600
