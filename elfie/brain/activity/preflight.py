"""Side-effect-free validation for Activity drafts inside a ReasoningRun."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Optional, Protocol, Tuple

from elfie.brain.activity.observation_payloads import (
    ActivityPreflightVerdictObservation,
)
from elfie.brain.activity.system import (
    ActivityDraft,
    ActivityPreflightResult,
    ActivityPreflightStatus,
    ActivityRecord,
    ActivityStepKind,
    ActivityStorePort,
)
from elfie.brain.observation import (
    BrainObservation,
    BrainObservationSink,
    ObservationStatus,
)
from elfie.brain.workspace.contracts import ExternalExecutionDomain
from elfie.message_types import ErrorInfo, UTCDateTime


class ActivityPreflightPort(Protocol):
    """Reasoning-owned read-only capability for validating one draft."""

    def preflight(self, draft: ActivityDraft) -> ActivityPreflightResult:
        """Return validation evidence without persistence or external effects."""


TargetResolver = Callable[[str, str, str], bool]


class ActivityCommitPort(Protocol):
    """Settlement boundary that accepts only evidence issued by Preflight."""

    def commit(
        self,
        draft: ActivityDraft,
        preflight: ActivityPreflightResult,
    ) -> ActivityRecord:
        """Commit a draft once after verifying its host-issued evidence."""


class ActivityPreflightService:
    """Combine store, capability, target, budget, and time checks."""

    def __init__(
        self,
        *,
        store: ActivityStorePort,
        clock: Callable[[], UTCDateTime],
        capabilities: Callable[[], object],
        available_budget: Callable[[], float],
        target_resolver: Optional[TargetResolver] = None,
        observation_sink: BrainObservationSink | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._capabilities = capabilities
        self._available_budget = available_budget
        self._target_resolver = target_resolver
        self._observation_sink = observation_sink
        self._issued: dict[str, ActivityPreflightResult] = {}
        self._lock = RLock()
        self._emit_lock = RLock()
        self._emit_sequence = 0

    def _next_observation_sequence(self) -> int:
        with self._emit_lock:
            self._emit_sequence += 1
            return self._emit_sequence

    def _emit_verdict(
        self,
        draft: ActivityDraft,
        result: ActivityPreflightResult,
    ) -> None:
        sink = self._observation_sink
        if sink is None:
            return
        sink.emit(
            BrainObservation[ActivityPreflightVerdictObservation](
                boundary="activity",
                kind="preflight_verdict",
                sequence=self._next_observation_sequence(),
                captured_at=datetime.now(timezone.utc),
                turn_id="",
                frame_id="",
                cause_event_ids=tuple(str(item) for item in draft.cause_event_ids),
                status=ObservationStatus.completed,
                payload=ActivityPreflightVerdictObservation(
                    activity_id=str(draft.activity_id),
                    status=result.status.value,
                    reason_codes=tuple(error.code for error in result.reasons),
                    evidence_issued=(
                        result.status is ActivityPreflightStatus.VALIDATED
                    ),
                    step_count=len(draft.steps),
                    estimated_budget=draft.estimated_budget,
                ),
            )
        )

    def preflight(self, draft: ActivityDraft) -> ActivityPreflightResult:
        """Validate all facts needed before the originating Turn can settle."""
        result = self._validate_draft(draft)
        self._emit_verdict(draft, result)
        return result

    def _validate_draft(self, draft: ActivityDraft) -> ActivityPreflightResult:
        now = self._clock()
        stored = self._store.preflight(draft, now=now)
        if stored.status is not ActivityPreflightStatus.VALIDATED:
            return stored

        capabilities = self._capabilities()
        capability_revision = int(getattr(capabilities, "revision", -1))
        errors: list[ErrorInfo] = []
        clarification: list[ErrorInfo] = []

        if draft.estimated_budget > self._available_budget():
            errors.append(
                ErrorInfo(
                    code="activity_budget_unavailable",
                    message="Activity estimated budget exceeds the current allowance",
                )
            )

        channels = {
            str(channel.channel_id): channel
            for channel in tuple(getattr(capabilities, "connected_channels", ()))
        }
        body = getattr(capabilities, "current_body", None)
        for step in draft.steps:
            scope = step.scope
            if scope.capability_revision != capability_revision:
                errors.append(
                    ErrorInfo(
                        code="activity_capability_revision_stale",
                        message="Activity scope was resolved against stale capabilities",
                    )
                )
                continue
            if scope.expires_at < step.deadline:
                errors.append(
                    ErrorInfo(
                        code="activity_scope_expired",
                        message="Activity execution scope expires before its step",
                    )
                )
                continue
            if not scope.allows(step.operation):
                errors.append(
                    ErrorInfo(
                        code="activity_operation_unauthorized",
                        message="Activity operation is outside its execution scope",
                    )
                )
                continue
            if step.kind is ActivityStepKind.INTERNAL:
                continue
            if scope.external_domain is ExternalExecutionDomain.COMMUNICATION:
                channel = channels.get(scope.channel_id or "")
                if channel is None:
                    clarification.append(
                        ErrorInfo(
                            code="activity_channel_unavailable",
                            message="The target communication channel is not connected",
                        )
                    )
                    continue
                conversations: Tuple[str, ...] = tuple(
                    getattr(channel, "authorized_conversation_ids", ())
                )
                if scope.conversation_id not in conversations:
                    clarification.append(
                        ErrorInfo(
                            code="activity_conversation_unresolved",
                            message="The target conversation is not authorized or resolved",
                        )
                    )
                    continue
                if self._target_resolver is None or not self._target_resolver(
                    str(scope.target_actor_id),
                    scope.channel_id or "",
                    scope.conversation_id or "",
                ):
                    clarification.append(
                        ErrorInfo(
                            code="activity_target_unresolved",
                            message="The target person is not resolved to that conversation",
                        )
                    )
            elif scope.external_domain is ExternalExecutionDomain.NERVOUS_SYSTEM:
                if body is None or (
                    getattr(body, "body_id", None) != scope.body_id
                    or getattr(body, "body_generation", None) != scope.body_generation
                ):
                    errors.append(
                        ErrorInfo(
                            code="activity_body_stale",
                            message="Activity targets a body that is no longer authoritative",
                        )
                    )
                    continue
                actions = tuple(getattr(body, "actions", ()))
                if "*" not in actions and step.operation not in actions:
                    errors.append(
                        ErrorInfo(
                            code="activity_body_operation_unavailable",
                            message="The current body cannot perform the Activity operation",
                        )
                    )

        if errors:
            return ActivityPreflightResult(
                activity_id=draft.activity_id,
                status=ActivityPreflightStatus.REJECTED,
                checked_at=now,
                reasons=tuple(errors),
            )
        if clarification:
            return ActivityPreflightResult(
                activity_id=draft.activity_id,
                status=ActivityPreflightStatus.NEEDS_CLARIFICATION,
                checked_at=now,
                reasons=tuple(clarification),
            )
        with self._lock:
            self._issued[self._evidence_key(draft)] = stored
        return stored

    def commit(
        self,
        draft: ActivityDraft,
        preflight: ActivityPreflightResult,
    ) -> ActivityRecord:
        """Consume exact same-run evidence and persist the validated draft."""
        key = self._evidence_key(draft)
        with self._lock:
            issued = self._issued.pop(key, None)
        # Evidence never crosses a serialization boundary: the ReasoningRun
        # attaches this exact host object to the accepted plan.  Identity here
        # prevents a model from copying a plausible validated payload.
        if issued is None or issued is not preflight:
            raise ValueError(
                "Activity Preflight evidence was not issued for this draft"
            )
        return self._store.commit(draft, preflight=preflight)

    @staticmethod
    def _evidence_key(draft: ActivityDraft) -> str:
        return f"{draft.activity_id}:{draft.model_dump_json()}"


__all__ = (
    "ActivityPreflightPort",
    "ActivityPreflightService",
    "ActivityCommitPort",
    "TargetResolver",
)
