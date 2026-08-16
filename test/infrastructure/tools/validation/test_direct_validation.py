from infrastructure.models.validation.validation_models import CheckStatus
from infrastructure.persistence.configuration.bundled_defaults import load_tool_defaults
from infrastructure.tools.validation.direct_validation import DirectToolValidationRunner
from test.support.model_execution import model_execution_config


class FakeSearch:
    def search(self, query):
        return f"result for {query}"


def test_direct_tool_suite_validates_local_tools_and_skips_network(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    runner = DirectToolValidationRunner(
        model_execution_config(), tool_defaults=load_tool_defaults()
    )

    suite = runner.run()

    by_id = {result.check_id: result for result in suite.results}
    assert by_id["tool.local_file"].status is CheckStatus.PASSED
    assert by_id["tool.web_search"].status is CheckStatus.SKIPPED
    assert set(by_id) == {"tool.local_file", "tool.web_search"}
    assert suite.passed is True


def test_network_tool_can_be_verified_with_injected_search(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    runner = DirectToolValidationRunner(
        model_execution_config(), search_plugin=FakeSearch()
    )

    result = runner.verify_web_search()

    assert result.status is CheckStatus.PASSED
