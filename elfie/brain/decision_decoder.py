"""Validate model output with one repair and a speech-only safe fallback."""

from __future__ import annotations

import json
import re
from enum import Enum, unique
from typing import Any, Callable, Optional, Tuple

from pydantic import ValidationError

from elfie.brain.decision_seed import DecisionDecodeSeed
from elfie.brain.decision_trust import bind_plan_to_seed
from elfie.brain.decision_types import (
    CancelPolicy,
    DecisionIntent,
    DecisionPlan,
    MessageIntent,
    NoOpIntent,
    SpeechIntent,
)
from elfie.brain.runtime_port import (
    ModelGenerationCapabilities,
    ModelGenerationResult,
)
from elfie.brain.turn_outcome import ModelMode, TerminalStatus, TurnOutcome
from elfie.message_types import (
    FrozenContractModel,
    IntentId,
    PlanId,
)

RepairCallback = Callable[[str, Tuple[str, ...]], str]
_OWNER_MESSAGE_FALLBACK = "我收到你的消息了，正在想一想。"
_FENCED_JSON_PATTERN = re.compile(
    r"^```(?:json)?\s*(?P<body>.*?)\s*```$",
    flags=re.IGNORECASE | re.DOTALL,
)


@unique
class DecisionDecodeMode(str, Enum):
    """Safety interpretation applied to the returned model text."""

    NATIVE_SCHEMA = "native_schema"
    JSON_TEXT = "json_text"
    PLAIN_TEXT = "plain_text"


