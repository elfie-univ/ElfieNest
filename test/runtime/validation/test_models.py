import json

from runtime.validation.models import (
    CheckResult,
    CheckStatus,
    ValidationReport,
    ValidationSuite,
)


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

    path = report.save(tmp_path)
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
