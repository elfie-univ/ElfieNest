from ai_runtime.providers.model_hints import (
    ProviderModelSpec,
    configured_model_names,
    configured_model_specs,
    parse_model_input,
    suggested_model_names,
)


def test_parses_multiple_manual_model_ids_with_chinese_or_ascii_commas():
    assert parse_model_input("model-a， model-b,model-a") == ["model-a", "model-b"]


def test_suggests_official_xfyun_coding_plan_alias():
    assert suggested_model_names(
        "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2"
    ) == ["astron-code-latest"]


def test_placeholder_does_not_override_known_endpoint_suggestion():
    assert configured_model_names(
        {
            "api_base": "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2",
            "test_model": "custom-model",
        }
    ) == ["astron-code-latest"]


def test_reads_model_id_and_display_name_pairs():
    specs = configured_model_specs(
        {
            "models": [
                {"id": "odd-provider-id", "display_name": "GLM-5"},
                {"id": "another-id", "display_name": "Kimi K2"},
            ]
        }
    )

    assert [(item.model_id, item.display_name) for item in specs] == [
        ("odd-provider-id", "GLM-5"),
        ("another-id", "Kimi K2"),
    ]


def test_legacy_test_model_does_not_override_catalog_display_name():
    specs = configured_model_specs(
        {
            "models": [{"id": "xopglm5", "display_name": "GLM-5"}],
            "test_model": "xopglm5",
        }
    )

    assert specs == [ProviderModelSpec("xopglm5", "GLM-5")]


def test_official_model_id_corrects_an_incorrect_manual_display_name():
    specs = configured_model_specs(
        {
            "models": [
                {"id": "xopkimik25", "display_name": "MiniMax-M2.5"},
            ]
        }
    )

    assert specs == [ProviderModelSpec("xopkimik25", "Kimi-K2.5")]
