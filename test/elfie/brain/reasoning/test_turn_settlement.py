"""Turn settlement keeps context assembly read-only and commits owner candidates once."""

from datetime import datetime, timezone

from elfie.brain.activity.context import ActivityContextReader
from elfie.brain.consolidation.system import CognitiveConsolidationSystem
from elfie.brain.emotion.contracts import EmotionSnapshot, EmotionValue
from elfie.brain.memory import MemorySystem
from elfie.brain.motivation.system import MotivationSystem
from elfie.brain.orientation.system import OrientationSystem
from elfie.brain.reasoning.context_source import BrainContextProvider
from elfie.brain.reasoning.context_types import (
    EffectiveCapabilities,
)
from elfie.brain.reasoning.conversation_context import ConversationContextStore
from elfie.brain.reasoning.memory_context import MemoryContextReader
from elfie.brain.reasoning.settlement import TurnSettlement
from elfie.brain.selfhood.contracts import ProfileAnchorSnapshot
from elfie.brain.selfhood.system import SelfhoodSystem
from elfie.brain.state_lifecycle import StateCommitStatus
from elfie.brain.workspace.contracts import (
    CommunicationScope,
    ExternalExecutionDomain,
    PerceptionEvent,
    ResponseScope,
    SocialPayload,
    SourceDomain,
    TriggerReason,
    TurnFrame,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MessageMeta,
    TraceId,
    TurnId,
)
from test.elfie.brain.memory.fake_store import FakeMemoryStore

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def _frame() -> TurnFrame:
    owner = ActorRef(actor_id=ActorId("owner-1"), source_kind="owner")
    event = PerceptionEvent(
        meta=MessageMeta(
            event_id=EventId("message-1"),
            elfie_id=ElfieId("elfie-1"),
            source=owner,
            occurred_at=NOW,
            received_at=NOW,
            trace_id=TraceId("trace-1"),
        ),
        payload=SocialPayload(
            type="social",
            channel_id="chat",
            conversation_id="owner-chat",
            sender=owner,
            content="今晚提醒我带钥匙",
        ),
    )
    return TurnFrame(
        frame_id=EventId("frame-1"),
        elfie_id=ElfieId("elfie-1"),
        revision=1,
        captured_at=NOW,
        cutoff_seq=1,
        trigger_reason=TriggerReason.CONVERSATION_QUIET,
        source_domain=SourceDomain.COMMUNICATION,
        interaction_scope=CommunicationScope(
            channel_id="chat", conversation_id="owner-chat"
        ),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.COMMUNICATION,
            channel_id="chat",
            conversation_id="owner-chat",
        ),
        events=(event,),
    )


def test_context_read_does_not_write_memory_and_settlement_commits_once() -> None:
    memory = MemorySystem(
        FakeMemoryStore.in_memory(),
        elfie_id="elfie-1",
        initial_at=NOW,
        clock=lambda: NOW,
    )
    context = BrainContextProvider(
        memory=MemoryContextReader(memory),
        conversations=ConversationContextStore(),
        activities=ActivityContextReader(None),
        capability_reader=lambda captured_at, _authorized: EffectiveCapabilities(
            revision=0,
            captured_at=captured_at,
            current_body=None,
            connected_channels=(),
        ),
        clock=lambda: NOW,
        orientation=OrientationSystem(initial_at=NOW),
        selfhood=SelfhoodSystem(initial_at=NOW),
        motivation=MotivationSystem(initial_at=NOW),
        consolidation=CognitiveConsolidationSystem(
            pending_episode_ids=memory.pending_consolidation_ids,
            consolidate=lambda limit: memory.run_consolidation(max_episodes=limit),
            initial_at=NOW,
        ),
        profile_anchors=ProfileAnchorSnapshot.unknown().model_copy(
            update={"captured_at": NOW}
        ),
    )
    emotion = EmotionSnapshot(
        revision=1,
        captured_at=NOW,
        values=(EmotionValue(name="calm", intensity=0.2),),
        dominant="calm",
    )

    context.memory(_frame(), emotion, NOW)
    assert memory.revision == 0
    assert memory.storage.count_nodes("episodic") == 0

    candidates = context.memory_candidates(_frame(), emotion, NOW)
    receipts = TurnSettlement(memory).settle(candidates)
    duplicate = TurnSettlement(memory).settle(candidates)

    assert receipts[0].status is StateCommitStatus.COMMITTED
    assert duplicate[0].status is StateCommitStatus.DUPLICATE
    assert memory.revision == 1
    assert memory.storage.count_nodes("episodic") == 1


def test_orientation_candidate_is_visible_to_run_but_commits_only_at_settlement() -> (
    None
):
    memory = MemorySystem(
        FakeMemoryStore.in_memory(),
        elfie_id="elfie-1",
        initial_at=NOW,
        clock=lambda: NOW,
    )
    orientation = OrientationSystem(initial_at=NOW)
    context = BrainContextProvider(
        memory=MemoryContextReader(memory),
        conversations=ConversationContextStore(),
        activities=ActivityContextReader(None),
        capability_reader=lambda captured_at, _authorized: EffectiveCapabilities(
            revision=0,
            captured_at=captured_at,
            current_body=None,
            connected_channels=(),
        ),
        clock=lambda: NOW,
        orientation=orientation,
        selfhood=SelfhoodSystem(initial_at=NOW),
        motivation=MotivationSystem(initial_at=NOW),
        consolidation=CognitiveConsolidationSystem(
            pending_episode_ids=memory.pending_consolidation_ids,
            consolidate=lambda limit: memory.run_consolidation(max_episodes=limit),
            initial_at=NOW,
        ),
        profile_anchors=ProfileAnchorSnapshot.unknown().model_copy(
            update={"captured_at": NOW}
        ),
    )
    capabilities = context.capabilities(NOW)
    before = context.orientation_checkpoint()

    candidate = context.orientation_candidate(
        _frame(),
        NOW,
        TurnId("turn-orientation-1"),
        capabilities,
    )

    assert candidate.value.current_turn_id == "turn-orientation-1"
    assert context.orientation_checkpoint() == before

    receipts = TurnSettlement(
        memory,
        orientation=context.commit_orientation_candidate,
    ).settle((candidate,))

    assert receipts[0].status is StateCommitStatus.COMMITTED
    assert context.orientation_checkpoint().revision == before.revision + 1
    assert context.orientation_snapshot().current_turn_id == "turn-orientation-1"
