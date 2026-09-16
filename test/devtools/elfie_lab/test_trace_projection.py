from datetime import datetime, timezone
from typing import Any, Optional

from devtools.elfie_lab.trace_projection import build_observability_trace
from elfie.brain.activity.observation_payloads import (
    ActivityPreflightVerdictObservation,
)
from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.energy.contracts import EnergySnapshot
from elfie.brain.memory.observation_payloads import (
    MemoryEncodeCandidate,
    MemoryEncodeCommit,
    MemoryReinforcementApplied,
    MemoryUseProposalRecorded,
)
from elfie.brain.motivation.contracts import MotivationSnapshot
from elfie.brain.observation import BrainObservation, ObservationStatus
from elfie.brain.orientation.contracts import OrientationSnapshot
from elfie.brain.reasoning.agent_loop_observations import (
    AgentLoopActionObservation,
    AgentLoopJudgeObservation,
    AgentLoopObservationRecorded,
    ModelCallObservation,
)
from elfie.brain.reasoning.coordinator_observations import (
    CognitiveBudgetReleasedObservation,
    CognitiveBudgetSettledObservation,
    DecisionRoutedObservation,
    EmotionCandidateObservation,
    EmotionDimensionChangeObservation,
    EnergyBudgetStateObservation,
    EventSalienceObservation,
    WorkspaceFrameAdmissionObservation,
)
from elfie.brain.reasoning.observation_payloads import (
    CompiledContextObservation,
    CompiledConversationObservation,
    MemoryRecallBundleObservation,
    MemoryRecallResultObservation,
    MemoryStateObservation,
    MemoryTurnOpened,
)
from elfie.brain.reasoning.run_controller_observations import (
    CognitiveBudgetReservedObservation,
    ContextTrimObservation,
    ConversationAppendedObservation,
    ConversationSummaryCoverageObservation,
    ReasoningBudgetFrozenObservation,
    ReasoningContextFrozenObservation,
    ReasoningModeSelectedObservation,
    SelfhoodProjectionObservation,
)
from elfie.brain.selfhood.contracts import SelfhoodPromptProjection


def test_memory_projection_is_rebuilt_from_raw_observation_events():
    observations = [
        _bridge_observation(
            kind="turn_opened",
            payload=MemoryTurnOpened(
                frame_id="frame-1",
                query="你还记得吗？",
                pinned_revision=42,
                state=MemoryStateObservation(
                    revision=42,
                    episodic_count=1,
                    total_count=2,
                    snapshot_freshness="fresh",
                ),
            ),
        ),
        _bridge_observation(
            kind="recall_result",
            payload=MemoryRecallResultObservation(
                frame_id="frame-1",
                query="你还记得吗？",
                status="recalled",
                pinned_revision=42,
                bundle=MemoryRecallBundleObservation(
                    recall_revision=42,
                    focus_node_ids=("node:1",),
                    assertion_ids=("assertion:memory-1",),
                    episode_ids=("episode:1",),
                    evidence_ids=("evidence:1",),
                    path_count=1,
                    conflict_count=0,
                ),
            ),
        ),
        _bridge_observation(
            kind="recall_result",
            payload=MemoryRecallResultObservation(
                frame_id="frame-1",
                query="上次聊了什么",
                status="recalled",
                pinned_revision=42,
                bundle=MemoryRecallBundleObservation(
                    recall_revision=42,
                    assertion_ids=("assertion:memory-2",),
                ),
            ),
        ),
        _observation(
            boundary="memory.encode",
            kind="use_proposal_recorded",
            frame_id="",
            payload=MemoryUseProposalRecorded(
                proposal_id="prop-1",
                target_kind="assertion",
                target_ids=("assertion:memory-1",),
                recall_revision=42,
                accepted=True,
            ),
        ),
    ]

    trace = build_observability_trace(
        turn_id="turn-1",
        stimulus={"source_domain": "communication", "message": "你还记得吗？"},
        state_before={"energy": 90},
        state_after={},
        state_diff={},
        raw_stages={"reasoning": {}},
        result={},
        decision={},
        duration_ms=12,
        observations=[
            _model_call_observation(context_revision=7),
            *observations,
        ],
    )

    memory = trace["memory"]
    assert memory["status"] == "recalled"
    assert memory["query"] == "你还记得吗？"
    assert memory["revision"] == 42
    assert memory["returned_points"] == [
        {"kind": "focus_node", "id": "node:1", "evidence": "node:1"},
        {
            "kind": "assertion",
            "id": "assertion:memory-1",
            "evidence": "assertion:memory-1",
        },
        {"kind": "episode", "id": "episode:1", "evidence": "episode:1"},
        {"kind": "evidence", "id": "evidence:1", "evidence": "evidence:1"},
    ]
    assert memory["selected"] == [
        {
            "proposal_id": "prop-1",
            "target_kind": "assertion",
            "target_ids": ["assertion:memory-1"],
            "recall_revision": 42,
            "accepted": True,
            "reason": None,
        }
    ]
    assert len(memory["on_demand"]) == 1
    on_demand = memory["on_demand"][0]
    assert on_demand["status"] == "recalled"
    assert on_demand["query"] == "上次聊了什么"
    assert on_demand["revision"] == 42
    assert on_demand["returned_points"] == [
        {
            "kind": "assertion",
            "id": "assertion:memory-2",
            "evidence": "assertion:memory-2",
        }
    ]
    assert memory["raw"]["baseline"]["kind"] == "recall_result"
    assert memory["raw"]["turn_opened"]["kind"] == "turn_opened"

    baseline = trace["chain"][2]["baseline_memory"]
    assert baseline["status"] == "recalled"
    assert baseline["revision"] == 42
    assert baseline["returned_points"] == memory["returned_points"]
    assert baseline["evidence_basis"] == "brain_observations.reasoning.memory_bridge"

    assert trace["chain"][1]["output"]["context_revision"] == 7


