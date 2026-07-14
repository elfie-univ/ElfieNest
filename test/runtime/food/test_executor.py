from runtime.config import LLMRuntimeConfig
from runtime.food.executor import FoodExecutor
from runtime.food.models import ExecutionProfile, FoodRecipe
from runtime.safety.permissions import PermissionManager
from runtime.tools.code import CodeSandboxPlugin
from runtime.tools.file import FileSandbox
from runtime.tools.local_files import LocalFileAccessPlugin
from runtime.tools.skills_evolution import SkillsSelfEvolutionPlugin


class NoopSearch:
    def search(self, query):
        return "result"


def make_executor(config, tmp_path, calls):
    permission = PermissionManager(config)

    def call(provider, model, messages, temperature, max_tokens, request_options):
        calls.append((provider, model, request_options))
        if model == "broken":
            raise RuntimeError("offline")
        return "ok"

    return FoodExecutor(
        config=config,
        search_plugin=NoopSearch(),
        sandbox_plugin=CodeSandboxPlugin(),
        skills_evolution_plugin=SkillsSelfEvolutionPlugin(
            permission, FileSandbox(tmp_path / "skills")
        ),
        permission_manager=permission,
        file_access_plugin=LocalFileAccessPlugin(tmp_path / "files"),
        model_caller=call,
    )


def test_food_executor_uses_technical_fallback_inside_same_food(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig()
    calls = []
    recipe = FoodRecipe(
        "standard",
        "标准粮",
        "默认",
        ExecutionProfile("ollama/broken"),
        technical_fallbacks=(ExecutionProfile("ollama/working"),),
    )

    result = make_executor(config, tmp_path, calls).execute(
        recipe, [{"role": "user", "content": "hello"}]
    )

    assert calls == [
        ("ollama", "broken", {}),
        ("ollama", "working", {}),
    ]
    assert result.model == "ollama/working"
    assert result.technical_fallback_used is True
    assert result.execution_stage == "fallback_1"


def test_food_executor_can_use_deep_profile_without_changing_food(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig()
    calls = []
    recipe = FoodRecipe(
        "standard",
        "标准粮",
        "默认",
        ExecutionProfile("ollama/normal"),
        deep=ExecutionProfile("ollama/deep"),
    )

    result = make_executor(config, tmp_path, calls).execute(
        recipe,
        [{"role": "user", "content": "hard question"}],
        prefer_deep=True,
    )

    assert calls == [("ollama", "deep", {})]
    assert result.execution_stage == "deep"
    assert result.technical_fallback_used is False
