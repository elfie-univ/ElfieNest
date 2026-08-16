from app.features.configuration.capabilities import StoredValidationResult
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.validation.validation_models import CheckResult, CheckStatus
from infrastructure.tools import DirectCapabilityValidationAdapter
from test.support.model_execution import model_execution_config


class FakeRunner:
    def __init__(self, config: ModelExecutionConfig) -> None:
        self.config = config

    def verify_web_search(self) -> CheckResult:
        return CheckResult(
            check_id="tool.web_search",
            status=CheckStatus.FAILED,
            message="search unavailable",
            details={"error_type": "SearchError", "private": "not-forwarded"},
        )

    def verify_file_sandbox(self) -> CheckResult:
        return CheckResult(
            check_id="tool.local_file",
            status=CheckStatus.PASSED,
            message="sandbox passed",
        )


def _factory(config: ModelExecutionConfig):
    return FakeRunner(config)


def test_validation_adapter_delegates_and_keeps_only_typed_details():
    adapter = DirectCapabilityValidationAdapter(
        config_loader=lambda: model_execution_config(),
        runner_factory=_factory,
    )

    result: StoredValidationResult = adapter.verify("web_search")

    assert result.status == "failed"
    assert result.error_type == "SearchError"
    assert "private" not in result.__dict__


def test_validation_adapter_uses_existing_file_sandbox_check():
    adapter = DirectCapabilityValidationAdapter(
        config_loader=lambda: model_execution_config(),
        runner_factory=_factory,
    )

    result = adapter.verify("local_file")

    assert result.status == "passed"
    assert result.check_id == "tool.local_file"
