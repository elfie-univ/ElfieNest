from elfie import ElfieFactory
from elfie.brain.reasoning.skills import (
    BUILTIN_SKILLS,
    SkillDefinition,
    SkillManager,
    SkillPolicy,
)
from elfie.diagnostics import ElfieDiagnostics
from elfie.factory import ElfieAssembly
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.tools.execution.config import TOOL_KEYS


def test_builtin_skill_definitions_use_semantic_tool_keys() -> None:
    assert (
        tuple(tool_key for skill in BUILTIN_SKILLS for tool_key in skill.tool_keys)
        == TOOL_KEYS
    )
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
            tool_keys=("web_search",),
            display_name="Research assistant",
            description="A bounded search capability.",
        )
    )

    assert manager.authorize(["web_search", "code_sandbox"]) == ("web_search",)


def test_one_skill_can_authorize_multiple_tools() -> None:
    manager = SkillManager(
        policy=SkillPolicy(
            allowed_skill_ids=frozenset({"research_assistant"}),
        ),
        include_builtins=False,
    )
    manager.register(
        SkillDefinition(
            skill_id="research_assistant",
            tool_keys=("web_search", "local_file"),
            display_name="Research assistant",
            description="A bounded research capability.",
        )
    )

    assert tuple(skill.skill_id for skill in manager.allowed_skills()) == (
        "research_assistant",
    )
    assert manager.allowed_tool_keys() == ("web_search", "local_file")
    assert manager.authorize(["local_file", "web_search"]) == (
        "local_file",
        "web_search",
    )


def test_skill_policy_is_applied_before_tool_bindings_are_flattened() -> None:
    manager = SkillManager(
        policy=SkillPolicy(denied_skill_ids=frozenset({"blocked_skill"})),
        include_builtins=False,
    )
    manager.register(
        SkillDefinition(
            skill_id="allowed_skill",
            tool_keys=("web_search",),
            display_name="Allowed",
            description="Allowed capability.",
        )
    )
    manager.register(
        SkillDefinition(
            skill_id="blocked_skill",
            tool_keys=("web_search", "local_file"),
            display_name="Blocked",
            description="Blocked capability.",
        )
    )

    assert manager.allowed_tool_keys() == ("web_search",)
    snapshot = manager.snapshot()
    assert snapshot["skills"][0]["allowed"] is True
    assert snapshot["skills"][1]["allowed"] is False


def test_authorization_is_inert_when_no_tools_are_requested() -> None:
    manager = SkillManager()

    assert manager.authorize(None) == ()
    assert manager.authorize([]) == ()


def test_snapshot_exposes_domain_fields_without_runtime_proxy_state() -> None:
    snapshot = SkillManager(
        policy=SkillPolicy(allowed_skill_ids=frozenset({"web_search"}))
    ).snapshot()

    assert snapshot["allowed_tool_keys"] == ["web_search"]
    assert snapshot["skills"][0]["tool_keys"] == ("web_search",)
    assert set(snapshot["skills"][0]) >= {
        "skill_id",
        "tool_keys",
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

    assert ElfieDiagnostics(elfie).skills is manager
    assert ElfieDiagnostics(elfie).skills.allowed_tool_keys() == ("web_search",)
