"""OPT-002 deterministic continuous-learning replay through the real Brain path."""

from __future__ import annotations

from elfie import ElfieFactory
from elfie.body import HeadlessBody
from elfie.brain.memory import ConsolidationRequest, RecallRequest
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    StructuredOutputMode,
)
from elfie.communication import CommunicationHub
from elfie.factory import ElfieAssembly
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from test.elfie.test_cognitive_lifecycle import RecordingChannel, _owner_message


class StableReplyRuntime:
    def capabilities(self) -> ModelGenerationCapabilities:
        return ModelGenerationCapabilities(
            provider="fake",
            model_key="opt-002-stable",
            supports_json_schema=True,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=256,
        )

    def abandon(self, request: ModelGenerationRequest) -> None:
        del request

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        return ModelGenerationResult(
            text="我记住了。",
            selected_mode=StructuredOutputMode.PLAIN_TEXT,
            provider="fake",
            model_key="opt-002-stable",
        )


class NoopMemoryProjection:
    """Use the source-grounded deterministic extractor in this replay.

    The SQLite source-first worker deliberately requires an injected model
    boundary.  A valid empty proposal keeps this end-to-end test provider-free
    while exercising the same conservative fallback used by the evaluator.
    """

    def ask_with_food(self, **_kwargs: object) -> str:
        return '{"nodes":[],"mentions":[],"assertions":[]}'


def test_normal_chat_closes_captures_consolidates_and_recalls_after_restart(
    tmp_path,
) -> None:
    db_path = tmp_path / "knowledge.sqlite"

    def create():
        store = SQLiteMemoryStoreAdapter(db_path)
        body = HeadlessBody(body_id="opt-002-body")
        body.connect()
        hub = CommunicationHub("opt-002-elfie")
        channel = RecordingChannel()
        hub.register_channel(channel, connect=True)
        elfie = ElfieFactory().create(
            ElfieAssembly(
                profile=create_visual_profile(
                    elfie_id="opt-002-elfie",
                    display_name="Lumi",
                    species_id="fox",
                    seed=23,
                ),
                memory_store=store,
                body=body,
                communication=hub,
                model_port=StableReplyRuntime(),
            )
        )
        return elfie, store

    elfie, store = create()
    elfie.start()
    elfie.receive_communication_envelope(
        _owner_message(
            elfie.cognitive_datetime,
            event_id="opt-002-owner-1",
            text="我有个朋友叫小雨，小雨也叫雨宝。我喜欢蓝色。",
            elfie_id="opt-002-elfie",
        )
    )
    elfie.advance_clock(0.5)
    elfie.wait_for_outcome_count(1, timeout=1.0)
    elfie.wait_for_output(elfie.turn_outcomes()[0].turn_id, timeout=1.0)
    elfie.receive_communication_envelope(
        _owner_message(
            elfie.cognitive_datetime,
            event_id="opt-002-owner-2",
            text="换个话题，今天先这样。",
            elfie_id="opt-002-elfie",
        )
    )
    elfie.advance_clock(0.5)
    elfie.wait_for_outcome_count(2, timeout=1.0)
    elfie.wait_for_output(elfie.turn_outcomes()[1].turn_id, timeout=1.0)

    assert store.pending_episodes(limit=8)
    assert store.count_episodes() >= 1
    elfie._memory.run_consolidation_batch(  # noqa: SLF001 - deterministic replay seam
        ConsolidationRequest(max_episodes=8),
        model_port=NoopMemoryProjection(),
    )
    bundle = store.recall(RecallRequest(text="雨宝", episode_limit=8))
    assert any(item.episode_id.startswith("episode:topic:") for item in bundle.episodes)
    assert store.find_graph_nodes("雨宝")[0].label == "小雨"
    assert any(
        assertion.predicate == "likes"
        for assertion in store.graph_assertions_for(
            (store.find_graph_nodes("主人")[0].node_id,)
        )
    )
    elfie.stop()
    elfie.join()
    store.close()

    restarted, restarted_store = create()
    restarted_bundle = restarted_store.recall(
        RecallRequest(text="雨宝", episode_limit=8)
    )
    assert any(
        item.episode_id.startswith("episode:topic:")
        for item in restarted_bundle.episodes
    )
    restarted_store.close()
