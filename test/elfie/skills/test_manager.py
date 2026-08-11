from elfie import ElfieFactory
from elfie.skills import (
    BUILTIN_SKILLS,
    SkillDefinition,
    SkillManager,
    SkillPolicy,
)
from infrastructure.tools.config import TOOL_KEYS


class CapturingRuntime:
    def __init__(self) -> None:
        self.calls = []

    def run_with_food(self, **kwargs):
        self.calls.append(kwargs)
        return "ok"

    def ask(self, *args, **kwargs):
        self.calls.append(kwargs)
        return "asked"


class LegacyRuntime:
    def ask(self, prompt, energy, task_complexity):
        return f"{prompt}:{energy}:{task_complexity}"


def test_builtin_skill_definitions_match_existing_runtime_tools() -> None:
    assert tuple(skill.runtime_tool for skill in BUILTIN_SKILLS) == TOOL_KEYS


def test_manager_intersects_brain_request_with_elfie_policy() -> None:
    manager = SkillManager(
        policy=SkillPolicy(denied_skill_ids=frozenset({"code_sandbox"}))
    )

    allowed = manager.filter_runtime_tools(
        ["web_search", "code_sandbox", "unknown", "web_search"]
    )

    assert allowed == ("web_search",)


def test_manager_supports_custom_skill_mapped_to_runtime_tool() -> None:
    manager = SkillManager(include_builtins=False)
    manager.register(
        SkillDefinition(
            skill_id="research_assistant",
            runtime_tool="web_search",
            display_name="资料助手",
            description="限定用途的搜索技能。",
        )
    )

    assert manager.filter_runtime_tools(["web_search", "code_sandbox"]) == (
        "web_search",
    )


def test_runtime_adapter_filters_existing_allowed_skills_argument() -> None:
    runtime = CapturingRuntime()
    manager = SkillManager(
        policy=SkillPolicy(allowed_skill_ids=frozenset({"local_file"}))
    )
    adapter = manager.wrap_runtime(runtime)

    result = adapter.run_with_food(
        prompt="读取资料",
        allowed_skills=["web_search", "local_file", "code_sandbox"],
    )

    assert result == "ok"
    assert runtime.calls[0]["allowed_skills"] == ["local_file"]


def test_runtime_adapter_preserves_none_as_no_tools_for_food_request() -> None:
    runtime = CapturingRuntime()
    adapter = SkillManager().wrap_runtime(runtime)

    adapter.run_with_food(prompt="普通请求", allowed_skills=None)

    assert runtime.calls[0]["allowed_skills"] == []


def test_runtime_ask_default_is_narrowed_to_elfie_policy() -> None:
    runtime = CapturingRuntime()
    manager = SkillManager(
        policy=SkillPolicy(allowed_skill_ids=frozenset({"web_search"}))
    )

    manager.wrap_runtime(runtime).ask("查询")

    assert runtime.calls[0]["allowed_skills"] == ["web_search"]


def test_runtime_adapter_keeps_legacy_mock_surface_unchanged() -> None:
    adapter = SkillManager().wrap_runtime(LegacyRuntime())

    assert not hasattr(adapter, "run_with_food")
    assert adapter.ask("你好", 80.0, 1) == "你好:80.0:1"


def test_factory_injects_skill_manager_into_canonical_elfie() -> None:
    manager = SkillManager(
        policy=SkillPolicy(allowed_skill_ids=frozenset({"web_search"}))
    )

    elfie = ElfieFactory().create(
        elfie_id="elfie-skills",
        memory_db_path=":memory:",
        skills=manager,
    )

    assert elfie.skills is manager
    assert elfie.skills.allowed_runtime_tools() == ("web_search",)