def test_context_view_comes_from_compiled_context_observations():
    compiled = CompiledContextObservation(
        turn_id="turn-1",
        frame_id="frame-1",
        context_revision=7,
        capability_revision=3,
        memory_recall_revision=42,
        max_tokens=1536,
        reasoning_mode="long",
        response_mode="structured",
        system_prompt="COMPILED SYSTEM",
        user_prompt="COMPILED USER",
        event_count=3,
        conversation_count=4,
        summary_count=1,
        run_observation_count=2,
        memory_chars=512,
        memory_estimated_tokens=128,
        truncated=False,
    )
    trace = build_observability_trace(
        turn_id="turn-1",
        stimulus={"source_domain": "communication", "message": "你还记得吗？"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={
            "reasoning": {"status": "completed", "model_calls": 1, "steps": []}
        },
        result={},
        decision={},
        duration_ms=12,
        observations=[
            _model_call_observation(context_revision=7, user_prompt="PROMPT"),
            _observation(
                boundary="reasoning.context_engine",
                kind="compiled_context",
                turn_id="turn-1",
                payload=compiled,
            ),
        ],
    )

    context_stage = trace["chain"][1]
    assert context_stage["status"] == "completed"
    assert "compiled" not in context_stage["output"]
    assert context_stage["raw"]["compiled_events"][0]["kind"] == "compiled_context"
    assert context_stage["raw"]["user_prompt"] == "PROMPT"
    assert context_stage["output"]["conversation"] == []
    assert context_stage["output"]["current_observations"] is None
    assert context_stage["output"]["current_run_observations"] is None
    iteration = trace["chain"][3]["iterations"][0]
    compiled_output = iteration["context_build"]["output"]["compiled"]
    assert compiled_output["run_observation_count"] == 2
    assert iteration["context_build"]["output"]["system_prompt"] == "COMPILED SYSTEM"
    assert iteration["context_build"]["output"]["user_prompt"] == "COMPILED USER"
    build_output = iteration["context_build"]["output"]
    assert "conversation" not in build_output
    assert "prompt_sections" not in build_output


def test_context_workspace_conversation_is_rebuilt_from_envelope_rows():
    occurred_at = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    compiled = CompiledContextObservation(
        turn_id="turn-1",
        frame_id="frame-1",
        context_revision=7,
        capability_revision=3,
        max_tokens=1536,
        reasoning_mode="long",
        response_mode="structured",
        conversation_count=2,
        run_observation_count=1,
        conversation=(
            CompiledConversationObservation(
                event_id="prior-event-1",
                actor_id="owner-1",
                display_name="主人",
                source_kind="owner",
                occurred_at=occurred_at,
                content="我们昨天聊到了蓝色小屋。",
            ),
            CompiledConversationObservation(
                event_id="prior-event-2",
                actor_id="elfie-1",
                source_kind="elfie",
                occurred_at=occurred_at,
                content="对呀，我还想再去看看。",
            ),
        ),
    )
    trace = build_observability_trace(
        turn_id="turn-1",
        stimulus={"source_domain": "communication", "message": "今天再去吗？"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={
            "reasoning": {"status": "completed", "model_calls": 1, "steps": []}
        },
        result={},
        decision={},
        duration_ms=12,
        observations=[
            _model_call_observation(context_revision=7, user_prompt="PROMPT"),
            _observation(
                boundary="reasoning.context_engine",
                kind="compiled_context",
                turn_id="turn-1",
                payload=compiled,
            ),
        ],
    )

    context_stage = trace["chain"][1]
    expected_rows = [
        {
            "event_id": "prior-event-1",
            "speaker": "开发者",
            "speaker_kind": "owner",
            "actor_id": "owner-1",
            "display_name": "主人",
            "content": "我们昨天聊到了蓝色小屋。",
            "occurred_at": occurred_at.isoformat(),
            "is_current": False,
        },
        {
            "event_id": "prior-event-2",
            "speaker": "elfie",
            "speaker_kind": "elfie",
            "actor_id": "elfie-1",
            "display_name": None,
            "content": "对呀，我还想再去看看。",
            "occurred_at": occurred_at.isoformat(),
            "is_current": False,
        },
    ]
    assert context_stage["output"]["conversation"] == expected_rows
    assert context_stage["output"]["current_observations"] is None
    assert context_stage["output"]["current_run_observations"] is None
    build_output = trace["chain"][3]["iterations"][0]["context_build"]["output"]
    assert "conversation" not in build_output
    assert "prompt_sections" not in build_output


def test_skipped_recall_projects_an_explicit_no_hit_without_error():
    observations = [
        _bridge_observation(
            kind="turn_opened",
            payload=MemoryTurnOpened(
                frame_id="frame-1",
                query="你好",
                pinned_revision=1,
                state=MemoryStateObservation(
                    revision=1,
                    episodic_count=0,
                    total_count=0,
                    snapshot_freshness="fresh",
                ),
            ),
        ),
        _bridge_observation(
            kind="recall_result",
            payload=MemoryRecallResultObservation(
                frame_id="frame-1",
                query="你好",
                status="skipped",
                pinned_revision=1,
                reason="baseline_recall_not_relevant",
                bundle=MemoryRecallBundleObservation(recall_revision=1),
            ),
        ),
    ]

    trace = build_observability_trace(
        turn_id="turn-skip",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={"reasoning": {}},
        result={},
        decision={},
        duration_ms=1,
        observations=observations,
    )

    memory = trace["memory"]
    assert memory["status"] == "skipped"
    assert memory["query"] == "你好"
    assert memory["reason"] == "baseline_recall_not_relevant"
    assert memory["revision"] == 1
    assert memory["returned_points"] == []
    assert memory["returned_evidence"] == ""
    assert memory["on_demand"] == []
    assert trace["chain"][2]["baseline_memory"]["status"] == "skipped"


def test_turn_without_observations_keeps_an_explicit_unavailable_memory_view():
    trace = build_observability_trace(
        turn_id="turn-empty",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={"reasoning": {}},
        result={},
        decision={},
        duration_ms=1,
    )

    memory = trace["memory"]
    assert memory["status"] == "unavailable"
    assert memory["query"] == ""
    assert memory["revision"] is None
    assert memory["returned_points"] == []
    assert memory["selected"] == []


def test_bridge_events_from_other_frames_do_not_leak_into_the_turn_view():
    observations = [
        _bridge_observation(
            kind="turn_opened",
            frame_id="frame-other",
            payload=MemoryTurnOpened(
                frame_id="frame-other",
                query="别的回合",
                pinned_revision=9,
                state=MemoryStateObservation(
                    revision=9,
                    episodic_count=0,
                    total_count=0,
                    snapshot_freshness="fresh",
                ),
            ),
        ),
        _bridge_observation(
            kind="recall_result",
            frame_id="frame-other",
            payload=MemoryRecallResultObservation(
                frame_id="frame-other",
                query="别的回合",
                status="recalled",
                pinned_revision=9,
                bundle=MemoryRecallBundleObservation(recall_revision=9),
            ),
        ),
        _bridge_observation(
            kind="turn_opened",
            payload=MemoryTurnOpened(
                frame_id="frame-1",
                query="你还记得吗？",
                pinned_revision=42,
                state=MemoryStateObservation(
                    revision=42,
                    episodic_count=0,
                    total_count=0,
                    snapshot_freshness="fresh",
                ),
            ),
        ),
        _bridge_observation(
            kind="recall_result",
            payload=MemoryRecallResultObservation(
                frame_id="frame-1",
                query="你还记得吗？",
                status="recalled",
                pinned_revision=42,
                bundle=MemoryRecallBundleObservation(
                    recall_revision=42,
                    episode_ids=("episode:1",),
                ),
            ),
        ),
    ]

    trace = build_observability_trace(
        turn_id="turn-1",
        stimulus={"source_domain": "communication", "message": "你还记得吗？"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={
            "reasoning": {},
            "cognitive_turn": {"frame_id": "frame-1"},
        },
        result={},
        decision={},
        duration_ms=1,
        observations=observations,
    )

    memory = trace["memory"]
    assert memory["status"] == "recalled"
    assert memory["query"] == "你还记得吗？"
    assert memory["revision"] == 42
    assert [point["id"] for point in memory["returned_points"]] == ["episode:1"]


def test_reasoning_projection_keeps_each_model_cycle_with_its_following_evidence():
    trace = build_observability_trace(
        turn_id="turn-multi",
        stimulus={"source_domain": "communication", "message": "你记得吗？"},
        state_before={"energy": 90},
        state_after={"energy": 89},
        state_diff={"energy": {"before": 90, "after": 89}},
        raw_stages={
            "reasoning": {
                "status": "completed",
                "model_calls": 2,
                "tool_calls": 0,
                "skill_calls": 0,
                "steps": [
                    {
                        "ordinal": 1,
                        "kind": "model",
                        "status": "returned",
                        "summary": '{"type":"recall_memory","query":"近况"}',
                    },
                    {
                        "ordinal": 2,
                        "kind": "observation",
                        "status": "received",
                        "operation": "memory_recall",
                        "summary": "memory recall completed",
                    },
                    {
                        "ordinal": 3,
                        "kind": "model",
                        "status": "returned",
                        "summary": '{"type":"answer","content":"记得"}',
                    },
                    {
                        "ordinal": 4,
                        "kind": "verify",
                        "status": "accepted",
                        "summary": "CognitiveAction accepted",
                    },
                ],
            },
        },
        result={"success": True, "message": "记得"},
        decision={"message_texts": ["记得"]},
        duration_ms=120,
        observations=[
            _model_call_observation(
                context_revision=10,
                user_prompt="CURRENT_MESSAGE\n你记得吗？",
                response='{"type":"recall_memory"}',
                iteration_index=1,
            ),
            _model_call_observation(
                context_revision=11,
                user_prompt="CURRENT_MESSAGE\n记忆证据：窗边聊天。",
                response='{"type":"answer","content":"记得"}',
                iteration_index=2,
            ),
        ],
    )

    reasoning = trace["chain"][3]
    assert [iteration["number"] for iteration in reasoning["iterations"]] == [
        "4.1",
        "4.2",
    ]
    first, second = reasoning["iterations"]
    assert first["model_call"]["raw"]["payload"]["iteration_index"] == 1
    assert first["model_call"]["effective_parameters"]["reasoning_mode"] == "long"
    assert first["model_call"]["output"]["provider"] == "mock"
    assert first["model_call"]["output"]["model"] == "elfie-mock"
    assert first["model_call"]["input"]["user_prompt"] == "CURRENT_MESSAGE\n你记得吗？"
    assert first["model_call"]["output"]["response"] == '{"type":"recall_memory"}'
    assert second["model_call"]["raw"]["payload"]["iteration_index"] == 2
    assert first["observations"][0]["operation"] == "memory_recall"
    assert first["observations"][0]["summary"] == "memory recall completed"
    assert first["observation_stage"]["number"] == "4.1.4"
    assert first["observation_stage"]["status"] == "observed"
    assert second["observation_stage"] is None
    assert first["action"]["output"]["type"] == "recall_memory"
    assert second["action"]["output"]["type"] == "answer"
    assert first["guard"] is None
    assert second["guard"] is None
    assert (
        trace["chain"][1]["raw"]["source"]
        == "brain_observations.reasoning.agent_loop.model_call"
    )
    assert all("used_by" not in owner for owner in trace["chain"][2]["owner_snapshots"])
    assert first["model_call"]["capabilities"] is None
    assert "provider_raw" not in first["model_call"]


def test_reasoning_projection_does_not_create_a_phantom_iteration_for_prefix_observation():
    trace = build_observability_trace(
        turn_id="turn-prefix",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={
            "reasoning": {
                "status": "completed",
                "model_calls": 1,
                "steps": [
                    {"ordinal": 1, "kind": "observation", "summary": "baseline"},
                    {"ordinal": 2, "kind": "model", "summary": '{"type":"answer"}'},
                    {
                        "ordinal": 3,
                        "kind": "verify",
                        "status": "accepted",
                        "summary": "ok",
                    },
                ],
            },
        },
        result={},
        decision={},
        duration_ms=1,
        observations=[
            _model_call_observation(
                context_revision=1,
                user_prompt="你好",
                response='{"type":"answer"}',
            )
        ],
    )

    iterations = trace["chain"][3]["iterations"]
    assert len(iterations) == 1
    assert iterations[0]["observations"][0]["summary"] == "baseline"


def test_reasoning_iterations_associate_envelopes_by_iteration_index_not_array_position():
    trace = build_observability_trace(
        turn_id="turn-retry",
        stimulus={"source_domain": "communication", "message": "你记得吗？"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={
            "reasoning": {
                "status": "completed",
                "model_calls": 2,
                "steps": [
                    # Deliberately out of sync with the envelopes: this stale
                    # summary would array-pair with the first model_call even
                    # though it describes a different action.
                    {
                        "ordinal": 1,
                        "kind": "model",
                        "status": "returned",
                        "summary": '{"type":"answer","content":"stale"}',
                    },
                    {
                        "ordinal": 2,
                        "kind": "verify",
                        "status": "accepted",
                        "summary": "CognitiveAction accepted",
                    },
                ],
            },
        },
        result={"success": True, "message": "记得"},
        decision={"message_texts": ["记得"]},
        duration_ms=30,
        observations=[
            _model_call_observation(
                context_revision=7,
                response='{"type":"recall_memory","query":"近况"}',
                iteration_index=1,
            ),
            _agent_loop_observation(
                kind="action_decoded",
                payload=AgentLoopActionObservation(
                    iteration_index=1,
                    action_type="recall_memory",
                    query="近况",
                ),
            ),
            # The second model_call carries its own stable key 3 (an index
            # gap), so pairing must not shift it onto the second array slot.
            _model_call_observation(
                context_revision=9,
                response='{"type":"answer","content":"记得"}',
                iteration_index=3,
            ),
            _agent_loop_observation(
                kind="action_decoded",
                payload=AgentLoopActionObservation(
                    iteration_index=3,
                    action_type="answer",
                    content="记得",
                ),
            ),
            _agent_loop_observation(
                kind="judge",
                payload=AgentLoopJudgeObservation(
                    iteration_index=3,
                    action_type="answer",
                    verdict="accepted",
                    content="记得",
                ),
            ),
            # Keyed to an iteration without a model_call: it must not create
            # a phantom third iteration.
            _agent_loop_observation(
                kind="observation",
                payload=AgentLoopObservationRecorded(
                    iteration_index=2,
                    observation_kind="memory",
                    observation_status="recalled",
                    content="memory recall completed",
                ),
            ),
        ],
    )

    reasoning = trace["chain"][3]
    assert [iteration["number"] for iteration in reasoning["iterations"]] == [
        "4.1",
        "4.2",
    ]
    first, second = reasoning["iterations"]
    assert first["model_call"]["raw"]["payload"]["iteration_index"] == 1
    assert first["action"]["output"]["type"] == "recall_memory"
    assert first["action"]["output"]["query"] == "近况"
    assert first["action"]["raw"]["source"] == (
        "brain_observations.reasoning.agent_loop.action_decoded"
    )
    assert first["raw"]["iteration_index"] == 1
    assert second["model_call"]["raw"]["payload"]["iteration_index"] == 3
    assert second["action"]["output"]["type"] == "answer"
    assert second["action"]["output"]["content"] == "记得"
    assert second["completion"][0]["status"] == "accepted"
    assert second["completion"][0]["verdict"] == "accepted"
    assert second["raw"]["iteration_index"] == 3


def test_activity_proposal_stays_in_decision_and_delivery_without_becoming_a_chat_turn():
    activity = {
        "intent_id": "activity-1",
        "type": "activity",
        "activity_id": "walk-1",
        "content": "在巢里散步",
    }
    trace = build_observability_trace(
        turn_id="turn-activity",
        stimulus={"source_domain": "communication", "message": "我们去散步吧"},
        state_before={"energy": 80},
        state_after={"energy": 79},
        state_diff={"energy": {"before": 80, "after": 79}},
        raw_stages={
            "reasoning": {"status": "completed", "model_calls": 1},
        },
        result={"success": True, "message": "好的"},
        decision={"activity_intents": [activity]},
        duration_ms=80,
    )

    decision = trace["chain"][4]
    governance = trace["chain"][5]
    assert decision["output"]["activity_intents"] == [activity]
    assert governance["output"]["activity_proposals"] == [activity]
    assert governance["delivery"]["input"]["activity_intents"] == [activity]
    assert governance["delivery"]["number"] == "6.1"
    assert governance["delivery"]["title"] == "Delivery / Activity request"
    assert governance["delivery"]["activity_request"]["status"] == "completed"


def test_failed_reasoning_remains_explicit_in_the_production_chain():
    trace = build_observability_trace(
        turn_id="turn-failed",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={"energy": 90},
        state_after={},
        state_diff={},
        raw_stages={
            "reasoning": {
                "status": "failed",
                "failure_reason": "model_unavailable",
                "model_calls": 0,
            },
        },
        result={"success": False, "error": "model unavailable"},
        decision={},
        duration_ms=20,
    )

    assert trace["chain"][3]["status"] == "failed"
    assert trace["chain"][3]["output"]["failure_reason"] == "model_unavailable"
    assert trace["chain"][4]["status"] == "unavailable"


def test_chain_stages_carry_the_sum_of_their_member_event_durations():
    budget = EnergyBudgetStateObservation(
        energy=90.0,
        fatigue=0.0,
        cognitive_mode="normal",
        long_reasoning_allowed=True,
        available_cognitive_budget=12.0,
        reserved_cognitive_budget=12.0,
    )
    observations = [
        _observation(
            boundary="workspace",
            kind="frame_claim",
            payload=WorkspaceFrameAdmissionObservation(
                trigger_reason="perception_write",
                cutoff_seq=1,
                admitted=True,
            ),
            duration_ms=2.0,
        ),
        _observation(
            boundary="reasoning.context_workspace",
            kind="conversation_appended",
            payload=ConversationAppendedObservation(),
            duration_ms=3.0,
        ),
        _bridge_observation(
            kind="turn_opened",
            payload=MemoryTurnOpened(
                frame_id="frame-1",
                query="你还记得吗？",
                pinned_revision=42,
                state=MemoryStateObservation(
                    revision=42,
                    episodic_count=0,
                    total_count=0,
                    snapshot_freshness="fresh",
                ),
            ),
            duration_ms=1.5,
        ),
        _bridge_observation(
            kind="recall_result",
            payload=MemoryRecallResultObservation(
                frame_id="frame-1",
                query="你还记得吗？",
                status="recalled",
                pinned_revision=42,
                bundle=MemoryRecallBundleObservation(recall_revision=42),
            ),
            duration_ms=4.0,
        ),
        _observation(
            boundary="memory.encode",
            kind="use_proposal_recorded",
            frame_id="",
            payload=MemoryUseProposalRecorded(
                proposal_id="prop-1",
                target_kind="assertion",
                target_ids=("assertion:memory-1",),
                recall_revision=42,
                accepted=True,
            ),
            duration_ms=0.5,
        ),
        _model_call_observation(context_revision=7, duration_ms=30.0),
        # A member event without a measured duration contributes zero.
        _model_call_observation(
            context_revision=8,
            iteration_index=2,
            duration_ms=None,
        ),
        _observation(
            boundary="energy",
            kind="budget_reserve",
            payload=CognitiveBudgetReservedObservation(
                mode="long",
                source="communication",
                granted=12.0,
                owner_revision=1,
                responsive=True,
                budget=budget,
            ),
            duration_ms=5.0,
        ),
        _observation(
            boundary="decision_boundary",
            kind="decision_routed",
            payload=DecisionRoutedObservation(
                plan_id="plan-1",
                interaction_scope_kind="conversation",
                source_domain="communication",
            ),
            duration_ms=2.5,
        ),
        _observation(
            boundary="activity",
            kind="preflight_verdict",
            payload=ActivityPreflightVerdictObservation(
                activity_id="walk-1",
                status="allowed",
            ),
            duration_ms=4.0,
        ),
        _observation(
            boundary="energy",
            kind="budget_settled",
            payload=CognitiveBudgetSettledObservation(
                stage="turn",
                consumed=10.0,
                charged=10.0,
                budget=budget,
            ),
            duration_ms=3.0,
        ),
        _observation(
            boundary="energy",
            kind="budget_released",
            payload=CognitiveBudgetReleasedObservation(
                stage="turn",
                released=False,
                budget=budget,
            ),
            duration_ms=2.0,
        ),
    ]

    trace = build_observability_trace(
        turn_id="turn-durations",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={"energy": 90},
        state_after={"energy": 80},
        state_diff={"energy": {"before": 90, "after": 80}},
        raw_stages={"reasoning": {"status": "completed", "model_calls": 2}},
        result={"success": True},
        decision={"message_texts": ["你好"]},
        duration_ms=999.0,
        observations=observations,
    )

    node_durations = {node["id"]: node["duration_ms"] for node in trace["chain"]}
    assert node_durations == {
        "event_admission": 2.0,
        "context_workspace": 3.0,
        "setup": 6.0,
        "reasoning_run": 35.0,
        "turn_decision": 2.5,
        "governance_delivery": 4.0,
        "settlement": 5.0,
    }

    settlement = trace["chain"][6]
    assert settlement["output"]["duration_ms"] == 999.0
    assert trace["duration_ms"] == 999.0
    assert settlement["duration_ms"] == 5.0
    assert settlement["duration_ms"] != trace["duration_ms"]


def test_stage_without_member_events_reports_duration_null():
    trace = build_observability_trace(
        turn_id="turn-durations",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={"reasoning": {}},
        result={},
        decision={},
        duration_ms=40.0,
        observations=[_model_call_observation(context_revision=7, duration_ms=30.0)],
    )

    node_durations = {node["id"]: node["duration_ms"] for node in trace["chain"]}
    assert node_durations == {
        "event_admission": None,
        "context_workspace": None,
        "setup": None,
        "reasoning_run": 30.0,
        "turn_decision": None,
        "governance_delivery": None,
        "settlement": None,
    }

    empty = build_observability_trace(
        turn_id="turn-empty",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={"reasoning": {}},
        result={},
        decision={},
        duration_ms=1.0,
    )

    assert all(node["duration_ms"] is None for node in empty["chain"])


def test_event_admission_projects_the_frame_claim_block():
    trace = build_observability_trace(
        turn_id="turn-admission",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={"reasoning": {}},
        result={},
        decision={},
        duration_ms=10,
        observations=[
            _observation(
                boundary="workspace",
                kind="frame_claim",
                payload=WorkspaceFrameAdmissionObservation(
                    source_domain="communication",
                    trigger_reason="perception_write",
                    cutoff_seq=5,
                    event_count=2,
                    max_event_salience=0.8,
                    event_saliences=(
                        EventSalienceObservation(event_id="event-1", salience=0.8),
                        EventSalienceObservation(event_id="event-2", salience=0.4),
                    ),
                    admitted=True,
                ),
            ),
        ],
    )

    assert trace["chain"][0]["admission"] == {
        "admitted": True,
        "trigger_reason": "perception_write",
        "cutoff_seq": 5,
        "event_count": 2,
        "max_event_salience": 0.8,
        "saliences": [
            {"event_id": "event-1", "salience": 0.8},
            {"event_id": "event-2", "salience": 0.4},
        ],
        "detail": None,
    }
    assert trace["chain"][0]["input"]["modality_values"] == {"text": "你好"}


def test_event_admission_projects_each_embodied_input_value():
    trace = build_observability_trace(
        turn_id="turn-embodied-admission",
        stimulus={
            "source_domain": "embodied",
            "message": "外面有一头大象。",
            "vision_media": {"mime_type": "image/png"},
            "temperature": 24.0,
            "impact_force": 3.0,
            "impact_direction": "背部",
            "gentle_stroke": 0.0,
        },
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={
            "typed_input": {
                "source_domain": "embodied",
                "modalities": ["hearing", "vision", "environment", "touch"],
            },
            "reasoning": {},
        },
        result={},
        decision={},
        duration_ms=10,
    )

    assert trace["chain"][0]["input"]["modality_values"] == {
        "hearing": "外面有一头大象。",
        "vision": "已提供视觉输入（image/png）",
        "environment": "温度 24°C",
        "touch": "背部 · 力度 3",
    }


def test_context_workspace_projects_the_appended_block():
    trace = build_observability_trace(
        turn_id="turn-appended",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={"reasoning": {}},
        result={},
        decision={},
        duration_ms=10,
        observations=[
            _observation(
                boundary="reasoning.context_workspace",
                kind="conversation_appended",
                payload=ConversationAppendedObservation(
                    channel_id="channel-1",
                    conversation_id="conv-1",
                    input_event_ids=("event-1", "event-2"),
                    message_count=2,
                    active_topic_message_count=6,
                    summaries=(
                        ConversationSummaryCoverageObservation(
                            summary_id="summary-1",
                            version=3,
                            source_event_ids=("event-1",),
                            unresolved_count=1,
                        ),
                    ),
                ),
            ),
        ],
    )

    assert trace["chain"][1]["appended"] == {
        "message_count": 2,
        "active_topic_message_count": 6,
        "channel_id": "channel-1",
        "conversation_id": "conv-1",
        "input_event_ids": ["event-1", "event-2"],
        "summaries": [
            {"summary_id": "summary-1", "version": 3, "unresolved_count": 1},
        ],
    }


def test_context_workspace_projects_the_persisted_checkpoint_without_current_input_duplication():
    checkpoint = {
        "threads": [
            {
                "channel_id": "channel-1",
                "conversation_id": "conv-1",
                "messages": [
                    {
                        "event_id": "prior-event",
                        "sender": {
                            "actor_id": "owner-1",
                            "display_name": "主人",
                            "source_kind": "human",
                        },
                        "occurred_at": "2026-09-07T10:00:00+00:00",
                        "content": "上一轮内容",
                    },
                    {
                        "event_id": "current-event",
                        "sender": {
                            "actor_id": "owner-1",
                            "display_name": "主人",
                            "source_kind": "human",
                        },
                        "occurred_at": "2026-09-07T10:01:00+00:00",
                        "content": "本轮内容",
                    },
                    {
                        "event_id": "elfie-reply:intent-current",
                        "sender": {
                            "actor_id": "elfie-1",
                            "source_kind": "elfie",
                        },
                        "occurred_at": "2026-09-07T10:02:00+00:00",
                        "content": "本轮回复",
                    },
                ],
                "summaries": [
                    {
                        "summary_id": "summary-1",
                        "version": 2,
                        "source_event_ids": ["old-event"],
                        "occurred_from": "2026-09-06T10:00:00+00:00",
                        "occurred_to": "2026-09-06T10:30:00+00:00",
                        "content": "之前的压缩摘要",
                        "unresolved_items": ["待确认事项"],
                    }
                ],
                "active_topic": {
                    "thread_id": "topic:prior-event",
                    "lineage_id": "topic:prior-event",
                    "messages": [],
                    "summaries": [],
                    "started_at": "2026-09-06T10:00:00+00:00",
                    "last_activity_at": "2026-09-07T10:00:00+00:00",
                    "close_after_event_id": None,
                    "participants": ["owner-1", "elfie-1"],
                },
                "pending_topics": [],
            }
        ],
        "pending_replies": [
            {
                "intent_id": "intent-1",
                "channel_id": "channel-1",
                "conversation_id": "conv-1",
                "reply_event_id": "reply-1",
                "content": "等待发送的回复",
                "cause_event_ids": ["prior-event"],
                "prepared_at": "2026-09-07T10:02:00+00:00",
                "memory_eligible": True,
            }
        ],
        "pending_closed_episode_payloads": [
            '{"episode_id":"episode-1","event_kind":"interaction","occurred_from":"2026-09-07T09:00:00+00:00","content_text":"待写入经历","summary_text":"待写入摘要","source_event_ids":["prior-event"]}'
        ],
    }
    trace = build_observability_trace(
        turn_id="turn-checkpoint",
        stimulus={"source_domain": "communication", "message": "本轮内容"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={"reasoning": {}},
        result={},
        decision={"message_intents": [{"intent_id": "intent-current"}]},
        duration_ms=10,
        workspace_checkpoint=checkpoint,
        observations=[
            _observation(
                boundary="reasoning.context_workspace",
                kind="conversation_appended",
                payload=ConversationAppendedObservation(
                    channel_id="channel-1",
                    conversation_id="conv-1",
                    input_event_ids=("current-event",),
                    message_count=2,
                ),
            )
        ],
    )

    stage = trace["chain"][1]
    workspace = stage["output"]["workspace"]
    assert workspace["threads"][0]["messages"][0]["content"] == "上一轮内容"
    assert workspace["threads"][0]["messages"][0]["speaker"] == "开发者"
    assert workspace["threads"][0]["messages"][2]["speaker"] == "elfie"
    assert workspace["threads"][0]["messages"][0]["is_current"] is False
    assert workspace["threads"][0]["messages"][1]["is_current"] is True
    assert workspace["threads"][0]["messages"][2]["is_current"] is True
    assert workspace["threads"][0]["summaries"][0]["content"] == "之前的压缩摘要"
    assert workspace["threads"][0]["active_state"]["state"] == "活跃"
    assert workspace["pending_replies"][0]["content"] == "等待发送的回复"
    assert workspace["pending_memory"][0]["content_text"] == "待写入经历"
    assert workspace["checkpoint"] == {
        "status": "已保存",
        "thread_count": 1,
        "pending_reply_count": 1,
        "pending_memory_count": 1,
    }
    assert stage["raw"]["workspace_checkpoint"] == checkpoint
    assert stage["raw"]["workspace_checkpoint_source"] == "brain_continuity_checkpoint"


def test_setup_prefers_mode_and_budget_observations_over_request_fields():
    absolute_deadline = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)

    def _trace(observations):
        return build_observability_trace(
            turn_id="turn-budget",
            stimulus={"source_domain": "communication", "message": "你好"},
            state_before={},
            state_after={},
            state_diff={},
            raw_stages={"reasoning": {"status": "completed", "model_calls": 1}},
            result={},
            decision={},
            duration_ms=50,
            observations=observations,
        )

    trace = _trace(
        [
            _observation(
                boundary="reasoning.run_controller",
                kind="mode_selected",
                payload=ReasoningModeSelectedObservation(
                    depth="deliberate",
                    depth_basis="long_response_requested",
                    reasoning_mode="long",
                    response_mode="structured",
                    requires_model=True,
                    structured_owner_reply=False,
                    fast_owner_reply=False,
                    effective_tools=("recall_memory",),
                    skill_count=2,
                ),
            ),
            _observation(
                boundary="reasoning.run_controller",
                kind="budget_frozen",
                payload=ReasoningBudgetFrozenObservation(
                    max_steps=8,
                    max_model_calls=4,
                    max_tool_calls=2,
                    deadline_seconds=20.0,
                    hard_deadline_seconds=30.0,
                    absolute_deadline=absolute_deadline,
                    max_context_tokens=4096,
                    cognitive_mode="normal",
                    long_reasoning_allowed=True,
                ),
            ),
            _model_call_observation(context_revision=7, reasoning_mode="fast"),
        ]
    )

    setup = trace["chain"][2]
    assert setup["output"]["reasoning_mode"] == "long"
    assert setup["output"]["depth"] == "deliberate"
    assert setup["output"]["depth_basis"] == "long_response_requested"
    assert setup["budget"] == {
        "max_steps": 8,
        "max_model_calls": 4,
        "max_planned_model_calls": None,
        "max_tool_calls": 2,
        "deadline_seconds": 20.0,
        "hard_deadline_seconds": 30.0,
        "absolute_deadline": absolute_deadline.isoformat(),
        "max_context_tokens": 4096,
        "cognitive_mode": "normal",
        "long_reasoning_allowed": True,
    }

    fallback = _trace(
        [_model_call_observation(context_revision=7, reasoning_mode="fast")]
    )
    fallback_setup = fallback["chain"][2]
    assert fallback_setup["output"]["reasoning_mode"] == "fast"
    assert fallback_setup["output"]["depth"] is None
    assert fallback_setup["output"]["depth_basis"] is None
    assert fallback_setup["budget"] is None


def test_setup_projects_the_selfhood_projection_snapshot():
    projected_at = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    trace = build_observability_trace(
        turn_id="turn-selfhood",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={"reasoning": {}},
        result={},
        decision={},
        duration_ms=10,
        observations=[
            _observation(
                boundary="selfhood",
                kind="projection_snapshot",
                payload=SelfhoodProjectionObservation(
                    revision=3,
                    projected_at=projected_at,
                    identity_core_text="IDENTITY_CORE",
                    adaptive_self_text="ADAPTIVE_SELF",
                ),
            ),
        ],
    )

    assert trace["chain"][2]["selfhood_projection"] == {
        "revision": 3,
        "projected_at": projected_at.isoformat(),
        "identity_core_text": "IDENTITY_CORE",
        "adaptive_self_text": "ADAPTIVE_SELF",
    }


def test_setup_owner_snapshots_come_from_context_freeze_not_state_before():
    captured_at = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    frozen = ReasoningContextFrozenObservation(
        context_revision=7,
        constitution_version=2,
        context_captured_at=captured_at,
        emotion=EmotionSnapshot.inactive(captured_at=captured_at, revision=11),
        homeostasis=EnergySnapshot(
            revision=12,
            captured_at=captured_at,
            energy=42.0,
            fatigue=18.0,
            sleeping=False,
            cognitive_mode="degraded",
            long_reasoning_allowed=False,
            available_cognitive_budget=8.0,
            normal_budget_available=4.0,
            emergency_reserve_available=20.0,
            reserved_cognitive_budget=3.0,
        ),
        motivation=MotivationSnapshot(
            revision=13,
            captured_at=captured_at,
            recovery_pressure=0.4,
            recovery_status="ready",
        ),
        orientation=OrientationSnapshot(
            revision=14,
            captured_at=captured_at,
            location="巢内",
            location_source="runtime",
        ),
        selfhood=SelfhoodPromptProjection(
            revision=15,
            captured_at=captured_at,
            identity_core_text="我是艾菲。",
            adaptive_self_text="我会先观察。",
        ),
    )
    trace = build_observability_trace(
        turn_id="turn-frozen",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={"energy": 99.0, "orientation": {"location": "旧位置"}},
        state_after={},
        state_diff={},
        raw_stages={"reasoning": {}},
        result={},
        decision={},
        duration_ms=10,
        observations=[
            _observation(
                boundary="reasoning.run_controller",
                kind="context_frozen",
                payload=frozen,
            )
        ],
    )

    setup = trace["chain"][2]
    assert setup["frozen_state"]["context_revision"] == 7
    assert setup["owner_snapshots"][0]["output"]["location"] == "巢内"
    assert setup["owner_snapshots"][3]["output"]["energy"] == 42.0
    assert setup["owner_snapshots"][1]["output"]["identity_core_text"] == "我是艾菲。"
    assert all(
        owner["evidence_basis"] == "reasoning.run_controller.context_frozen"
        for owner in setup["owner_snapshots"]
    )
    assert setup["raw"]["state_before"]["energy"] == 99.0


def test_context_trim_pairs_with_compiles_positionally_and_leftovers_stay_in_raw():
    def _compile(context_revision: int) -> CompiledContextObservation:
        return CompiledContextObservation(
            turn_id="turn-trim",
            frame_id="frame-1",
            context_revision=context_revision,
            capability_revision=1,
            max_tokens=1536,
            reasoning_mode="long",
            response_mode="structured",
        )

    def _trim(
        *,
        truncated: bool,
        event_truncated_count: int,
    ) -> ContextTrimObservation:
        return ContextTrimObservation(
            max_tokens=1536,
            reserved=256,
            memory_budget=512,
            content_budget=1024,
            event_budget=128,
            observation_budget=64,
            truncated=truncated,
            memory_truncated=False,
            event_truncated_count=event_truncated_count,
        )

    def _trace(trims):
        return build_observability_trace(
            turn_id="turn-trim",
            stimulus={"source_domain": "communication", "message": "你好"},
            state_before={},
            state_after={},
            state_diff={},
            raw_stages={"reasoning": {"status": "completed", "model_calls": 2}},
            result={},
            decision={},
            duration_ms=30,
            observations=[
                *[
                    _observation(
                        boundary="reasoning.context_engine",
                        kind="context_trimmed",
                        payload=trim,
                    )
                    for trim in trims
                ],
                _observation(
                    boundary="reasoning.context_engine",
                    kind="compiled_context",
                    payload=_compile(7),
                ),
                _observation(
                    boundary="reasoning.context_engine",
                    kind="compiled_context",
                    payload=_compile(9),
                ),
                _model_call_observation(context_revision=7, iteration_index=1),
                _model_call_observation(context_revision=9, iteration_index=2),
            ],
        )

    trace = _trace(
        [
            _trim(truncated=False, event_truncated_count=0),
            _trim(truncated=True, event_truncated_count=2),
            _trim(truncated=True, event_truncated_count=5),
        ]
    )
    iterations = trace["chain"][3]["iterations"]
    assert iterations[0]["context_build"]["output"]["trim"]["truncated"] is False
    assert (
        iterations[0]["context_build"]["output"]["trim"]["event_truncated_count"] == 0
    )
    assert iterations[1]["context_build"]["output"]["trim"]["truncated"] is True
    assert (
        iterations[1]["context_build"]["output"]["trim"]["event_truncated_count"] == 2
    )
    assert trace["chain"][3]["raw"]["context_trims_unpaired"] == [
        {
            "max_tokens": 1536,
            "reserved": 256,
            "memory_budget": 512,
            "content_budget": 1024,
            "event_budget": 128,
            "observation_budget": 64,
            "truncated": True,
            "memory_truncated": False,
            "event_truncated_count": 5,
            "history_truncated_count": 0,
            "run_observation_truncated_count": 0,
        }
    ]

    short = _trace([_trim(truncated=False, event_truncated_count=0)])
    short_iterations = short["chain"][3]["iterations"]
    assert "trim" in short_iterations[0]["context_build"]["output"]
    assert "trim" not in short_iterations[1]["context_build"]["output"]
    assert "context_trims_unpaired" not in short["chain"][3]["raw"]


def test_model_call_projection_surfaces_token_usage_and_provider_latency():
    def _trace(**kwargs):
        return build_observability_trace(
            turn_id="turn-tokens",
            stimulus={"source_domain": "communication", "message": "你好"},
            state_before={},
            state_after={},
            state_diff={},
            raw_stages={"reasoning": {"status": "completed", "model_calls": 1}},
            result={},
            decision={},
            duration_ms=30,
            observations=[_model_call_observation(context_revision=7, **kwargs)],
        )

    measured = _trace(
        prompt_tokens=120,
        completion_tokens=45,
        provider_latency_ms=321.5,
    )["chain"][3]["iterations"][0]["model_call"]
    assert measured["prompt_tokens"] == 120
    assert measured["completion_tokens"] == 45
    assert measured["provider_latency_ms"] == 321.5

    bare = _trace()["chain"][3]["iterations"][0]["model_call"]
    assert bare["prompt_tokens"] is None
    assert bare["completion_tokens"] is None
    assert bare["provider_latency_ms"] is None


def test_governance_projects_the_decision_routing_block():
    trace = build_observability_trace(
        turn_id="turn-routing",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={"reasoning": {"status": "completed"}},
        result={"success": True},
        decision={"message_texts": ["你好"]},
        duration_ms=30,
        observations=[
            _observation(
                boundary="decision_boundary",
                kind="decision_routed",
                payload=DecisionRoutedObservation(
                    plan_id="plan-1",
                    intent_types=("speak", "message"),
                    interaction_scope_kind="conversation",
                    source_domain="communication",
                    response_domain="communication",
                    response_channel_id="channel-1",
                    response_conversation_id="conv-1",
                    memory_eligible=False,
                    routed=True,
                ),
            ),
        ],
    )

    assert trace["chain"][5]["routing"] == {
        "routed": True,
        "interaction_scope_kind": "conversation",
        "response_domain": "communication",
        "response_channel_id": "channel-1",
        "response_conversation_id": "conv-1",
        "memory_eligible": False,
    }


def test_settlement_projects_memory_writeback_emotion_and_energy_blocks():
    budget = EnergyBudgetStateObservation(
        energy=90.0,
        fatigue=0.0,
        cognitive_mode="normal",
        long_reasoning_allowed=True,
        available_cognitive_budget=12.0,
        reserved_cognitive_budget=12.0,
    )
    trace = build_observability_trace(
        turn_id="turn-settle",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={"reasoning": {"status": "completed"}},
        result={"success": True},
        decision={},
        duration_ms=60,
        observations=[
            _observation(
                boundary="memory.encode",
                kind="encode_candidate",
                payload=MemoryEncodeCandidate(
                    candidate_id="cand-1",
                    base_revision=4,
                    source_event_ids=("event-1",),
                    emotion="happiness",
                    intensity=60.0,
                    content_chars=120,
                ),
            ),
            _observation(
                boundary="memory.encode",
                kind="encode_commit",
                payload=MemoryEncodeCommit(
                    candidate_id="cand-1",
                    episode_id="episode-9",
                    status="committed",
                    revision_before=4,
                    revision_after=5,
                ),
            ),
            _observation(
                boundary="memory.encode",
                kind="reinforcement_applied",
                payload=MemoryReinforcementApplied(
                    event_id="event-1",
                    target_kind="assertion",
                    target_id="assertion:1",
                    outcome_kind="answer_accepted",
                    accepted=True,
                    revision_before=5,
                    revision_after=6,
                ),
            ),
            _observation(
                boundary="emotion",
                kind="emotion_candidate",
                payload=EmotionCandidateObservation(
                    stage="slow",
                    revision=7,
                    dimensions=(
                        EmotionDimensionChangeObservation(
                            name="happiness",
                            before=0.5,
                            after=0.7,
                        ),
                    ),
                    changed_dimensions=("happiness",),
                ),
            ),
            _observation(
                boundary="energy",
                kind="budget_settled",
                payload=CognitiveBudgetSettledObservation(
                    stage="turn",
                    consumed=10.0,
                    charged=8.0,
                    budget=budget,
                ),
            ),
            _observation(
                boundary="energy",
                kind="budget_released",
                payload=CognitiveBudgetReleasedObservation(
                    stage="turn",
                    released=False,
                    budget=budget,
                ),
            ),
        ],
    )

    settlement = trace["chain"][6]
    assert settlement["memory_writeback"] == {
        "candidates": [
            {
                "candidate_id": "cand-1",
                "base_revision": 4,
                "source_event_ids": ["event-1"],
                "emotion": "happiness",
                "intensity": 60.0,
                "content_chars": 120,
            }
        ],
        "commits": [
            {
                "candidate_id": "cand-1",
                "episode_id": "episode-9",
                "status": "committed",
                "reason": None,
                "revision_before": 4,
                "revision_after": 5,
            }
        ],
        "reinforcements": [
            {
                "event_id": "event-1",
                "target_kind": "assertion",
                "target_id": "assertion:1",
                "outcome_kind": "answer_accepted",
                "accepted": True,
                "reason": None,
                "revision_before": 5,
                "revision_after": 6,
            }
        ],
    }
    assert settlement["emotion_changes"] == {
        "stage": "slow",
        "revision": 7,
        "dimensions": [{"name": "happiness", "before": 0.5, "after": 0.7}],
        "changed_dimensions": ["happiness"],
    }
    assert settlement["energy_settlement"] == {
        "consumed": 10.0,
        "charged": 8.0,
        "released": False,
        "energy_state": {
            "energy": 90.0,
            "fatigue": 0.0,
            "cognitive_mode": "normal",
            "long_reasoning_allowed": True,
            "available_cognitive_budget": 12.0,
            "reserved_cognitive_budget": 12.0,
        },
    }


def test_new_blocks_report_none_without_their_observations():
    trace = build_observability_trace(
        turn_id="turn-none",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={"reasoning": {"status": "completed", "model_calls": 1}},
        result={},
        decision={},
        duration_ms=10,
        observations=[_model_call_observation(context_revision=7)],
    )

    chain = trace["chain"]
    assert chain[0]["admission"] is None
    assert chain[1]["appended"] is None
    assert chain[2]["budget"] is None
    assert chain[2]["selfhood_projection"] is None
    assert chain[3]["raw"].get("context_trims_unpaired") is None
    assert chain[3]["iterations"][0]["context_build"] is None
    assert chain[5]["routing"] is None
    assert chain[6]["memory_writeback"] is None
    assert chain[6]["emotion_changes"] is None
    assert chain[6]["energy_settlement"] is None


_SEQUENCE = {"value": 0}


def _observation(
    *,
    kind: str,
    payload: Any,
    boundary: str = "reasoning.memory_bridge",
    frame_id: str = "frame-1",
    turn_id: str = "",
    duration_ms: Optional[float] = None,
) -> BrainObservation:
    _SEQUENCE["value"] += 1
    return BrainObservation(
        boundary=boundary,
        kind=kind,
        sequence=_SEQUENCE["value"],
        captured_at=datetime.now(timezone.utc),
        turn_id=turn_id,
        frame_id=frame_id,
        duration_ms=duration_ms,
        status=ObservationStatus.completed,
        payload=payload,
    )


def _bridge_observation(
    *,
    kind: str,
    payload: Any,
    frame_id: str = "frame-1",
    duration_ms: Optional[float] = None,
) -> BrainObservation:
    return _observation(
        kind=kind,
        payload=payload,
        frame_id=frame_id,
        duration_ms=duration_ms,
    )


def _model_call_observation(
    *,
    context_revision: int,
    user_prompt: str = "CURRENT_MESSAGE\n你好",
    response: str = '{"type":"answer","content":"好的"}',
    iteration_index: int = 1,
    system_prompt: str = "SYSTEM",
    duration_ms: Optional[float] = None,
    reasoning_mode: str = "long",
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    provider_latency_ms: Optional[float] = None,
) -> BrainObservation:
    return _observation(
        boundary="reasoning.agent_loop",
        kind="model_call",
        duration_ms=duration_ms,
        payload=ModelCallObservation(
            iteration_index=iteration_index,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            reasoning_mode=reasoning_mode,
            response_mode="structured",
            response_schema_name="DecisionPlan",
            temperature=0.2,
            max_tokens=1536,
            context_revision=context_revision,
            capability_revision=1,
            response_text=response,
            selected_mode="json_schema",
            provider="mock",
            model_key="elfie-mock",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            provider_latency_ms=provider_latency_ms,
            duration_ms=5.0,
        ),
    )


def _agent_loop_observation(*, kind: str, payload: Any) -> BrainObservation:
    return _observation(
        boundary="reasoning.agent_loop",
        kind=kind,
        payload=payload,
    )
