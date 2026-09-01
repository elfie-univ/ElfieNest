"""E1 vertical slice: a Genesis fact reaches one owner chat reply."""

from __future__ import annotations

from elfie import ElfieFactory
from elfie.body import HeadlessBody
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    StructuredOutputMode,
)
from elfie.communication import CommunicationHub
from elfie.factory import ElfieAssembly
from elfie.genesis import GenesisMemoryCommitter
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from test.elfie.genesis.test_contracts import _bundle
from test.elfie.test_cognitive_lifecycle import (
    CONSTITUTION,
    RecordingChannel,
    _owner_message,
    _selfhood_seed,
)


class StableOwnerReplyRuntime:
    def __init__(self) -> None:
        self.requests: list[ModelGenerationRequest] = []

    def capabilities(self) -> ModelGenerationCapabilities:
        return ModelGenerationCapabilities(
            provider="fake",
            model_key="e1-stable",
            supports_json_schema=True,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=256,
        )

    def abandon(self, request: ModelGenerationRequest) -> None:
        del request

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        self.requests.append(request)
        return ModelGenerationResult(
            text="我来自 Elfaria。",
            selected_mode=StructuredOutputMode.PLAIN_TEXT,
            provider="fake",
            model_key="e1-stable",
        )


class FailingOwnerReplyRuntime(StableOwnerReplyRuntime):
    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        del request
        raise RuntimeError("model unavailable")


def test_stage1_chat_reads_genesis_memory_and_delivers_one_reply() -> None:
    profile = create_visual_profile(
        elfie_id="genesis-check",
        display_name="Lumi",
        species_id="fox",
        seed=23,
    )
    store = SQLiteMemoryStoreAdapter.in_memory()
    GenesisMemoryCommitter().commit(_bundle(), store)
    body = HeadlessBody(body_id="e1-body")
    body.connect()
    hub = CommunicationHub("genesis-check")
    channel = RecordingChannel()
    hub.register_channel(channel, connect=True)
    runtime = StableOwnerReplyRuntime()
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=profile,
            selfhood_seed=_selfhood_seed("genesis-check", "Lumi"),
            reasoning_constitution=CONSTITUTION,
            memory_store=store,
            body=body,
            communication=hub,
            model_port=runtime,
        )
    )

    elfie.start()
    try:
        elfie.receive_communication_envelope(
            _owner_message(
                elfie.cognitive_datetime,
                event_id="e1-owner-1",
                conversation_id="owner-chat",
                text="你来自哪里？",
                elfie_id="genesis-check",
            )
        )
        elfie.advance_clock(0.5)
        elfie.wait_for_outcome_count(1, timeout=1.0)
        outcome = elfie.turn_outcomes()[0]
        elfie.wait_for_output(outcome.turn_id, timeout=1.0)

        assert len(runtime.requests) == 1
        assert "RELEVANT_MEMORY" in runtime.requests[0].user_prompt
        assert "genesis:knowledge:genesis-check:0" in runtime.requests[0].user_prompt
        assert "我来自 Elfaria。" in runtime.requests[0].user_prompt
        assert len(channel.sent) == 1
        assert channel.sent[0].parts[0].text == "我来自 Elfaria。"
    finally:
        elfie.stop()
        elfie.join()
        store.close()


def test_stage1_restart_keeps_genesis_fact_available(tmp_path) -> None:
    db_path = tmp_path / "knowledge.sqlite"
    with SQLiteMemoryStoreAdapter(db_path) as seed_store:
        GenesisMemoryCommitter().commit(_bundle(), seed_store)

    def create_runtime() -> tuple[object, RecordingChannel, object]:
        store = SQLiteMemoryStoreAdapter(db_path)
        body = HeadlessBody(body_id="e1-restart-body")
        body.connect()
        hub = CommunicationHub("genesis-check")
        channel = RecordingChannel()
        hub.register_channel(channel, connect=True)
        runtime = StableOwnerReplyRuntime()
        elfie = ElfieFactory().create(
            ElfieAssembly(
                profile=create_visual_profile(
                    elfie_id="genesis-check",
                    display_name="Lumi",
                    species_id="fox",
                    seed=23,
                ),
                selfhood_seed=_selfhood_seed("genesis-check", "Lumi"),
                reasoning_constitution=CONSTITUTION,
                memory_store=store,
                body=body,
                communication=hub,
                model_port=runtime,
            )
        )
        return elfie, channel, store

    first, _first_channel, first_store = create_runtime()
    first.start()
    first.receive_communication_envelope(
        _owner_message(
            first.cognitive_datetime,
            event_id="e1-restart-owner-1",
            conversation_id="owner-chat",
            text="你来自哪里？",
            elfie_id="genesis-check",
        )
    )
    first.advance_clock(0.5)
    first.wait_for_outcome_count(1, timeout=1.0)
    first.wait_for_output(first.turn_outcomes()[0].turn_id, timeout=1.0)
    first.stop()
    first.join()
    first_store.close()

    second, second_channel, second_store = create_runtime()
    second.start()
    second.receive_communication_envelope(
        _owner_message(
            second.cognitive_datetime,
            event_id="e1-restart-owner-2",
            conversation_id="owner-chat",
            text="你来自哪里？",
            elfie_id="genesis-check",
        )
    )
    second.advance_clock(0.5)
    second.wait_for_outcome_count(1, timeout=1.0)
    second.wait_for_output(second.turn_outcomes()[0].turn_id, timeout=1.0)

    assert len(second_channel.sent) == 1
    assert second_channel.sent[0].parts[0].text == "我来自 Elfaria。"

    second.stop()
    second.join()
    second_store.close()


def test_stage1_model_failure_delivers_truthful_short_failure_notice() -> None:
    profile = create_visual_profile(
        elfie_id="e1-model-failure",
        display_name="Lumi",
        species_id="fox",
        seed=23,
    )
    store = SQLiteMemoryStoreAdapter.in_memory()
    body = HeadlessBody(body_id="e1-failure-body")
    body.connect()
    hub = CommunicationHub("e1-model-failure")
    channel = RecordingChannel()
    hub.register_channel(channel, connect=True)
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=profile,
            selfhood_seed=_selfhood_seed("e1-model-failure", "Lumi"),
            reasoning_constitution=CONSTITUTION,
            memory_store=store,
            body=body,
            communication=hub,
            model_port=FailingOwnerReplyRuntime(),
        )
    )

    elfie.start()
    elfie.receive_communication_envelope(
        _owner_message(
            elfie.cognitive_datetime,
            event_id="e1-failing-owner-1",
            conversation_id="owner-chat",
            text="这个话题先这样",
            elfie_id="e1-model-failure",
        )
    )
    elfie.advance_clock(0.5)
    elfie.wait_for_outcome_count(1, timeout=1.0)
    outcome = elfie.turn_outcomes()[0]
    elfie.wait_for_output(outcome.turn_id, timeout=1.0)

    assert outcome.status.value == "failed"
    assert len(channel.sent) == 1
    assert channel.sent[0].parts[0].text == "我这次没能完成回复，请稍后再试。"

    # A host-generated failure notice is visible for continuity but must not
    # become a durable conversational fact that can pollute a later Recall.
    episodes = store.list_episodes()
    assert len(episodes) == 1
    assert "这个话题先这样" in episodes[0].content_text
    assert "我这次没能完成回复，请稍后再试。" not in episodes[0].content_text
    thread_messages = elfie.continuity_checkpoint().conversation.threads[0].messages
    assert [message.content for message in thread_messages] == [
        "这个话题先这样",
        "我这次没能完成回复，请稍后再试。",
    ]

    elfie.stop()
    elfie.join()
