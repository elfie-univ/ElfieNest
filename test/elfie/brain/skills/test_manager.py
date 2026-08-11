from elfie import ElfieFactory
from elfie.brain.skills import (
    BUILTIN_SKILLS,
    SkillDefinition,
    SkillManager,
    SkillPolicy,
)
from elfie.factory import ElfieAssembly
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.tools.config import TOOL_KEYS


def test_builtin_skill_definitions_use_semantic_tool_keys() -> None:
    assert tuple(skill.tool_key for skill in BUILTIN_SKILLS) == TOOL_KEYS
    assert all("runtime" not in skill.description.lower() for skill in BUILTIN_SKILLS)


def test_manager_intersects_brain_request_with_elfie_policy() -> None:
    manager = SkillManager(
        policy=SkillPolicy(denied_skill_ids=frozenset({"code_sandbox"}))
    )

    allowed = manager.authorize(["web_search", "code_sandbox", "unknown", "web_search"])

    assert allowed == ("web_search",)


def test_manager_supports_custom_skill_mapped_to_semantic_tool_key() -> None:
    manager = SkillManager(include_builtins=False)
    manager.register(
        SkillDefinition(
            skill_id="research_assistant",
            tool_key="web_search",
            display_name="Research assistant",
            description="A bounded search capability.",
        )
    )

    assert manager.authorize(["web_search", "code_sandbox"]) == ("web_search",)


def test_authorization_is_inert_when_no_tools_are_requested() -> None:
    manager = SkillManager()

    assert manager.authorize(None) == ()
    assert manager.authorize([]) == ()


def test_snapshot_exposes_domain_fields_without_runtime_proxy_state() -> None:
    snapshot = SkillManager(
        policy=SkillPolicy(allowed_skill_ids=frozenset({"web_search"}))
    ).snapshot()

    assert snapshot["allowed_tool_keys"] == ["web_search"]
    assert snapshot["skills"][0]["tool_key"] == "web_search"
    assert set(snapshot["skills"][0]) >= {
        "skill_id",
        "tool_key",
        "display_name",
        "description",
        "allowed",
    }


def test_factory_injects_skill_manager_into_canonical_elfie() -> None:
    manager = SkillManager(
        policy=SkillPolicy(allowed_skill_ids=frozenset({"web_search"}))
    )

    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=create_visual_profile(
                elfie_id="elfie-skills",
                display_name="技能精灵",
                species_id="fox",
                seed=1,
            ),
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            skills=manager,
        )
    )

    assert elfie.skills is manager
    assert elfie.skills.allowed_tool_keys() == ("web_search",)
