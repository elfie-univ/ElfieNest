"""Validate model output with one repair and a speech-only safe fallback."""

from __future__ import annotations

import json
import re
from enum import Enum, unique
from typing import Any, Callable, Mapping, Optional, Tuple, cast

from pydantic import JsonValue, TypeAdapter, ValidationError

from elfie.brain.reasoning.decision_seed import DecisionDecodeSeed
from elfie.brain.reasoning.decision_trust import bind_plan_to_seed
from elfie.brain.reasoning.decision_types import (
    AnswerDraft,
    CancelPolicy,
    ClarificationDraft,
    CognitiveAction,
    DecisionIntent,
    DecisionPlan,
    MemoryUseReference,
    MessageIntent,
    NoOpDraft,
    NoOpIntent,
    RecallMemory,
    SpeechIntent,
)
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationResult,
    StructuredOutputMode,
)
from elfie.brain.reasoning.turn_outcome import ModelMode, TerminalStatus, TurnOutcome
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
_COGNITIVE_ACTION_ADAPTER = TypeAdapter(CognitiveAction)


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


class CognitiveActionDecodeResult(FrozenContractModel):
    """Validated P0 cognitive action before host-owned decision compilation."""

    action: Optional[CognitiveAction]
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
        allowed_memory_references: Optional[Tuple[Tuple[str, str], ...]] = None,
    ) -> DecisionDecodeResult:
        """Validate once, optionally repair once, then degrade safely."""
        selected_mode = self._mode(capabilities, generation.selected_mode)
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
            extracted = self._extract_decision_message(generation.text)
            return self._fallback(
                seed=seed,
                generation=generation,
                selected_mode=selected_mode,
                errors=(),
                repair_count=0,
                reason=(
                    None if extracted is None else "structured_reply_on_plain_model"
                ),
                fallback_text=extracted,
                suppress_json_like=extracted is None,
            )
        try:
            plan = self._decode_plan(
                generation.text,
                seed=seed,
                allowed_memory_references=allowed_memory_references,
            )
        except (ValidationError, ValueError) as first_error:
            errors = self._errors(first_error)
        else:
            return self._result(plan, generation, selected_mode, (), 0, None)

        if repair_callback is not None:
            repaired_text = repair_callback(generation.text, errors)
            try:
                plan = self._decode_plan(
                    repaired_text,
                    seed=seed,
                    allowed_memory_references=allowed_memory_references,
                )
            except (ValidationError, ValueError) as repair_error:
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

    def decode_cognitive_action(
        self,
        *,
        generation: ModelGenerationResult,
        capabilities: ModelGenerationCapabilities,
        allowed_memory_references: Tuple[Tuple[str, str], ...] = (),
    ) -> CognitiveActionDecodeResult:
        """Decode the P0 control union; only plain text may become an answer."""
        selected_mode = self._mode(capabilities, generation.selected_mode)
        action: Optional[CognitiveAction]
        errors: Tuple[str, ...] = ()
        raw = generation.text.strip()
        if selected_mode is DecisionDecodeMode.PLAIN_TEXT and not self._looks_like_json(
            raw
        ):
            action = AnswerDraft(type="answer", content=raw) if raw else None
            if action is None:
                errors = ("empty_or_meaningless_output",)
        else:
            candidate = raw
            fenced = _FENCED_JSON_PATTERN.fullmatch(candidate)
            if fenced is not None:
                candidate = fenced.group("body").strip()
            try:
                action = _COGNITIVE_ACTION_ADAPTER.validate_json(candidate)
                action = self._normalize_action_memory_references(
                    action,
                    allowed_memory_references=allowed_memory_references,
                )
            except (ValidationError, ValueError) as error:
                action = None
                errors = self._errors(error)
        report = DecisionDecodeReport(
            selected_mode=selected_mode,
            validation_errors=errors,
            repair_count=0,
            fallback_reason=(
                None if action is not None else "cognitive_action_validation_failed"
            ),
            model_id=generation.model_key,
            provider=generation.provider,
            token_count=generation.token_count,
            latency_ms=generation.latency_ms,
        )
        return CognitiveActionDecodeResult(action=action, report=report)

    def compile_cognitive_draft(
        self,
        *,
        seed: DecisionDecodeSeed,
        action: CognitiveAction,
        report: DecisionDecodeReport,
    ) -> DecisionDecodeResult:
        """Bind one accepted draft to the trusted Turn envelope and reply scope."""
        if isinstance(action, RecallMemory):
            raise ValueError("RecallMemory cannot be compiled as a final decision")
        intent_id = IntentId(f"cognitive-intent-{seed.turn_id}")
        intent: DecisionIntent
        if isinstance(action, (AnswerDraft, ClarificationDraft)):
            if seed.reply_channel_id is None or seed.reply_conversation_id is None:
                raise ValueError(
                    "owner reply draft requires a trusted communication scope"
                )
            intent = MessageIntent(
                type="message",
                intent_id=intent_id,
                cause_event_ids=seed.cause_event_ids,
                dependency_ids=(),
                deadline=seed.deadline,
                cancel_policy=CancelPolicy.ALWAYS,
                channel_id=seed.reply_channel_id,
                conversation_id=seed.reply_conversation_id,
                content=action.content,
            )
        elif isinstance(action, NoOpDraft):
            intent = NoOpIntent(
                type="noop",
                intent_id=intent_id,
                cause_event_ids=seed.cause_event_ids,
                dependency_ids=(),
                deadline=seed.deadline,
                cancel_policy=CancelPolicy.IF_NOT_STARTED,
                reason=action.reason,
            )
        else:  # pragma: no cover - discriminated union is exhaustive
            raise TypeError("unsupported cognitive draft")
        memory_uses = tuple(
            MemoryUseReference(
                target_kind=item.target_kind,
                target_id=item.target_id,
                claim_ref=item.claim_ref,
                intent_id=intent_id,
            )
            for item in action.memory_uses
        )
        plan = DecisionPlan(
            plan_id=PlanId(f"cognitive-plan-{seed.turn_id}"),
            turn_id=seed.turn_id,
            frame_id=seed.frame_id,
            context_revision=seed.context_revision,
            capability_revision=seed.capability_revision,
            created_at=seed.created_at,
            deadline=seed.deadline,
            cause_event_ids=seed.cause_event_ids,
            intents=(intent,),
            memory_uses=memory_uses,
            emotion_feedback=action.emotion_feedback,
        )
        return DecisionDecodeResult(plan=plan, report=report)

    @staticmethod
    def cognitive_action_schema() -> Mapping[str, JsonValue]:
        """Return the single P0 cognitive-action schema used by every step."""
        return cast(Mapping[str, JsonValue], _COGNITIVE_ACTION_ADAPTER.json_schema())

    @staticmethod
    def _normalize_action_memory_references(
        action: CognitiveAction,
        *,
        allowed_memory_references: Tuple[Tuple[str, str], ...],
    ) -> CognitiveAction:
        if isinstance(action, RecallMemory):
            return action
        normalized = DecisionPlanDecoder._normalize_memory_references(
            action.memory_uses,
            allowed_memory_references=allowed_memory_references,
        )
        if normalized == action.memory_uses:
            return action
        return action.model_copy(update={"memory_uses": normalized})

    @staticmethod
    def _normalize_memory_references(
        references: Tuple[MemoryUseReference, ...],
        *,
        allowed_memory_references: Tuple[Tuple[str, str], ...],
    ) -> Tuple[MemoryUseReference, ...]:
        """Return RecallBundle IDs, accepting only an unambiguous assertion suffix."""
        allowed = tuple(
            (str(target_kind), str(target_id))
            for target_kind, target_id in allowed_memory_references
        )
        allowed_set = set(allowed)
        normalized: list[MemoryUseReference] = []
        for reference in references:
            target_kind = str(reference.target_kind)
            target_id = str(reference.target_id)
            key = (target_kind, target_id)
            if key in allowed_set:
                canonical_id = target_id
            else:
                canonical_id = DecisionPlanDecoder._assertion_suffix_match(
                    target_kind,
                    target_id,
                    allowed=allowed,
                )
                if canonical_id is None:
                    raise ValueError(
                        "memory use reference is outside the supplied RecallBundle"
                    )
            if canonical_id == target_id:
                normalized.append(reference)
            else:
                normalized.append(
                    reference.model_copy(update={"target_id": canonical_id})
                )
        return tuple(normalized)

    @staticmethod
    def _assertion_suffix_match(
        target_kind: str,
        target_id: str,
        *,
        allowed: Tuple[Tuple[str, str], ...],
    ) -> Optional[str]:
        """Resolve only a unique omitted ``assertion:`` namespace."""
        if target_kind != "assertion":
            return None
        matches = tuple(
            candidate_id
            for candidate_kind, candidate_id in allowed
            if candidate_kind == "assertion"
            and candidate_id.startswith("assertion:")
            and candidate_id[len("assertion:") :] == target_id
        )
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _decode_plan(
        raw_text: str,
        *,
        seed: DecisionDecodeSeed,
        allowed_memory_references: Optional[Tuple[Tuple[str, str], ...]],
    ) -> DecisionPlan:
        """Parse, bind and optionally validate model-selected Memory IDs."""
        plan = bind_plan_to_seed(DecisionPlan.model_validate_json(raw_text), seed)
        if allowed_memory_references is not None:
            normalized = DecisionPlanDecoder._normalize_memory_references(
                plan.memory_uses,
                allowed_memory_references=allowed_memory_references,
            )
            if normalized != plan.memory_uses:
                plan = plan.model_copy(update={"memory_uses": normalized})
        return plan

    @staticmethod
    def _mode(
        capabilities: ModelGenerationCapabilities,
        selected_mode: StructuredOutputMode,
    ) -> DecisionDecodeMode:
        if selected_mode is StructuredOutputMode.PLAIN_TEXT:
            return DecisionDecodeMode.PLAIN_TEXT
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
    def _extract_decision_message(text: str) -> Optional[str]:
        """Avoid leaking a structured envelope from a text-only local model."""
        candidate = text.strip()
        fenced = _FENCED_JSON_PATTERN.fullmatch(candidate)
        if fenced is not None:
            candidate = fenced.group("body").strip()
        try:
            parsed: Any = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        intents = parsed.get("intents")
        if not isinstance(intents, list):
            return None
        for intent in intents:
            if not isinstance(intent, dict) or intent.get("type") != "message":
                continue
            content = intent.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
        return None

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
    def _errors(error: ValidationError | ValueError) -> Tuple[str, ...]:
        if isinstance(error, ValidationError):
            return tuple(item["msg"] for item in error.errors())
        return (str(error),)


__all__ = (
    "CognitiveActionDecodeResult",
    "DecisionDecodeMode",
    "DecisionDecodeReport",
    "DecisionDecodeResult",
    "DecisionDecodeSeed",
    "DecisionPlanDecoder",
    "RepairCallback",
)
