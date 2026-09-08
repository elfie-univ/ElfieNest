from datetime import datetime, timezone
from typing import Any, Optional

from devtools.elfie_lab.trace_projection import build_observability_trace
from elfie.brain.activity.observation_payloads import (
    ActivityPreflightVerdictObservation,
)
from elfie.brain.memory.observation_payloads import MemoryUseProposalRecorded
from elfie.brain.observation import BrainObservation, ObservationStatus
from elfie.brain.reasoning.agent_loop_observations import ModelCallObservation
from elfie.brain.reasoning.coordinator_observations import (
    CognitiveBudgetReleasedObservation,
    CognitiveBudgetSettledObservation,
    DecisionRoutedObservation,
    EnergyBudgetStateObservation,
    WorkspaceFrameAdmissionObservation,
)
from elfie.brain.reasoning.observation_payloads import (
    CompiledContextObservation,
    MemoryRecallBundleObservation,
    MemoryRecallResultObservation,
    MemoryStateObservation,
    MemoryTurnOpened,
)
from elfie.brain.reasoning.run_controller_observations import (
    CognitiveBudgetReservedObservation,
    ConversationAppendedObservation,
)


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
    assert context_stage["output"]["compiled"] == {
        "context_revision": 7,
        "capability_revision": 3,
        "memory_recall_revision": 42,
        "max_tokens": 1536,
        "reasoning_mode": "long",
        "response_mode": "structured",
        "event_count": 3,
        "state_update_count": 0,
        "media_sample_count": 0,
        "conversation_count": 4,
        "summary_count": 1,
        "run_observation_count": 2,
        "memory_chars": 512,
        "memory_estimated_tokens": 128,
        "truncated": False,
    }
    assert context_stage["raw"]["compiled_events"][0]["kind"] == "compiled_context"
    assert context_stage["raw"]["user_prompt"] == "PROMPT"
    iteration = trace["chain"][3]["iterations"][0]
    compiled_output = iteration["context_build"]["output"]["compiled"]
    assert compiled_output["run_observation_count"] == 2
    assert "user_prompt" not in iteration["context_build"]["output"]


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
    assert first["observation_stage"]["status"] == "recorded"
    assert second["observation_stage"]["number"] == "4.2.4"
    assert second["observation_stage"]["status"] == "skipped"
    assert first["action"]["output"]["type"] == "recall_memory"
    assert second["action"]["output"]["type"] == "answer"
    assert first["guard"]["number"] == "4.1.5"
    assert second["guard"]["number"] == "4.2.6"
    assert first["guard"]["status"] == "skipped"
    assert second["guard"]["status"] == "skipped"
    assert first["guard"]["output"] == {}
    assert second["guard"]["output"] == {}
    assert "separate Guard record" in first["guard"]["skip_reason"]
    assert "separate Guard record" in second["guard"]["skip_reason"]
    assert (
        trace["chain"][1]["raw"]["source"]
        == "brain_observations.reasoning.agent_loop.model_call"
    )
    assert all("used_by" not in owner for owner in trace["chain"][2]["owner_snapshots"])
    # Capabilities are not part of the model_call observation surface.
    assert "capabilities" not in first["model_call"]
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
    assert governance["delivery"]["activity_request"]["status"] == "recorded"


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
) -> BrainObservation:
    return _observation(
        boundary="reasoning.agent_loop",
        kind="model_call",
        duration_ms=duration_ms,
        payload=ModelCallObservation(
            iteration_index=iteration_index,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            reasoning_mode="long",
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
            duration_ms=5.0,
        ),
    )
