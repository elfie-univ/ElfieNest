"""Skill authorization integration with the typed reasoning request boundary."""

from elfie import ElfieFactory
from elfie.body import HeadlessBody
from elfie.brain.reasoning.skills import SkillManager, SkillPolicy
from elfie.communication import CommunicationHub
from elfie.factory import ElfieAssembly
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from test.elfie.test_cognitive_lifecycle import (
    CONSTITUTION,
    RecordingChannel,
    TwoTurnRuntime,
    _owner_message,
    _selfhood_seed,
)


def test_elfie_keeps_authorized_tools_out_of_fast_owner_conversation() -> None:
    manager = SkillManager(
        policy=SkillPolicy(allowed_skill_ids=frozenset({"web_search"}))
    )
    body = HeadlessBody(body_id="skills-body")
    hub = CommunicationHub("elfie-loop")
    hub.register_channel(RecordingChannel(), connect=True)
    runtime = TwoTurnRuntime()
    runtime.release_first.set()
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=create_visual_profile(
                elfie_id="elfie-loop",
                display_name="技能回路精灵",
                species_id="fox",
                seed=1,
            ),
            selfhood_seed=_selfhood_seed("elfie-loop", "技能回路精灵"),
            reasoning_constitution=CONSTITUTION,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            body=body,
            communication=hub,
            skills=manager,
            model_port=runtime,
        )
    )

    elfie.start()
    elfie.receive_communication_envelope(_owner_message(elfie.cognitive_datetime))
    elfie.advance_clock(0.5)
    elfie.wait_for_outcome_count(1, timeout=1.0)

    assert runtime.requests[0].reasoning_mode == "fast"
    assert runtime.requests[0].allowed_tools == ()
    elfie.stop()
    elfie.join()
