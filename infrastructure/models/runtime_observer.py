"""Read-only Adapter over the existing model/food/tool observer fact source."""

from __future__ import annotations

from typing import Optional

from app.features.operations import (
    OperationsPortError,
    RuntimeEventStatus,
    RuntimeEventType,
    StoredRuntimeEvent,
    StoredRuntimeMetadata,
    StoredRuntimeSnapshot,
)
from infrastructure.models.runtime_observations import (
    RuntimeEvent,
    RuntimeObserver,
    get_runtime_observer,
)
from infrastructure.models.runtime_observations import (
    RuntimeEventStatus as TechnicalRuntimeEventStatus,
)
from infrastructure.models.runtime_observations import (
    RuntimeEventType as TechnicalRuntimeEventType,
)


class RuntimeObserverProjectionAdapter:
    """Project the current observer snapshot without owning or mutating it."""

    def __init__(self, observer: Optional[RuntimeObserver] = None) -> None:
        self._observer = observer or get_runtime_observer()

    def snapshot(self) -> StoredRuntimeSnapshot:
        events = self._observer.snapshot()
        return StoredRuntimeSnapshot(
            event_count=len(events),
            last_event=None if not events else self._event(events[-1]),
        )

    @classmethod
    def _event(cls, event: RuntimeEvent) -> StoredRuntimeEvent:
        return StoredRuntimeEvent(
            event_type=cls._event_type(event.event_type),
            status=cls._event_status(event.status),
            subject=event.subject,
            metadata=tuple(
                StoredRuntimeMetadata(key=key, value=value)
                for key, value in event.metadata.items()
            ),
        )

    @staticmethod
    def _event_type(value: TechnicalRuntimeEventType) -> RuntimeEventType:
        if value is TechnicalRuntimeEventType.MODEL_CALL:
            return "model_call"
        if value is TechnicalRuntimeEventType.TOOL_CALL:
            return "tool_call"
        if value is TechnicalRuntimeEventType.PERMISSION_DECISION:
            return "permission_decision"
        if value is TechnicalRuntimeEventType.FALLBACK:
            return "fallback"
        if value is TechnicalRuntimeEventType.PROVIDER_VERIFY:
            return "provider_verify"
        if value is TechnicalRuntimeEventType.FOOD_DECISION:
            return "food_decision"
        raise OperationsPortError("unsupported Runtime observer event type")

    @staticmethod
    def _event_status(value: TechnicalRuntimeEventStatus) -> RuntimeEventStatus:
        if value is TechnicalRuntimeEventStatus.OK:
            return "ok"
        if value is TechnicalRuntimeEventStatus.ERROR:
            return "error"
        raise OperationsPortError("unsupported Runtime observer event status")


__all__ = ("RuntimeObserverProjectionAdapter",)