class DecisionDecodeReport(FrozenContractModel):
    """Minimal decoding evidence, intentionally not a rich cognitive trace."""

    selected_mode: DecisionDecodeMode
    validation_errors: Tuple[str, ...]
    repair_count: int
    fallback_reason: Optional[str]
    model_id: str
    provider: str
    token_count: Optional[int]
    latency_ms: Optional[float]

    def to_turn_outcome(
        self,
        *,
        plan: DecisionPlan,
        status: TerminalStatus,
        timeout_reason: Optional[str] = None,
        stale_reason: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> TurnOutcome:
        """Summarize decoding into the stable terminal turn contract."""
        mode = ModelMode.STRUCTURED
        if self.repair_count == 1:
            mode = ModelMode.REPAIRED
        if self.fallback_reason is not None:
            mode = ModelMode.TEXT_FALLBACK
        if plan.intents[0].type == "noop":
            mode = ModelMode.NO_OP
        return TurnOutcome(
            turn_id=plan.turn_id,
            frame_id=plan.frame_id,
            plan_id=plan.plan_id,
            status=status,
            model_mode=mode,
            fallback_reason=self.fallback_reason,
            timeout_reason=timeout_reason,
            stale_reason=stale_reason,
            error_code=error_code,
            receipt_ids=(),
        )


class DecisionDecodeResult(FrozenContractModel):
    """Validated plan and its minimal decode evidence."""

    plan: DecisionPlan
    report: DecisionDecodeReport


class DecisionPlanDecoder:
    """Decode only verified structure; fallback never infers actions."""

    def decode(
        self,
        *,
        seed: DecisionDecodeSeed,
        generation: ModelGenerationResult,
        capabilities: ModelGenerationCapabilities,
        repair_callback: Optional[RepairCallback] = None,
    ) -> DecisionDecodeResult:
        """Validate once, optionally repair once, then degrade safely."""
        selected_mode = self._mode(capabilities)
        is_legacy_wrapper, legacy_text = self._legacy_response_wrapper(generation.text)
        if is_legacy_wrapper:
            return self._fallback(
                seed=seed,
                generation=generation,
                selected_mode=selected_mode,
                errors=(),
                repair_count=0,
                reason=(
                    "legacy_response_wrapper"
                    if legacy_text is not None
                    else "empty_or_meaningless_output"
                ),
                fallback_text=legacy_text,
                suppress_json_like=True,
            )
        if selected_mode is DecisionDecodeMode.PLAIN_TEXT:
            return self._fallback(
                seed=seed,
                generation=generation,
                selected_mode=selected_mode,
                errors=(),
                repair_count=0,
                reason=None,
                fallback_text=None,
                suppress_json_like=False,
            )
        try:
            plan = bind_plan_to_seed(
                DecisionPlan.model_validate_json(generation.text),
                seed,
            )
        except ValidationError as first_error:
            errors = self._errors(first_error)
        else:
            return self._result(plan, generation, selected_mode, (), 0, None)

        if repair_callback is not None:
            repaired_text = repair_callback(generation.text, errors)
            try:
                plan = bind_plan_to_seed(
                    DecisionPlan.model_validate_json(repaired_text),
                    seed,
                )
            except ValidationError as repair_error:
                errors += self._errors(repair_error)
            else:
                return self._result(plan, generation, selected_mode, errors, 1, None)
            repair_count = 1
        else:
            repair_count = 0
        return self._fallback(
            seed=seed,
            generation=generation,
            selected_mode=selected_mode,
            errors=errors,
            repair_count=repair_count,
            reason="json_validation_failed",
            fallback_text=None,
            suppress_json_like=True,
        )

    @staticmethod
    def _mode(capabilities: ModelGenerationCapabilities) -> DecisionDecodeMode:
        if capabilities.plain_text_only:
            return DecisionDecodeMode.PLAIN_TEXT
        if capabilities.supports_json_schema:
            return DecisionDecodeMode.NATIVE_SCHEMA
        return DecisionDecodeMode.JSON_TEXT

    def _fallback(
        self,
        *,
        seed: DecisionDecodeSeed,
        generation: ModelGenerationResult,
        selected_mode: DecisionDecodeMode,
        errors: Tuple[str, ...],
        repair_count: int,
        reason: Optional[str],
        fallback_text: Optional[str],
        suppress_json_like: bool,
    ) -> DecisionDecodeResult:
        text = generation.text if fallback_text is None else fallback_text
        meaningful = bool(text.strip("{}[]:,. \t\r\n"))
        if suppress_json_like and fallback_text is None and self._looks_like_json(text):
            meaningful = False
        plan_id = PlanId(f"fallback-{seed.turn_id}")
        intent_id = IntentId(f"fallback-intent-{seed.turn_id}")
        intent: DecisionIntent
        if seed.reply_channel_id and seed.reply_conversation_id:
            intent = MessageIntent(
                type="message",
                intent_id=intent_id,
                cause_event_ids=seed.cause_event_ids,
                dependency_ids=(),
                deadline=seed.deadline,
                cancel_policy=CancelPolicy.ALWAYS,
                channel_id=seed.reply_channel_id,
                conversation_id=seed.reply_conversation_id,
                content=text if meaningful else _OWNER_MESSAGE_FALLBACK,
            )
            fallback_reason = reason or "owner_message_fallback"
        elif meaningful:
            intent = SpeechIntent(
                type="speech",
                intent_id=intent_id,
                cause_event_ids=seed.cause_event_ids,
                dependency_ids=(),
                deadline=seed.deadline,
                cancel_policy=CancelPolicy.ALWAYS,
                text=text,
            )
            fallback_reason = reason or "plain_text_model"
        else:
            intent = NoOpIntent(
                type="noop",
                intent_id=intent_id,
                cause_event_ids=seed.cause_event_ids,
                dependency_ids=(),
                deadline=seed.deadline,
                cancel_policy=CancelPolicy.IF_NOT_STARTED,
                reason="empty_or_meaningless_output",
            )
            fallback_reason = "empty_or_meaningless_output"
        plan = DecisionPlan(
            plan_id=plan_id,
            turn_id=seed.turn_id,
            frame_id=seed.frame_id,
            context_revision=seed.context_revision,
            capability_revision=seed.capability_revision,
            created_at=seed.created_at,
            deadline=seed.deadline,
            cause_event_ids=seed.cause_event_ids,
            intents=(intent,),
        )
        return self._result(
            plan,
            generation,
            selected_mode,
            errors,
            repair_count,
            fallback_reason,
        )

    @staticmethod
    def _looks_like_json(text: str) -> bool:
        stripped = text.lstrip()
        return stripped.startswith(("{", "[", "```"))

    @staticmethod
    def _legacy_response_wrapper(raw_text: str) -> Tuple[bool, Optional[str]]:
        """Recognize the old response envelope without treating it as a plan."""
        candidate = raw_text.strip()
        fenced = _FENCED_JSON_PATTERN.fullmatch(candidate)
        if fenced is not None:
            candidate = fenced.group("body").strip()
        try:
            parsed: Any = json.loads(candidate)
        except json.JSONDecodeError:
            return False, None
        if not isinstance(parsed, dict):
            return False, None
        decision_plan = parsed.get("DecisionPlan")
        if not isinstance(decision_plan, dict) or not isinstance(
            decision_plan.get("actions"), list
        ):
            return False, None
        for action in decision_plan["actions"]:
            if not isinstance(action, dict) or action.get("action") != "respond":
                continue
            parameters = action.get("parameters")
            if not isinstance(parameters, dict):
                continue
            for field in ("content", "text", "message"):
                value = parameters.get(field)
                if isinstance(value, str) and value.strip():
                    return True, value.strip()
        return True, None

    @staticmethod
    def _result(
        plan: DecisionPlan,
        generation: ModelGenerationResult,
        mode: DecisionDecodeMode,
        errors: Tuple[str, ...],
        repair_count: int,
        fallback_reason: Optional[str],
    ) -> DecisionDecodeResult:
        return DecisionDecodeResult(
            plan=plan,
            report=DecisionDecodeReport(
                selected_mode=mode,
                validation_errors=errors,
                repair_count=repair_count,
                fallback_reason=fallback_reason,
                model_id=generation.model_key,
                provider=generation.provider,
                token_count=generation.token_count,
                latency_ms=generation.latency_ms,
            ),
        )

    @staticmethod
    def _errors(error: ValidationError) -> Tuple[str, ...]:
        return tuple(item["msg"] for item in error.errors())


__all__ = (
    "DecisionDecodeMode",
    "DecisionDecodeReport",
    "DecisionDecodeResult",
    "DecisionDecodeSeed",
    "DecisionPlanDecoder",
    "RepairCallback",
)
