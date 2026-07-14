from runtime.config import LLMRuntimeConfig
from runtime.food.advisor import LLMFoodPlanningAdvisor, select_planning_model
from runtime.food.planner import ModelEvidence


def test_llm_advisor_sends_only_model_evidence_and_parses_json(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    captured = []

    def fake_call(config, provider, model, messages, temperature, max_tokens):
        captured.append(messages[0]["content"])
        return '```json\n{"standard":"cloud/balanced"}\n```'

    config = LLMRuntimeConfig()
    advisor = LLMFoodPlanningAdvisor(config, "cloud/planner", model_caller=fake_call)
    result = advisor.recommend(
        ["standard"],
        [ModelEvidence("cloud/balanced", frozenset({"text"}), True, latency_ms=200)],
    )

    assert result == {"standard": "cloud/balanced"}
    assert "api_key" not in captured[0]


def test_select_planning_model_requires_reasoning_and_configured_provider(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig()
    config.providers["cloud"] = {"api_key": "configured"}
    selected = select_planning_model(
        config,
        [
            ModelEvidence("cloud/plain", frozenset({"text"}), True),
            ModelEvidence(
                "cloud/reasoner",
                frozenset({"text", "reasoning"}),
                True,
                cost_grade=4,
            ),
        ],
    )

    assert selected == "cloud/reasoner"


def test_select_planning_model_falls_back_to_verified_text_model(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig()

    selected = select_planning_model(
        config,
        [ModelEvidence("ollama/gemma", frozenset({"text"}), True)],
    )

    assert selected == "ollama/gemma"
