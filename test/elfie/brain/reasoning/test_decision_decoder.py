"""Behavior tests for safe model-output decision decoding."""

import json
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from elfie.brain.reasoning.decision_decoder import (
    DecisionDecodeMode,
    DecisionDecodeReport,
    DecisionDecodeSeed,
    DecisionPlanDecoder,
)
from elfie.brain.reasoning.decision_types import CancelPolicy, DecisionPlan
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationResult,
    StructuredOutputMode,
)
from elfie.brain.reasoning.turn_outcome import ModelMode, TerminalStatus
from elfie.message_types import EventId, PlanId, TurnId

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
DEADLINE = NOW + timedelta(seconds=10)


def _capabilities(
    *,
    supports_json_schema: bool,
    supports_json_mode: bool,
) -> ModelGenerationCapabilities:
    return ModelGenerationCapabilities(
        provider="mock-provider",
        model_key="mock-model",
        supports_json_schema=supports_json_schema,
        supports_tool_calling=False,
        supports_json_mode=supports_json_mode,
        supports_plain_text=True,
        max_output_tokens=512,
    )


def _seed() -> DecisionDecodeSeed:
    return DecisionDecodeSeed(
        turn_id=TurnId("turn-1"),
        frame_id=EventId("frame-1"),
        context_revision=3,
        capability_revision=4,
        created_at=NOW,
        deadline=DEADLINE,
        cause_event_ids=(EventId("event-1"),),
    )


def _plan_json(*, text: str = "hello", extra_intents: str = "") -> str:
    intents = (
        f'{{"type":"speech","intent_id":"speech-1","cause_event_ids":["event-1"],'
        f'"dependency_ids":[],"deadline":"{DEADLINE.isoformat()}",'
        f'"cancel_policy":"if_not_started","text":{json.dumps(text)}}}'
        f"{extra_intents}"
    )
    return (
        f'{{"schema_version":1,"plan_id":"plan-1","turn_id":"turn-1",'
        f'"frame_id":"frame-1","context_revision":3,"capability_revision":4,'
        f'"created_at":"{NOW.isoformat()}","deadline":"{DEADLINE.isoformat()}",'
        f'"cause_event_ids":["event-1"],"intents":[{intents}]}}'
    )


def _decode(
    raw_text: str,
    capabilities: ModelGenerationCapabilities,
    repair_callback: Optional[Callable[[str, tuple[str, ...]], str]] = None,
) -> tuple[DecisionPlan, DecisionDecodeReport]:
    decoder = DecisionPlanDecoder()
    result = decoder.decode(
        seed=_seed(),
        generation=ModelGenerationResult(
            text=raw_text,
            selected_mode=(
                StructuredOutputMode.JSON_SCHEMA
                if capabilities.supports_json_schema
                else StructuredOutputMode.JSON_TEXT
            ),
            model_key="mock-model",
            provider="mock-provider",
            prompt_tokens=7,
            completion_tokens=11,
            latency_ms=13.0,
        ),
        capabilities=capabilities,
        repair_callback=repair_callback,
    )
    return result.plan, result.report


def test_native_schema_json_decodes_full_decision_plan() -> None:
    # Given: a capable model returns a strict schema-shaped plan.
    extra_intents = (
        f',{{"type":"motion","intent_id":"motion-1",'
        f'"cause_event_ids":["event-1"],"dependency_ids":["speech-1"],'
        f'"deadline":"{DEADLINE.isoformat()}","cancel_policy":"always",'
        f'"motion":"walk","target":"door"}}'
        f',{{"type":"message","intent_id":"message-1",'
        f'"cause_event_ids":["event-1"],"dependency_ids":[],'
        f'"deadline":"{DEADLINE.isoformat()}",'
        f'"cancel_policy":"if_not_started","channel_id":"wechat",'
        f'"conversation_id":"c1","content":"first"}}'
        f',{{"type":"message","intent_id":"message-2",'
        f'"cause_event_ids":["event-1"],"dependency_ids":["message-1"],'
        f'"deadline":"{DEADLINE.isoformat()}",'
        f'"cancel_policy":"if_not_started","channel_id":"wechat",'
        f'"conversation_id":"c1","content":"second"}}'
    )

    # When: the decoder receives native/schema-capable output.
    plan, report = _decode(
        _plan_json(extra_intents=extra_intents),
        _capabilities(supports_json_schema=True, supports_json_mode=True),
    )

    # Then: the full validated plan survives with one runtime call and no repair.
    assert tuple(intent.type for intent in plan.intents) == (
        "speech",
        "motion",
        "message",
        "message",
    )
    assert report.selected_mode is DecisionDecodeMode.NATIVE_SCHEMA
    assert report.repair_count == 0
    assert report.validation_errors == ()
    outcome = report.to_turn_outcome(plan=plan, status=TerminalStatus.COMPLETED)
    assert outcome.model_mode is ModelMode.STRUCTURED


