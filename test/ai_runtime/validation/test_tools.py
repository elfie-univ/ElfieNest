from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.tools.file import FileSandbox
from ai_runtime.validation.models import CheckStatus
from ai_runtime.validation.tools import DirectToolValidationRunner


class FakeSearch:
    def search(self, query):
        return f"result for {query}"


def test_file_sandbox_uses_explicit_elfie_workspace(tmp_path):
    sandbox = FileSandbox(tmp_path / "elfies" / "00000042" / "skills")

    assert sandbox.skills_root == str(tmp_path / "elfies" / "00000042" / "skills")


def test_direct_tool_suite_validates_local_tools_and_skips_network(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    runner = DirectToolValidationRunner(LLMRuntimeConfig())

    suite = runner.run()

    by_id = {result.check_id: result for result in suite.results}
    assert by_id["tool.code_sandbox"].status is CheckStatus.SKIPPED
    assert by_id["tool.local_file"].status is CheckStatus.PASSED
    assert by_id["tool.permission_boundary"].status is CheckStatus.PASSED
    assert by_id["tool.skill_lifecycle"].status is CheckStatus.SKIPPED
    assert by_id["tool.web_search"].status is CheckStatus.SKIPPED
    assert suite.passed is True


def test_network_tool_can_be_verified_with_injected_search(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    runner = DirectToolValidationRunner(LLMRuntimeConfig(), search_plugin=FakeSearch())

    result = runner.verify_web_search()

    assert result.status is CheckStatus.PASSED
