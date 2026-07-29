from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.executor import FoodExecutor
from ai_runtime.food.models import ExecutionProfile, FoodRecipe
from ai_runtime.safety.permissions import PermissionManager
from ai_runtime.tools.code import CodeSandboxPlugin
from ai_runtime.tools.file import FileSandbox
from ai_runtime.tools.local_files import LocalFileAccessPlugin
from ai_runtime.tools.skills_evolution import SkillsSelfEvolutionPlugin


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


def test_food_executor_rejects_a_bare_model_reference(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    calls = []
    recipe = FoodRecipe("standard", "标准粮", "默认", ExecutionProfile("qwen2.5:0.5b"))

    try:
        make_executor(LLMRuntimeConfig(), tmp_path, calls).execute(
            recipe, [{"role": "user", "content": "hello"}]
        )
    except Exception as exc:
        assert "connection_id/model_id" in str(exc)
    else:
        raise AssertionError("裸模型名不得被默认解释为 Ollama")
    assert calls == []


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


def test_food_executor_treats_local_connection_instance_as_keyless(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig()
    config.providers["ollama_0001"] = {
        "api_mode": "ollama",
        "api_base": "http://localhost:11434",
        "api_key": "",
    }
    calls = []

    result = make_executor(config, tmp_path, calls).execute(
        FoodRecipe(
            "local",
            "本地粮",
            "本地",
            ExecutionProfile("ollama_0001/qwen3"),
        ),
        [{"role": "user", "content": "hello"}],
    )

    assert result.text == "ok"
    assert calls == [("ollama_0001", "qwen3", {})]


def test_food_executor_builds_multimodal_payload_for_selected_provider(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig()
    config.providers["cloud"] = {"api_key": "test-placeholder"}
    captured = []

    def call(provider, model, messages, temperature, max_tokens, request_options):
        captured.append(messages)
        return "看到了"

    permission = PermissionManager(config)
    executor = FoodExecutor(
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
    image = tmp_path / "image.png"
    image.write_bytes(b"image")

    result = executor.execute(
        FoodRecipe(
            "daily",
            "Daily",
            "test",
            ExecutionProfile("ollama/text-model"),
            vision=ExecutionProfile("cloud/vision-model"),
        ),
        [{"role": "user", "content": "这是什么？"}],
        prefer_vision=True,
        images=(str(image),),
    )

    assert result.text == "看到了"
    assert result.execution_stage == "vision"
    assert captured[0][0]["content"][1]["type"] == "image_url"
