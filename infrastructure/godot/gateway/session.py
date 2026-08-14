"""Authoritative Godot Runtime session state and inbound event queue."""

from __future__ import annotations

import queue
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock

from infrastructure.godot.gateway.messages import (
    CommandName,
    JsonObject,
    RuntimeCommandFrame,
    RuntimeEventFrame,
    SemanticLane,
)


@dataclass(frozen=True)
class RuntimeConnection:
    """当前权威 Runtime 连接租约。"""

    runtime_id: str
    generation: int


class RuntimeAuthorityError(RuntimeError):
    """另一个 Runtime 已经持有 authority。"""

    def __init__(self, runtime_id: str) -> None:
        super().__init__(runtime_id)
        self.runtime_id = runtime_id

    def __str__(self) -> str:
        return f"runtime {self.runtime_id} already owns authority"


class RuntimeQueueFullError(RuntimeError):
    """Runtime inbound event queue 已满。"""


class RuntimeSessionNotReadyError(RuntimeError):
    """Runtime 尚未 ready 或 revision 不匹配。"""


class StaleRuntimeEventError(RuntimeError):
    """事件来自过期 runtime/generation。"""


class RuntimeSession:
    """Single-authority Runtime session with explicit event draining."""

    def __init__(self, max_queue_size: int = 32) -> None:
        self._max_queue_size = max_queue_size
        self._active: RuntimeConnection | None = None
        self._last_runtime_id: str | None = None
        self._last_generation = 0
        self._configured_revision: int | None = None
        self._queue: queue.Queue[RuntimeEventFrame] = queue.Queue(
            maxsize=max_queue_size
        )
        self._seen_event_ids: set[tuple[str, int, str]] = set()
        self._seen_event_order: deque[tuple[str, int, str]] = deque()
        self._max_seen_event_ids = max(256, max_queue_size * 4)
        self._command_sequence = 0
        self._lock = RLock()
        self.duplicate_event_count = 0
        self.stale_event_count = 0
        self.dropped_event_count = 0

    @property
    def active(self) -> RuntimeConnection | None:
        with self._lock:
            return self._active

    @property
    def configured_revision(self) -> int | None:
        with self._lock:
            return self._configured_revision

    def acquire_authority(self, runtime_id: str) -> RuntimeConnection:
        with self._lock:
            active = self._active
            if active is not None:
                raise RuntimeAuthorityError(active.runtime_id)
            if self._last_runtime_id == runtime_id:
                generation = self._last_generation + 1
            else:
                generation = 1
            connection = RuntimeConnection(
                runtime_id=runtime_id,
                generation=generation,
            )
            self._active = connection
            self._last_runtime_id = runtime_id
            self._last_generation = generation
            self._configured_revision = None
            self._command_sequence = 0
            return connection

    def disconnect(self, connection: RuntimeConnection) -> None:
        with self._lock:
            if self._active == connection:
                self._active = None
                self._configured_revision = None

    def mark_world_configured(
        self,
        connection: RuntimeConnection,
        *,
        world_revision: int,
    ) -> None:
        with self._lock:
            self._require_active(connection)
            self._configured_revision = world_revision

    def ensure_ready_for_command(self, *, world_revision: int) -> None:
        with self._lock:
            if self._active is None or self._configured_revision is None:
                raise RuntimeSessionNotReadyError("world is not configured")
            if self._configured_revision != world_revision:
                raise RuntimeSessionNotReadyError("world revision mismatch")

    def accept_event(self, event: RuntimeEventFrame) -> bool:
        """Validate authority and identity once before semantic routing."""
        with self._lock:
            self._require_current_event(event)
            event_key = (event.runtime_id, event.generation, event.message_id)
            if event_key in self._seen_event_ids:
                self.duplicate_event_count += 1
                return False
            self._remember_event(event_key)
            return True

    def enqueue_event(self, event: RuntimeEventFrame) -> None:
        """Validate, deduplicate and queue one Nest-lane event atomically."""
        with self._lock:
            self._require_current_event(event)
            event_key = (event.runtime_id, event.generation, event.message_id)
            if event_key in self._seen_event_ids:
                self.duplicate_event_count += 1
                return
            if self._queue.full():
                self.dropped_event_count += 1
                raise RuntimeQueueFullError(event.message_id)
            self._remember_event(event_key)
            self._queue.put_nowait(event)

    def _require_current_event(self, event: RuntimeEventFrame) -> None:
        active = self._active
        if (
            active is None
            or event.runtime_id != active.runtime_id
            or event.generation != active.generation
        ):
            self.stale_event_count += 1
            raise StaleRuntimeEventError(event.message_id)

    def _remember_event(self, event_key: tuple[str, int, str]) -> None:
        self._seen_event_ids.add(event_key)
        self._seen_event_order.append(event_key)
        while len(self._seen_event_order) > self._max_seen_event_ids:
            self._seen_event_ids.discard(self._seen_event_order.popleft())

    def drain_events(self) -> tuple[RuntimeEventFrame, ...]:
        with self._lock:
            drained: list[RuntimeEventFrame] = []
            while not self._queue.empty():
                drained.append(self._queue.get_nowait())
            return tuple(drained)

    def create_command(
        self,
        name: CommandName,
        payload: JsonObject,
        *,
        world_revision: int,
        cause_id: str | None = None,
    ) -> RuntimeCommandFrame:
        """Create one command for the active authority with readiness gating."""
        with self._lock:
            connection = self._active
            if connection is None:
                raise RuntimeSessionNotReadyError("runtime is not connected")
            if name is not CommandName.CONFIGURE_WORLD:
                self.ensure_ready_for_command(world_revision=world_revision)
            body_lane = name in {
                CommandName.EXECUTE_INTENT,
                CommandName.CANCEL_INTENT,
            }
            target_actor_id = str(payload.get("actor_id", "")) if body_lane else None
            self._command_sequence += 1
            return RuntimeCommandFrame(
                protocol=3,
                kind="command",
                lane=SemanticLane.BODY if body_lane else SemanticLane.NEST,
                name=name,
                message_id=(
                    f"{connection.runtime_id}-{connection.generation}-"
                    f"command-{self._command_sequence:06d}"
                ),
                runtime_id=connection.runtime_id,
                generation=connection.generation,
                world_revision=world_revision,
                issued_at=datetime.now(timezone.utc),
                cause_id=cause_id,
                target_actor_id=target_actor_id,
                payload=payload,
            )

    def _require_active(self, connection: RuntimeConnection) -> None:
        if self._active != connection:
            self.stale_event_count += 1
            raise StaleRuntimeEventError(connection.runtime_id)
