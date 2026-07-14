from types import SimpleNamespace

from elfie.brain.brain_types import BrainDecision
from elfie.elfie_individual import ElfieIndividual


class FoodRuntime:
    class Config:
        providers = {
            "ollama": {"api_key": ""},
            "cloud": {"api_key": "configured"},
        }

    config = Config()

    def run_with_food(self, **kwargs):  # pragma: no cover - capability marker
        raise AssertionError("brain method is replaced in this unit test")


def test_energy_cost_uses_actual_food_model_not_configured_provider_count(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    elfie = ElfieIndividual()
    consumed = []
    monkeypatch.setattr(
        elfie.hypothalamus,
        "consume_energy_by_action",
        consumed.append,
    )

    def local_decision(context, runtime):
        elfie.brain.last_runtime_result = SimpleNamespace(
            actual_model="ollama/local-model"
        )
        return BrainDecision(action="nod_head", speech_text="本地")

    monkeypatch.setattr(elfie.brain, "think_and_decide", local_decision)
    elfie.perceive_and_respond(
        {"has_new_message": True, "user_message": "第一条"}, FoodRuntime()
    )

    def cloud_decision(context, runtime):
        elfie.brain.last_runtime_result = SimpleNamespace(
            actual_model="cloud/remote-model"
        )
        return BrainDecision(action="nod_head", speech_text="云端")

    monkeypatch.setattr(elfie.brain, "think_and_decide", cloud_decision)
    elfie.perceive_and_respond(
        {"has_new_message": True, "user_message": "第二条"}, FoodRuntime()
    )

    assert consumed == [False, True]
