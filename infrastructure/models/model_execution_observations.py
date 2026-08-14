from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Union

from pydantic import JsonValue

from infrastructure.models.model_execution_ports import (
    ToolCallObservationPortModel,
    ToolPermissionObservationPortModel,
)
from infrastructure.models.storage_ports import ReportStoragePort

logger = logging.getLogger("infrastructure.models.model_execution_observations")

ModelExecutionMetadataValue = Union[str, int, float, bool]


class ModelExecutionEventType(str, Enum):
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    PERMISSION_DECISION = "permission_decision"
    FALLBACK = "fallback"
    PROVIDER_VERIFY = "provider_verify"
    FOOD_DECISION = "food_decision"


class ModelExecutionEventStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


@dataclass(frozen=True)
class ModelExecutionEvent:
    event_type: ModelExecutionEventType
    status: ModelExecutionEventStatus
    subject: str
    metadata: dict[str, ModelExecutionMetadataValue] = field(default_factory=dict)

    def to_dict(
        self,
    ) -> dict[
        str, ModelExecutionMetadataValue | dict[str, ModelExecutionMetadataValue]
    ]:
        return {
            "event_type": self.event_type.value,
            "status": self.status.value,
            "subject": self.subject,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ModelCallObservation:
    provider: str
    model_name: str
    status: ModelExecutionEventStatus
    prompt_chars: int
    response_chars: int = 0
    error_type: str = ""

    def to_event(self) -> ModelExecutionEvent:
        metadata: dict[str, ModelExecutionMetadataValue] = {
            "provider": self.provider,
            "prompt_chars": self.prompt_chars,
            "response_chars": self.response_chars,
        }
        if self.error_type:
            metadata["error_type"] = self.error_type
        return ModelExecutionEvent(
            event_type=ModelExecutionEventType.MODEL_CALL,
            status=self.status,
            subject=self.model_name,
            metadata=metadata,
        )


@dataclass(frozen=True)
class ToolCallObservation:
    tool_name: str
    status: ModelExecutionEventStatus
    metadata: dict[str, ModelExecutionMetadataValue] = field(default_factory=dict)

    def to_event(self) -> ModelExecutionEvent:
        return ModelExecutionEvent(
            event_type=ModelExecutionEventType.TOOL_CALL,
            status=self.status,
            subject=self.tool_name,
            metadata=dict(self.metadata),
        )


@dataclass(frozen=True)
class PermissionDecisionObservation:
    action: str
    resource: str
    allowed: bool
    mode: str
    reason: str = ""

    def to_event(self) -> ModelExecutionEvent:
        metadata: dict[str, ModelExecutionMetadataValue] = {
            "resource": self.resource,
            "allowed": self.allowed,
            "mode": self.mode,
        }
        if self.reason:
            metadata["reason"] = self.reason
        return ModelExecutionEvent(
            event_type=ModelExecutionEventType.PERMISSION_DECISION,
            status=ModelExecutionEventStatus.OK
            if self.allowed
            else ModelExecutionEventStatus.ERROR,
            subject=self.action,
            metadata=metadata,
        )


@dataclass(frozen=True)
class FallbackObservation:
    from_model_key: str
    from_provider: str
    to_model_key: str
    to_provider: str
    reason: str

    def to_event(self) -> ModelExecutionEvent:
        return ModelExecutionEvent(
            event_type=ModelExecutionEventType.FALLBACK,
            status=ModelExecutionEventStatus.OK,
            subject=self.to_model_key,
            metadata={
                "from_model_key": self.from_model_key,
                "from_provider": self.from_provider,
                "to_provider": self.to_provider,
                "reason": self.reason,
            },
        )


@dataclass(frozen=True)
class ProviderVerifyObservation:
    provider_id: str
    status: ModelExecutionEventStatus
    provider_status: str
    latency_ms: float = 0.0
    error: str = ""

    def to_event(self) -> ModelExecutionEvent:
        metadata: dict[str, ModelExecutionMetadataValue] = {
            "provider_status": self.provider_status,
            "latency_ms": self.latency_ms,
        }
        if self.error:
            metadata["error"] = self.error
        return ModelExecutionEvent(
            event_type=ModelExecutionEventType.PROVIDER_VERIFY,
            status=self.status,
            subject=self.provider_id,
            metadata=metadata,
        )


@dataclass(frozen=True)
class FoodDecisionObservation:
    food_id: str
    status: ModelExecutionEventStatus
    requested_food_id: str
    semantic_role: str
    model: str = ""
    reason: str = ""

    def to_event(self) -> ModelExecutionEvent:
        metadata: dict[str, ModelExecutionMetadataValue] = {
            "requested_food_id": self.requested_food_id,
            "semantic_role": self.semantic_role,
        }
        if self.model:
            metadata["model"] = self.model
        if self.reason:
            metadata["reason"] = self.reason
        return ModelExecutionEvent(
            event_type=ModelExecutionEventType.FOOD_DECISION,
            status=self.status,
            subject=self.food_id,
            metadata=metadata,
        )


class ModelExecutionObserver:
    def __init__(self, report_writer: ReportStoragePort | None = None) -> None:
        self._lock = threading.Lock()
        self._events: list[ModelExecutionEvent] = []
        self._report_writer = report_writer

    def record_model_call(self, observation: ModelCallObservation) -> None:
        self._record(observation.to_event())

    def record_tool_call(self, observation: ToolCallObservation) -> None:
        self._record(observation.to_event())

    def record_permission_decision(
        self, observation: PermissionDecisionObservation
    ) -> None:
        self._record(observation.to_event())

    def record_tool_observation(
        self, observation: ToolCallObservationPortModel
    ) -> None:
        """Implement the Tools-owned observation Port without reversing ownership."""
        self.record_tool_call(
            ToolCallObservation(
                tool_name=observation.tool_name,
                status=(
                    ModelExecutionEventStatus.OK
                    if observation.ok
                    else ModelExecutionEventStatus.ERROR
                ),
                metadata=_model_execution_metadata(observation.metadata),
            )
        )

    def record_permission_observation(
        self, observation: ToolPermissionObservationPortModel
    ) -> None:
        """Map a Tools permission record into the execution projection."""
        self.record_permission_decision(
            PermissionDecisionObservation(
                action=observation.action,
                resource=observation.resource,
                allowed=observation.allowed,
                mode=observation.mode,
                reason=observation.reason,
            )
        )

    def record_fallback(self, observation: FallbackObservation) -> None:
        self._record(observation.to_event())

    def record_provider_verify(self, observation: ProviderVerifyObservation) -> None:
        self._record(observation.to_event())

    def record_food_decision(self, observation: FoodDecisionObservation) -> None:
        self._record(observation.to_event())

    def snapshot(self) -> tuple[ModelExecutionEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def flush(self, batch_id: str) -> None:
        _ = batch_id
        with self._lock:
            self._events = []

    def reset(self) -> None:
        with self._lock:
            self._events = []

    def _record(self, event: ModelExecutionEvent) -> None:
        with self._lock:
            self._events.append(event)
        try:
            if self._report_writer is None:
                return
            run_id = self._report_writer.start_run(
                scope=f"runtime:{event.event_type.value}",
                trigger="runtime",
            )
            self._report_writer.append_observation(
                run_id=run_id,
                subject_kind=_report_subject_kind(event.event_type),
                subject_id=event.subject,
                status=(
                    "passed"
                    if event.status is ModelExecutionEventStatus.OK
                    else "failed"
                ),
                details={
                    "event_type": event.event_type.value,
                    **event.metadata,
                },
            )
            self._report_writer.finish_run(run_id, status="complete")
        except Exception as failure:
            logger.warning("模型执行观测事件持久化失败: %s", failure)


def _report_subject_kind(event_type: ModelExecutionEventType) -> str:
    if event_type is ModelExecutionEventType.TOOL_CALL:
        return "tool"
    if event_type is ModelExecutionEventType.FALLBACK:
        return "fallback"
    if event_type is ModelExecutionEventType.FOOD_DECISION:
        return "food"
    if event_type is ModelExecutionEventType.PROVIDER_VERIFY:
        return "provider"
    return "runtime"


def _model_execution_metadata(
    metadata: Mapping[str, JsonValue],
) -> dict[str, ModelExecutionMetadataValue]:
    return {
        key: value
        for key, value in metadata.items()
        if isinstance(value, (str, int, float, bool))
    }


_model_execution_observer: ModelExecutionObserver | None = None
_model_execution_observer_lock = threading.Lock()


def get_model_execution_observer(
    report_writer: ReportStoragePort | None = None,
) -> ModelExecutionObserver:
    global _model_execution_observer
    if _model_execution_observer is None:
        with _model_execution_observer_lock:
            if _model_execution_observer is None:
                _model_execution_observer = ModelExecutionObserver(report_writer)
    elif report_writer is not None:
        # Composition roots may be rebuilt against a new data home (tests and
        # local recovery do this as well).  Preserve the singleton's in-memory
        # event identity, but always bind persistence to the latest injected
        # writer instead of retaining a stale database path.
        _model_execution_observer._report_writer = report_writer
    return _model_execution_observer
