from devtools.elfie_lab.trace_projection import build_observability_trace


def test_memory_evidence_projection_keeps_raw_and_readable_points():
    prompt = """MEMORY_RECALL_STATUS:
status=recalled; revision=42; reason=none

RELEVANT_MEMORY:
<MEMORY_CONTEXT version="1">
<FACT id="assertion:memory-1">
事实：主人喜欢在窗边和我聊天。
关系：elfie --likes--> conversation
状态：active；置信度：0.900
证据原文 assertion:memory-1：窗边聊天记录
</FACT>
</MEMORY_CONTEXT>

CURRENT_MESSAGE:
你还记得吗？"""

    trace = build_observability_trace(
        turn_id="turn-1",
        stimulus={"source_domain": "communication", "message": "你还记得吗？"},
        state_before={"energy": 90},
        state_after={},
        state_diff={},
        raw_stages={
            "model_calls": [{"request": {"user_prompt": prompt}}],
            "reasoning": {},
        },
        result={},
        decision={},
        duration_ms=12,
    )

    baseline = trace["chain"][2]["baseline_memory"]
    assert baseline["status"] == "recalled"
    assert baseline["revision"] == 42
    assert baseline["returned_points"] == [
        {
            "kind": "fact",
            "claim": "主人喜欢在窗边和我聊天。",
            "relation": "elfie --likes--> conversation",
            "evidence": "窗边聊天记录",
            "status": "active",
            "confidence": 0.9,
        }
    ]
    assert baseline["returned_evidence"].startswith("<MEMORY_CONTEXT")
    assert baseline["evidence_basis"] == "model_request.RELEVANT_MEMORY"
    delivery = trace["chain"][5]["delivery"]
    assert delivery["number"] == "6.1"
    assert delivery["title"] == "Delivery / Activity request"
    assert delivery["output"]["receipts"] == []
    assert delivery["activity_request"]["status"] == "skipped"


def test_reasoning_projection_keeps_each_model_cycle_with_its_following_evidence():
    trace = build_observability_trace(
        turn_id="turn-multi",
        stimulus={"source_domain": "communication", "message": "你记得吗？"},
        state_before={"energy": 90},
        state_after={"energy": 89},
        state_diff={"energy": {"before": 90, "after": 89}},
        raw_stages={
            "model_calls": [
                {
                    "call_index": 1,
                    "provider": "mock",
                    "model": "elfie-mock",
                    "effective_parameters": {
                        "reasoning_mode": "long",
                        "temperature": 0.2,
                        "max_tokens": 1536,
                    },
                    "capabilities": {
                        "supports_json_schema": True,
                        "supports_tool_calling": False,
                    },
                    "request": {
                        "context_revision": 10,
                        "system_prompt": "SYSTEM",
                        "user_prompt": "CURRENT_MESSAGE\n你记得吗？",
                    },
                    "response": '{"type":"recall_memory"}',
                    "result": {"selected_mode": "json_schema"},
                },
                {
                    "call_index": 2,
                    "request": {
                        "context_revision": 11,
                        "system_prompt": "SYSTEM",
                        "user_prompt": "CURRENT_MESSAGE\n记忆证据：窗边聊天。",
                    },
                    "response": '{"type":"answer","content":"记得"}',
                    "result": {"selected_mode": "json_schema"},
                },
            ],
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
                        "summary": "query=近况; reason=needed; result=窗边聊天; detail=none",
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
    )

    reasoning = trace["chain"][3]
    assert [iteration["number"] for iteration in reasoning["iterations"]] == [
        "4.1",
        "4.2",
    ]
    first, second = reasoning["iterations"]
    assert first["model_call"]["raw"]["call_index"] == 1
    assert first["model_call"]["effective_parameters"]["reasoning_mode"] == "long"
    assert first["model_call"]["capabilities"]["supports_json_schema"] is True
    assert first["model_call"]["input"]["user_prompt"] == "CURRENT_MESSAGE\n你记得吗？"
    assert first["model_call"]["output"]["response"] == '{"type":"recall_memory"}'
    assert second["model_call"]["raw"]["call_index"] == 2
    assert first["observations"][0]["operation"] == "memory_recall"
    assert first["observations"][0]["returned_evidence"] == "窗边聊天"
    assert first["observations"][0]["detail"] == "none"
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
    assert trace["chain"][1]["raw"]["source"] == "ModelGenerationRequest.user_prompt"
    assert all("used_by" not in owner for owner in trace["chain"][2]["owner_snapshots"])
    assert "provider_raw" not in first["model_call"]


def test_reasoning_projection_does_not_create_a_phantom_iteration_for_prefix_observation():
    trace = build_observability_trace(
        turn_id="turn-prefix",
        stimulus={"source_domain": "communication", "message": "你好"},
        state_before={},
        state_after={},
        state_diff={},
        raw_stages={
            "model_calls": [
                {
                    "call_index": 1,
                    "request": {"context_revision": 1, "user_prompt": "你好"},
                    "response": '{"type":"answer"}',
                    "result": {},
                }
            ],
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
            "model_calls": [],
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
            "model_calls": [],
        },
        result={"success": False, "error": "model unavailable"},
        decision={},
        duration_ms=20,
    )

    assert trace["chain"][3]["status"] == "failed"
    assert trace["chain"][3]["output"]["failure_reason"] == "model_unavailable"
    assert trace["chain"][4]["status"] == "unavailable"
