"""Constant-time event trigger metrics for the perceptual workspace."""

from __future__ import annotations

from typing import Iterable, Optional

from elfie.brain.perception_types import PerceptionEvent, SocialPayload
from elfie.brain.workspace_types import WorkspaceStorageMetrics
from elfie.message_types import Priority, UTCDateTime


class WorkspaceEventMetrics:
    """Maintain event-derived trigger values while storage mutates."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._oldest_at: Optional[UTCDateTime] = None
        self._newest_at: Optional[UTCDateTime] = None
        self._oldest_social_at: Optional[UTCDateTime] = None
        self._newest_social_at: Optional[UTCDateTime] = None
        self._critical_count = 0
        self._max_salience = 0.0

    def record(self, event: PerceptionEvent) -> None:
        """Fold one newly stored reliable event into current metrics."""
        occurred_at = event.meta.occurred_at
        if self._oldest_at is None or occurred_at < self._oldest_at:
            self._oldest_at = occurred_at
        if self._newest_at is None or occurred_at > self._newest_at:
            self._newest_at = occurred_at
        if isinstance(event.payload, SocialPayload):
            if self._oldest_social_at is None or occurred_at < self._oldest_social_at:
                self._oldest_social_at = occurred_at
            if self._newest_social_at is None or occurred_at > self._newest_social_at:
                self._newest_social_at = occurred_at
        if event.meta.priority is Priority.CRITICAL:
            self._critical_count += 1
        self._max_salience = max(self._max_salience, event.salience)

    def refresh(self, events: Iterable[PerceptionEvent]) -> None:
        """Recompute after a frame commit removes an arbitrary prefix."""
        retained = tuple(events)
        self._reset()
        for event in retained:
            self.record(event)

    def snapshot(
        self,
        *,
        reliable_event_count: int,
        state_key_count: int,
        media_sample_count: int,
    ) -> WorkspaceStorageMetrics:
        """Combine event metrics with independent storage-zone counts."""
        return WorkspaceStorageMetrics(
            reliable_event_count=reliable_event_count,
            state_key_count=state_key_count,
            media_sample_count=media_sample_count,
            oldest_event_at=self._oldest_at,
            newest_event_at=self._newest_at,
            oldest_social_at=self._oldest_social_at,
            newest_social_at=self._newest_social_at,
            critical_event_count=self._critical_count,
            max_salience=self._max_salience,
        )


__all__ = ("WorkspaceEventMetrics",)
