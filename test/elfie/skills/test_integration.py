from types import SimpleNamespace

from elfie import ElfieFactory
from elfie.skills import SkillManager, SkillPolicy


class RuntimeWithFood:
    class Config:
        providers = {"ollama": {"api_key": "", "api_base": "mock://local"}}

    config = Config()

    def __init__(self) -> None:
        self.allowed_skills = None

    def run_with_food(self, **kwargs):
        self.allowed_skills = kwargs["allowed_skills"]
        return SimpleNamespace(text="收到。[ACTION]nod_head[/ACTION]", actual_model="ollama/test")


def test_elfie_filters_brain_requested_tools_before_runtime_execution() -> None:
    elfie = ElfieFactory().create(
        elfie_id="elfie-skills",
        memory_db_path=":memory:",
        skills=SkillManager(
            policy=SkillPolicy(allowed_skill_ids=frozenset({"web_search"}))
        ),
    )
    runtime = RuntimeWithFood()

    result = elfie.perceive_and_respond(
        {
            "message_id": "message-1",
            "has_new_message": True,
            "user_message": "帮我搜索最新消息",
            "temperature": 24.0,
            "salience_score": 20.0,
        },
        runtime,
    )

    assert result["success"] is True
    assert runtime.allowed_skills == ["web_search"]
