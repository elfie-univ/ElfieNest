from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Union

from ai_runtime.storage.report_repository import ReportRepository

logger = logging.getLogger("ai_runtime.usage.observer")

RuntimeMetadataValue = Union[str, int, float, bool]


class RuntimeEventType(str, Enum):
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    PERMISSION_DECISION = "permission_decision"
    FALLBACK = "fallback"
    PROVIDER_VERIFY = "provider_verify"
    FOOD_DECISION = "food_decision"


class RuntimeEventStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


@dataclass(frozen=True)
class RuntimeEvent:
    event_type: RuntimeEventType
    status: RuntimeEventStatus
    subject: str
    metadata: dict[str, RuntimeMetadataValue] = field(default_factory=dict)

    def to_dict(
        self,
    ) -> dict[str, RuntimeMetadataValue | dict[str, RuntimeMetadataValue]]:
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
    status: RuntimeEventStatus
    prompt_chars: int
    response_chars: int = 0
    error_type: str = ""

    def to_event(self) -> RuntimeEvent:
        metadata: dict[str, RuntimeMetadataValue] = {
            "provider": self.provider,
            "prompt_chars": self.prompt_chars,
            "response_chars": self.response_chars,
        }
        if self.error_type:
            metadata["error_type"] = self.error_type
        return RuntimeEvent(
            event_type=RuntimeEventType.MODEL_CALL,
            status=self.status,
            subject=self.model_name,
            metadata=metadata,
        )


@dataclass(frozen=True)
class ToolCallObservation:
    tool_name: str
    status: RuntimeEventStatus
    metadata: dict[str, RuntimeMetadataValue] = field(default_factory=dict)

    def to_event(self) -> RuntimeEvent:
        return RuntimeEvent(
            event_type=RuntimeEventType.TOOL_CALL,
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

    def to_event(self) -> RuntimeEvent:
        metadata: dict[str, RuntimeMetadataValue] = {
            "resource": self.resource,
            "allowed": self.allowed,
            "mode": self.mode,
        }
        if self.reason:
            metadata["reason"] = self.reason
        return RuntimeEvent(
            event_type=RuntimeEventType.PERMISSION_DECISION,
            status=RuntimeEventStatus.OK if self.allowed else RuntimeEventStatus.ERROR,
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

    def to_event(self) -> RuntimeEvent:
        return RuntimeEvent(
            event_type=RuntimeEventType.FALLBACK,
            status=RuntimeEventStatus.OK,
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
    status: RuntimeEventStatus
    provider_status: str
    latency_ms: float = 0.0
    error: str = ""

    def to_event(self) -> RuntimeEvent:
        metadata: dict[str, RuntimeMetadataValue] = {
            "provider_status": self.provider_status,
            "latency_ms": self.latency_ms,
        }
        if self.error:
            metadata["error"] = self.error
        return RuntimeEvent(
            event_type=RuntimeEventType.PROVIDER_VERIFY,
            status=self.status,
            subject=self.provider_id,
            metadata=metadata,
        )


@dataclass(frozen=True)
class FoodDecisionObservation:
    food_id: str
    status: RuntimeEventStatus
    requested_food_id: str
    semantic_role: str
    model: str = ""
    reason: str = ""

    def to_event(self) -> RuntimeEvent:
        metadata: dict[str, RuntimeMetadataValue] = {
            "requested_food_id": self.requested_food_id,
            "semantic_role": self.semantic_role,
        }
        if self.model:
            metadata["model"] = self.model
        if self.reason:
            metadata["reason"] = self.reason
        return RuntimeEvent(
            event_type=RuntimeEventType.FOOD_DECISION,
            status=self.status,
            subject=self.food_id,
            metadata=metadata,
        )


class RuntimeObserver:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[RuntimeEvent] = []

    def record_model_call(self, observation: ModelCallObservation) -> None:
        self._record(observation.to_event())

    def record_tool_call(self, observation: ToolCallObservation) -> None:
        self._record(observation.to_event())

    def record_permission_decision(
        self, observation: PermissionDecisionObservation
    ) -> None:
        self._record(observation.to_event())

    def record_fallback(self, observation: FallbackObservation) -> None:
        self._record(observation.to_event())

    def record_provider_verify(self, observation: ProviderVerifyObservation) -> None:
        self._record(observation.to_event())

    def record_food_decision(self, observation: FoodDecisionObservation) -> None:
        self._record(observation.to_event())

    def snapshot(self) -> tuple[RuntimeEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def flush(self, batch_id: str) -> None:
        _ = batch_id
        with self._lock:
            self._events = []

    def reset(self) -> None:
        with self._lock:
            self._events = []

    def _record(self, event: RuntimeEvent) -> None:
        with self._lock:
            self._events.append(event)
        try:
            repository = ReportRepository()
            run_id = repository.start_run(
                scope=f"runtime:{event.event_type.value}",
                trigger="runtime",
            )
            repository.append_observation(
                run_id=run_id,
                subject_kind=_report_subject_kind(event.event_type),
                subject_id=event.subject,
                status=(
                    "passed" if event.status is RuntimeEventStatus.OK else "failed"
                ),
                details={
                    "event_type": event.event_type.value,
                    **event.metadata,
                },
            )
            repository.finish_run(run_id, status="complete")
        except Exception as failure:
            logger.warning("Runtime 观测事件持久化失败: %s", failure)


def _report_subject_kind(event_type: RuntimeEventType) -> str:
    if event_type is RuntimeEventType.TOOL_CALL:
        return "tool"
    if event_type is RuntimeEventType.FALLBACK:
        return "fallback"
    if event_type is RuntimeEventType.FOOD_DECISION:
        return "food"
    if event_type is RuntimeEventType.PROVIDER_VERIFY:
        return "provider"
    return "runtime"


_runtime_observer: RuntimeObserver | None = None
_runtime_observer_lock = threading.Lock()


def get_runtime_observer() -> RuntimeObserver:
    global _runtime_observer
    if _runtime_observer is None:
        with _runtime_observer_lock:
            if _runtime_observer is None:
                _runtime_observer = RuntimeObserver()
    return _runtime_observer