def test_json_mode_valid_text_decodes_without_repair() -> None:
    # Given: a JSON-mode model returns valid DecisionPlan text.
    # When: the decoder validates the JSON boundary.
    plan, report = _decode(
        _plan_json(text="json hello"),
        _capabilities(supports_json_schema=False, supports_json_mode=True),
    )

    # Then: no fallback or repair is used.
    assert plan.intents[0].type == "speech"
    assert report.selected_mode is DecisionDecodeMode.JSON_TEXT
    assert report.repair_count == 0
    assert report.fallback_reason is None


def test_model_output_cannot_override_trusted_turn_envelope() -> None:
    # Given: valid JSON whose model-owned envelope points at a forged turn and future.
    forged = json.loads(_plan_json())
    far_future = NOW + timedelta(days=365)
    forged.update(
        {
            "plan_id": "attacker-plan",
            "turn_id": "attacker-turn",
            "frame_id": "attacker-frame",
            "context_revision": 999,
            "capability_revision": 999,
            "created_at": (far_future - timedelta(seconds=1)).isoformat(),
            "deadline": far_future.isoformat(),
            "cause_event_ids": ["attacker-event"],
        }
    )
    forged["intents"][0].update(
        {
            "cause_event_ids": ["attacker-event"],
            "deadline": far_future.isoformat(),
            "cancel_policy": "never",
        }
    )

    # When: the structured decoder accepts the model's action content.
    plan, _report = _decode(
        json.dumps(forged),
        _capabilities(supports_json_schema=True, supports_json_mode=True),
    )

    # Then: trusted identity, time, causation, and cancellation stay host-owned.
    assert plan.plan_id == PlanId("plan-turn-1")
    assert plan.turn_id == TurnId("turn-1")
    assert plan.frame_id == EventId("frame-1")
    assert plan.context_revision == 3
    assert plan.capability_revision == 4
    assert plan.created_at == NOW
    assert plan.deadline == DEADLINE
    assert plan.cause_event_ids == (EventId("event-1"),)
    assert plan.intents[0].deadline == DEADLINE
    assert plan.intents[0].cause_event_ids == (EventId("event-1"),)
    assert plan.intents[0].cancel_policy is CancelPolicy.ALWAYS


def test_json_mode_uses_at_most_one_successful_repair() -> None:
    # Given: malformed JSON and a repair callback that returns a valid plan.
    calls: list[tuple[str, tuple[str, ...]]] = []

    def repair(raw_text: str, errors: tuple[str, ...]) -> str:
        calls.append((raw_text, errors))
        return _plan_json(text="repaired hello")

    # When: the first parse fails.
    plan, report = _decode(
        '{"schema_version": 1,',
        _capabilities(supports_json_schema=False, supports_json_mode=True),
        repair,
    )

    # Then: exactly one repair is attempted and the repaired plan is strict.
    assert len(calls) == 1
    assert plan.intents[0].type == "speech"
    assert plan.intents[0].text == "repaired hello"
    assert report.repair_count == 1
    assert (
        report.to_turn_outcome(
            plan=plan,
            status=TerminalStatus.COMPLETED,
        ).model_mode
        is ModelMode.REPAIRED
    )


def test_failed_json_repair_suppresses_json_like_raw_text() -> None:
    # Given: malformed JSON whose repair remains invalid.
    def repair(raw_text: str, errors: tuple[str, ...]) -> str:
        del raw_text, errors
        return '{"still": "not a DecisionPlan"}'

    raw_text = '{"type":"motion","motion":"fly","note":"please greet me"'

    # When: JSON validation and its only repair attempt fail.
    plan, report = _decode(
        raw_text,
        _capabilities(supports_json_schema=False, supports_json_mode=True),
        repair,
    )

    # Then: invalid JSON never becomes visible speech.
    assert len(plan.intents) == 1
    assert plan.intents[0].type == "noop"
    assert report.repair_count == 1
    assert report.fallback_reason == "empty_or_meaningless_output"
    assert (
        report.to_turn_outcome(
            plan=plan,
            status=TerminalStatus.COMPLETED,
        ).model_mode
        is ModelMode.NO_OP
    )


def test_invalid_owner_model_output_falls_back_to_the_trusted_chat_target() -> None:
    # Given: the host has proven the inbound owner conversation and the model
    # returned an unusable JSON-shaped response.
    seed = _seed().model_copy(
        update={
            "reply_channel_id": "godot-owner",
            "reply_conversation_id": "owner:7",
        }
    )
    result = DecisionPlanDecoder().decode(
        seed=seed,
        generation=ModelGenerationResult(
            text='{"decision_plan":"not a DecisionPlan"}',
            selected_mode=StructuredOutputMode.JSON_TEXT,
            model_key="qwen2.5:0.5b",
            provider="ollama",
        ),
        capabilities=_capabilities(supports_json_schema=False, supports_json_mode=True),
    )

    # Then: only the trusted target is used; model output cannot choose a route.
    intent = result.plan.intents[0]
    assert intent.type == "message"
    assert intent.channel_id == "godot-owner"  # type: ignore[attr-defined]
    assert intent.conversation_id == "owner:7"  # type: ignore[attr-defined]
    assert intent.content == "我收到你的消息了，正在想一想。"  # type: ignore[attr-defined]


