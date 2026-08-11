"""Skill authorization integration with the typed cortical request boundary."""

from elfie import ElfieFactory
from elfie.body import HeadlessBody
from elfie.brain.skills import SkillManager, SkillPolicy
from elfie.communication import CommunicationHub
from test.elfie.test_cognitive_lifecycle import (
    RecordingChannel,
    TwoTurnRuntime,
    _owner_message,
)


def test_elfie_passes_authorized_tool_keys_to_cortical_request() -> None:
    manager = SkillManager(
        policy=SkillPolicy(allowed_skill_ids=frozenset({"web_search"}))
    )
    body = HeadlessBody(body_id="skills-body")
    hub = CommunicationHub("elfie-loop")
    hub.register_channel(RecordingChannel(), connect=True)
    runtime = TwoTurnRuntime()
    runtime.release_first.set()
    elfie = ElfieFactory().create(
        elfie_id="elfie-loop",
        memory_db_path=":memory:",
        body=body,
        communication=hub,
        skills=manager,
        model_port=runtime,
    )

    elfie.start()
    elfie.receive_communication_envelope(_owner_message(elfie.cognitive_datetime))
    elfie.advance_clock(0.5)
    elfie.wait_for_outcome_count(1, timeout=1.0)

    assert runtime.requests[0].allowed_tools == ("web_search",)
    elfie.stop()
    elfie.join()
