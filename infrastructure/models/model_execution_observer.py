"""Read-only Adapter over the existing model/food/tool observer fact source."""

from __future__ import annotations

from typing import Optional

from app.features.operations import (
    ModelExecutionEventStatus,
    ModelExecutionEventType,
    OperationsPortError,
    StoredModelExecutionEvent,
    StoredModelExecutionMetadata,
    StoredModelExecutionSnapshot,
)
from infrastructure.models.model_execution_observations import (
    ModelExecutionEvent,
    ModelExecutionObserver,
    get_model_execution_observer,
)
from infrastructure.models.model_execution_observations import (
    ModelExecutionEventStatus as TechnicalModelExecutionEventStatus,
)
from infrastructure.models.model_execution_observations import (
    ModelExecutionEventType as TechnicalModelExecutionEventType,
)


class ModelExecutionObserverProjectionAdapter:
    """Project the current observer snapshot without owning or mutating it."""

    def __init__(self, observer: Optional[ModelExecutionObserver] = None) -> None:
        self._observer = observer or get_model_execution_observer()

    def snapshot(self) -> StoredModelExecutionSnapshot:
        events = self._observer.snapshot()
        return StoredModelExecutionSnapshot(
            event_count=len(events),
            last_event=None if not events else self._event(events[-1]),
        )

    @classmethod
    def _event(cls, event: ModelExecutionEvent) -> StoredModelExecutionEvent:
        return StoredModelExecutionEvent(
            event_type=cls._event_type(event.event_type),
            status=cls._event_status(event.status),
            subject=event.subject,
            metadata=tuple(
                StoredModelExecutionMetadata(key=key, value=value)
                for key, value in event.metadata.items()
            ),
        )

    @staticmethod
    def _event_type(value: TechnicalModelExecutionEventType) -> ModelExecutionEventType:
        if value is TechnicalModelExecutionEventType.MODEL_CALL:
            return "model_call"
        if value is TechnicalModelExecutionEventType.TOOL_CALL:
            return "tool_call"
        if value is TechnicalModelExecutionEventType.PERMISSION_DECISION:
            return "permission_decision"
        if value is TechnicalModelExecutionEventType.FALLBACK:
            return "fallback"
        if value is TechnicalModelExecutionEventType.PROVIDER_VERIFY:
            return "provider_verify"
        if value is TechnicalModelExecutionEventType.FOOD_DECISION:
            return "food_decision"
        raise OperationsPortError("unsupported model execution event type")

    @staticmethod
    def _event_status(
        value: TechnicalModelExecutionEventStatus,
    ) -> ModelExecutionEventStatus:
        if value is TechnicalModelExecutionEventStatus.OK:
            return "ok"
        if value is TechnicalModelExecutionEventStatus.ERROR:
            return "error"
        raise OperationsPortError("unsupported model execution event status")


__all__ = ("ModelExecutionObserverProjectionAdapter",)