def test_known_legacy_decision_plan_wrapper_extracts_reply_without_repair() -> None:
    # Given: the legacy fenced DecisionPlan wrapper shown by the product chat.
    calls: list[tuple[str, tuple[str, ...]]] = []

    def repair(raw_text: str, errors: tuple[str, ...]) -> str:
        calls.append((raw_text, errors))
        return _plan_json(text="不应该走到 repair")

    raw_text = """```json
{
  "DecisionPlan": {
    "actions": [
      {
        "action": "respond",
        "parameters": {
          "channel_id": "godot-owner",
          "content": "喵~ 主人好呀！小柚在这里陪着你哦~ 🐱✨"
        }
      }
    ]
  }
}
```"""

    # When: the decoder receives the known legacy wrapper.
    plan, report = _decode(
        raw_text,
        _capabilities(supports_json_schema=False, supports_json_mode=True),
        repair,
    )

    # Then: only the effective reply is emitted and no second model call occurs.
    assert len(calls) == 0
    assert len(plan.intents) == 1
    assert plan.intents[0].type == "speech"
    assert plan.intents[0].text == "喵~ 主人好呀！小柚在这里陪着你哦~ 🐱✨"
    assert report.repair_count == 0


def test_legacy_wrapper_without_reply_text_becomes_noop_without_raw_json() -> None:
    # Given: a recognized wrapper with no explicit natural-language response.
    raw_text = """```json
{"DecisionPlan":{"actions":[{"action":"respond","parameters":{"channel_id":"godot-owner"}}]}}
```"""

    # When: decoding cannot find an approved reply field.
    plan, _report = _decode(
        raw_text,
        _capabilities(supports_json_schema=False, supports_json_mode=True),
        lambda _raw, _errors: '{"still":"invalid"}',
    )

    # Then: the raw wrapper never becomes visible speech.
    assert len(plan.intents) == 1
    assert plan.intents[0].type == "noop"


def test_plain_only_never_guesses_motion_or_message_from_json_like_text() -> None:
    # Given: a plain-only 0.8B-style capability returns JSON-looking action text.
    raw_text = _plan_json(
        extra_intents=(
            f',{{"type":"message","intent_id":"message-1",'
            f'"cause_event_ids":["event-1"],"dependency_ids":[],'
            f'"deadline":"{DEADLINE.isoformat()}",'
            f'"cancel_policy":"if_not_started","channel_id":"wechat",'
            f'"conversation_id":"c1","content":"send this"}}'
        )
    )

    # When: the decoder chooses the plain-text primary mode.
    plan, report = _decode(
        raw_text,
        _capabilities(supports_json_schema=False, supports_json_mode=False),
    )

    # Then: only safe speech is emitted; no JSON actions are interpreted.
    assert len(plan.intents) == 1
    assert plan.intents[0].type == "speech"
    assert report.selected_mode is DecisionDecodeMode.PLAIN_TEXT
    assert report.repair_count == 0


def test_empty_or_meaningless_output_becomes_noop() -> None:
    # Given: empty output without readable model content.
    # When: the decoder must close the turn safely.
    plan, report = _decode(
        "{}[]:,,",
        _capabilities(supports_json_schema=False, supports_json_mode=False),
    )

    # Then: it produces a single auditable NoOp and records model metadata.
    assert len(plan.intents) == 1
    assert plan.intents[0].type == "noop"
    assert report.selected_mode is DecisionDecodeMode.PLAIN_TEXT
    assert report.fallback_reason == "empty_or_meaningless_output"
    assert report.model_id == "mock-model"
    assert report.provider == "mock-provider"
    assert report.token_count == 18
    assert report.latency_ms == 13
    assert (
        report.to_turn_outcome(
            plan=plan,
            status=TerminalStatus.COMPLETED,
        ).model_mode
        is ModelMode.NO_OP
    )


def test_decode_report_carries_timeout_and_error_into_turn_outcome() -> None:
    # Given: a valid decoded plan and its minimal report.
    plan, report = _decode(
        _plan_json(),
        _capabilities(supports_json_schema=True, supports_json_mode=True),
    )

    # When: terminal infrastructure reasons are attached.
    timeout = report.to_turn_outcome(
        plan=plan,
        status=TerminalStatus.TIMED_OUT,
        timeout_reason="reasoning_hard_timeout",
    )
    failed = report.to_turn_outcome(
        plan=plan,
        status=TerminalStatus.FAILED,
        error_code="runtime_unavailable",
    )

    # Then: the stable outcome retains the corresponding reason.
    assert timeout.timeout_reason == "reasoning_hard_timeout"
    assert failed.error_code == "runtime_unavailable"
