from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.models import ExecutionProfile, FoodRecipe
from ai_runtime.food.planner import ModelEvidence
from ai_runtime.food.store import FoodCatalog
from ai_runtime.lab.cli import RuntimeLab
from ai_runtime.providers.model_hints import ProviderModelSpec
from ai_runtime.storage.config_store import read_yaml_mapping
from ai_runtime.storage.data_home import (
    get_config_path,
    get_env_path,
    get_food_catalog_path,
    get_provider_config_path,
)
from ai_runtime.validation.models import CheckResult, CheckStatus, ValidationSuite


def test_runtime_lab_direct_prompts_fail_closed_on_eof(tmp_path):
    def raise_eof(_prompt):
        raise EOFError

    lab = RuntimeLab(input_fn=raise_eof, output_fn=lambda _line: None)

    assert lab.input("确认") == ""


def test_runtime_lab_has_single_interactive_entry_and_can_exit(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    output = []
    answers = iter(["0"])
    lab = RuntimeLab(input_fn=lambda prompt: next(answers), output_fn=output.append)

    lab.run()

    rendered = "\n".join(output)
    assert "Provider 与原始模型" in rendered
    assert "运行总览与报告" in rendered
    assert "Agent 基础能力" in rendered
    assert "粮食策略" in rendered
    assert "已退出" in rendered


def test_food_update_requires_explicit_confirmation(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    from ai_runtime.food.evidence import ModelEvidenceStore
    from ai_runtime.food.planner import ModelEvidence

    ModelEvidenceStore().merge(
        [ModelEvidence("ollama/local", frozenset({"text"}), True, local=True)]
    )
    monkeypatch.setattr(
        "ai_runtime.lab.cli.select_planning_model", lambda config, items: None
    )
    output = []
    answers = iter(["2", "n", "0"])
    lab = RuntimeLab(input_fn=lambda prompt: next(answers), output_fn=output.append)

    lab.food_menu()

    assert not get_food_catalog_path().exists()
    assert "未应用更新。" in output
    assert any("计划修改" in line for line in output)
    assert any("未确认前不会写入" in line for line in output)


def test_food_model_collection_deduplicates_all_referenced_profiles(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    recipe = FoodRecipe(
        "standard",
        "标准粮",
        "",
        ExecutionProfile("cloud/main"),
        deep=ExecutionProfile("cloud/deep"),
        verifier=ExecutionProfile("cloud/main"),
        technical_fallbacks=(ExecutionProfile("ollama/local"),),
    )

    grouped = RuntimeLab._food_referenced_models(
        FoodCatalog(recipes={"standard": recipe})
    )

    assert grouped == {"cloud": ["main", "deep"], "ollama": ["local"]}


def test_food_validation_refreshes_referenced_model_before_catalog_check(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    from ai_runtime.food.store import FoodCatalogStore

    FoodCatalogStore().save(
        FoodCatalog(
            recipes={
                "standard": FoodRecipe(
                    "standard", "标准粮", "", ExecutionProfile("cloud/model-a")
                )
            }
        ),
        keep_history=False,
    )
    calls = []

    class FakeProviderRunner:
        def __init__(self, config):
            pass

        def verify_models(self, provider_id, model_names):
            calls.append((provider_id, model_names))
            return ValidationSuite(
                "provider:cloud",
                (
                    CheckResult(
                        "provider.cloud.model.model-a",
                        CheckStatus.PASSED,
                        "模型冒烟调用通过",
                        provider="cloud",
                        model="model-a",
                    ),
                ),
            )

    monkeypatch.setattr(
        "ai_runtime.lab.cli.ProviderValidationRunner", FakeProviderRunner
    )
    output = []
    lab = RuntimeLab(output_fn=output.append)
    monkeypatch.setattr(lab.menu, "confirm", lambda *args, **kwargs: True)

    lab._validate_foods(FoodCatalogStore())

    assert calls == [("cloud", ["model-a"])]
    evidence = ModelEvidenceStore().load()["cloud/model-a"]
    assert evidence.verified is True
    assert any(
        "food.standard.configuration: 标准粮配方验证通过" in line for line in output
    )


def test_food_update_reports_rule_generation_after_apply(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    from ai_runtime.food.evidence import ModelEvidenceStore
    from ai_runtime.food.planner import ModelEvidence

    ModelEvidenceStore().merge(
        [ModelEvidence("ollama/local", frozenset({"text"}), True, local=True)]
    )
    monkeypatch.setattr(
        "ai_runtime.lab.cli.select_planning_model", lambda config, items: None
    )
    output = []
    answers = iter(["2", "y", "0"])
    lab = RuntimeLab(input_fn=lambda prompt: next(answers), output_fn=output.append)

    lab.food_menu()

    assert get_food_catalog_path().exists()
    assert "本次粮食策略由确定性规则生成。" in output
    assert any("主模型:" in line for line in output)


def test_provider_menu_lists_only_configured_providers(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    output = []
    answers = iter(["0"])
    lab = RuntimeLab(input_fn=lambda prompt: next(answers), output_fn=output.append)

    lab.provider_menu()

    rendered = "\n".join(output)
    assert "ollama" in rendered
    assert "openai" not in rendered
    assert "添加或配置其他 Provider" in rendered


def test_interactive_menu_enters_child_and_returns_with_arrows(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    keys = iter(["down", "right", "left", "left"])
    lab = RuntimeLab(
        interactive=True,
        key_reader=lambda: next(keys),
        output_fn=lambda message: None,
    )

    lab.run()


def test_provider_edit_escape_does_not_persist_partial_changes(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    lab = RuntimeLab(
        input_fn=lambda prompt: "\x1b",
        secret_input_fn=lambda prompt: "unexpected",
        output_fn=lambda message: None,
    )
    original_base = lab.config.providers["ollama"]["api_base"]

    changed = lab._configure_provider("ollama")

    assert changed is False
    assert lab.config.providers["ollama"]["api_base"] == original_base
    assert not get_config_path().exists()
    assert not get_env_path().exists()


def test_provider_edit_escape_at_secret_discards_changed_base(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    lab = RuntimeLab(
        input_fn=lambda prompt: "https://changed.example/v1",
        secret_input_fn=lambda prompt: "\x1b",
        output_fn=lambda message: None,
    )
    original_base = lab.config.providers["openai"]["api_base"]

    changed = lab._configure_provider("openai")

    assert changed is False
    assert lab.config.providers["openai"]["api_base"] == original_base
    assert not get_config_path().exists()
    assert not get_env_path().exists()


def test_explicit_runtime_lab_home_keeps_single_file_development_format(
    monkeypatch,
    tmp_path,
) -> None:
    production_home = tmp_path / "production"
    development_home = tmp_path / "development"
    monkeypatch.setenv("ELFIE_HOME", str(production_home))
    lab = RuntimeLab(
        config_home=development_home,
        output_fn=lambda message: None,
    )
    provider = {
        "api_base": "https://development.example/v1",
        "api_mode": "chat_completions",
        "auth_type": "bearer",
    }

    lab._commit_provider("custom_development", provider, "development-secret")

    saved = read_yaml_mapping(development_home / "config.yaml")
    assert saved["providers"]["custom_development"]["api_base"].endswith("/v1")
    assert lab.config.config_home == str(development_home)
    assert "custom_development" in lab.config.providers
    assert "CUSTOM_DEVELOPMENT_API_KEY=development-secret" in (
        development_home / ".env"
    ).read_text(encoding="utf-8")
    assert lab._food_store().path == development_home / "foods.yaml"
    assert not production_home.exists()


def test_multiple_named_custom_providers_can_be_created(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    answers = iter(
        [
            "My Gateway",
            "https://one.example/v1",
            "My Gateway",
            "https://two.example/v1",
        ]
    )
    secrets = iter(["first-secret", "second-secret"])
    lab = RuntimeLab(
        input_fn=lambda prompt: next(answers),
        secret_input_fn=lambda prompt: next(secrets),
        output_fn=lambda message: None,
    )
    monkeypatch.setattr(
        lab,
        "_auto_discover_model_specs",
        lambda provider_id, provider: [
            ProviderModelSpec(
                "model-one" if "one.example" in provider["api_base"] else "model-two",
                "Model One" if "one.example" in provider["api_base"] else "Model Two",
            )
        ],
    )

    assert lab._create_custom_provider() is True
    assert lab._create_custom_provider() is True

    providers = read_yaml_mapping(get_provider_config_path())["providers"]
    assert providers["custom_my_gateway"]["display_name"] == "My Gateway"
    assert providers["custom_my_gateway_2"]["display_name"] == "My Gateway"
    assert providers["custom_my_gateway"]["models"] == [
        {"id": "model-one", "display_name": "Model One"}
    ]
    assert providers["custom_my_gateway"]["api_key_env"] == (
        "CUSTOM_MY_GATEWAY_API_KEY"
    )
    assert "api_key" not in providers["custom_my_gateway"]
    env_text = get_env_path().read_text(encoding="utf-8")
    assert "CUSTOM_MY_GATEWAY_API_KEY=first-secret" in env_text
    assert "CUSTOM_MY_GATEWAY_2_API_KEY=second-secret" in env_text


def test_custom_provider_escape_at_secret_prompt_creates_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    answers = iter(["Cancelled Gateway", "https://example.test/v1"])
    lab = RuntimeLab(
        input_fn=lambda prompt: next(answers),
        secret_input_fn=lambda prompt: "\x1b",
        output_fn=lambda message: None,
    )

    created = lab._create_custom_provider()

    assert created is False
    assert not get_config_path().exists()
    assert not get_env_path().exists()


def test_new_provider_falls_back_to_required_manual_id_and_display_name(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    answers = iter(
        [
            "XFYun Coding",
            "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2",
            "astron-code-latest",
            "GLM-5",
            "n",
        ]
    )
    lab = RuntimeLab(
        input_fn=lambda prompt: next(answers),
        secret_input_fn=lambda prompt: "<test-api-key>",
        output_fn=lambda message: None,
    )
    monkeypatch.setattr(
        lab,
        "_auto_discover_model_specs",
        lambda provider_id, provider: (_ for _ in ()).throw(RuntimeError("no /models")),
    )

    assert lab._create_custom_provider() is True

    provider = read_yaml_mapping(get_provider_config_path())["providers"][
        "custom_xfyun_coding"
    ]
    assert provider["models"] == [{"id": "astron-code-latest", "display_name": "GLM-5"}]


def test_provider_modify_keeps_existing_manual_models_when_refresh_fails(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    answers = iter(["", "", "n"])
    lab = RuntimeLab(
        input_fn=lambda prompt: next(answers),
        secret_input_fn=lambda prompt: "",
        output_fn=lambda message: None,
    )
    lab.config.providers["custom_gateway"] = {
        "display_name": "Gateway",
        "api_base": "https://gateway.example/v1",
        "api_mode": "chat_completions",
        "auth_type": "none",
        "status": "active",
        "models": [{"id": "odd-id", "display_name": "GLM-5"}],
    }
    monkeypatch.setattr(
        lab,
        "_auto_discover_model_specs",
        lambda provider_id, provider: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    assert lab._configure_provider("custom_gateway") is True

    provider = read_yaml_mapping(get_provider_config_path())["providers"][
        "custom_gateway"
    ]
    assert provider["models"] == [{"id": "odd-id", "display_name": "GLM-5"}]


def test_model_agent_validation_can_run_all_verified_models(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    ModelEvidenceStore().merge(
        [
            ModelEvidence(
                "ollama/local",
                frozenset({"text"}),
                True,
                display_name="Local",
                local=True,
            ),
            ModelEvidence(
                "cloud/remote",
                frozenset({"text"}),
                True,
                display_name="Remote",
            ),
        ]
    )
    calls = []

    class FakeRunner:
        def __init__(self, config):
            self.config = config

        def verify(self, provider, model):
            calls.append((provider, model))
            return ValidationSuite(
                f"agent:{provider}/{model}",
                (
                    CheckResult(
                        f"agent.{provider}.{model}.local_file",
                        CheckStatus.PASSED,
                        "ok",
                        provider=provider,
                        model=model,
                    ),
                ),
            )

    monkeypatch.setattr("ai_runtime.lab.cli.ModelAgentValidationRunner", FakeRunner)
    output = []
    answers = iter(["1", "y"])
    lab = RuntimeLab(input_fn=lambda prompt: next(answers), output_fn=output.append)

    lab._verify_model_agent()

    assert set(calls) == {("ollama", "local"), ("cloud", "remote")}
    evidence = ModelEvidenceStore().load()
    assert evidence["ollama/local"].tool_test_passed is True
    assert evidence["cloud/remote"].tool_test_passed is True
    assert any("通过 2 / 2" in line for line in output)
