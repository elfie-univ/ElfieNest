"""精灵完整通信 envelope 的线程安全收件箱。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum, unique
from threading import Lock
from typing import Deque, Optional, Set, Tuple

from elfie.communication.contracts import CommunicationEnvelope, MessageDirection


@dataclass(frozen=True)
class InboxDirectionError(ValueError):
    """An outbound envelope was offered to the inbound store."""

    direction: MessageDirection

    def __str__(self) -> str:
        return f"inbox only accepts inbound envelopes, got {self.direction.value}"


@dataclass(frozen=True)
class CommunicationInboxMetrics:
    """Bounded storage counters exposed for long-running runtime checks."""

    pending_count: int
    history_count: int
    seen_identity_count: int
    evicted_history_count: int
    evicted_identity_count: int
    closed: bool


@unique
class InboxAdmitStatus(str, Enum):
    """Atomic inbound admission outcome."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    FULL = "full"
    CLOSED = "closed"


class CommunicationInbox:
    """Canonical envelope storage with an atomic replay identity boundary."""

    def __init__(
        self,
        *,
        max_pending: int = 512,
        history_capacity: int = 1024,
        dedupe_capacity: int = 4096,
    ) -> None:
        self._pending: Deque[CommunicationEnvelope] = deque()
        self._history: Deque[CommunicationEnvelope] = deque()
        self._seen_identities: Set[Tuple[str, str]] = set()
        self._identity_order: Deque[Tuple[str, str]] = deque()
        self._max_pending = max_pending
        self._history_capacity = history_capacity
        self._dedupe_capacity = dedupe_capacity
        self._evicted_history_count = 0
        self._evicted_identity_count = 0
        self._closed = False
        self._lock = Lock()

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def claim_identity(self, envelope: CommunicationEnvelope) -> bool:
        """Atomically reserve dedupe and external identities once."""
        identities = self._identities(envelope)
        with self._lock:
            if self._closed or self._pending_full:
                return False
            if any(identity in self._seen_identities for identity in identities):
                return False
            for identity in identities:
                self._remember_identity(identity)
        return True

    def admit(self, envelope: CommunicationEnvelope) -> InboxAdmitStatus:
        """Atomically dedupe, reserve, and store one inbound envelope."""
        if envelope.direction is not MessageDirection.INBOUND:
            raise InboxDirectionError(direction=envelope.direction)
        identities = self._identities(envelope)
        with self._lock:
            if self._closed:
                return InboxAdmitStatus.CLOSED
            if any(identity in self._seen_identities for identity in identities):
                return InboxAdmitStatus.DUPLICATE
            if self._pending_full:
                return InboxAdmitStatus.FULL
            for identity in identities:
                self._remember_identity(identity)
            self._receive_locked(envelope)
        return InboxAdmitStatus.ACCEPTED

    def has_identity(self, envelope: CommunicationEnvelope) -> bool:
        """Return whether any replay identity was already admitted."""
        identities = self._identities(envelope)
        with self._lock:
            return any(identity in self._seen_identities for identity in identities)

    def receive(self, envelope: CommunicationEnvelope) -> None:
        """Store a validated, admitted inbound envelope."""
        if envelope.direction is not MessageDirection.INBOUND:
            raise InboxDirectionError(direction=envelope.direction)
        with self._lock:
            if self._closed:
                return
            self._receive_locked(envelope)

    def mark_cognitive_delivery(self, envelope: CommunicationEnvelope) -> bool:
        """Remove an envelope after the perception boundary retains it."""
        with self._lock:
            try:
                self._pending.remove(envelope)
            except ValueError:
                return False
        return True

    def drain(self, limit: Optional[int] = None) -> list[CommunicationEnvelope]:
        """Remove up to ``limit`` pending envelopes in arrival order."""
        with self._lock:
            count = len(self._pending) if limit is None else max(0, limit)
            messages: list[CommunicationEnvelope] = []
            while self._pending and len(messages) < count:
                messages.append(self._pending.popleft())
        return messages

    def close(self) -> None:
        """Reject future inbound storage and release pending retries."""
        with self._lock:
            self._closed = True
            self._pending.clear()

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    @property
    def history(self) -> list[CommunicationEnvelope]:
        with self._lock:
            return list(self._history)

    def metrics(self) -> CommunicationInboxMetrics:
        with self._lock:
            return CommunicationInboxMetrics(
                pending_count=len(self._pending),
                history_count=len(self._history),
                seen_identity_count=len(self._seen_identities),
                evicted_history_count=self._evicted_history_count,
                evicted_identity_count=self._evicted_identity_count,
                closed=self._closed,
            )

    @property
    def _pending_full(self) -> bool:
        return len(self._pending) >= self._max_pending

    def _remember_identity(self, identity: Tuple[str, str]) -> None:
        if identity in self._seen_identities:
            return
        if len(self._identity_order) >= self._dedupe_capacity:
            evicted = self._identity_order.popleft()
            self._seen_identities.discard(evicted)
            self._evicted_identity_count += 1
        self._seen_identities.add(identity)
        self._identity_order.append(identity)

    def _receive_locked(self, envelope: CommunicationEnvelope) -> None:
        self._pending.append(envelope)
        if len(self._history) >= self._history_capacity:
            self._history.popleft()
            self._evicted_history_count += 1
        self._history.append(envelope)

    @staticmethod
    def _identities(
        envelope: CommunicationEnvelope,
    ) -> list[Tuple[str, str]]:
        identities = [("dedupe", envelope.dedupe_key)]
        if envelope.external_message_id is not None:
            identities.append(("external", envelope.external_message_id))
        return identities


__all__ = (
    "CommunicationInbox",
    "CommunicationInboxMetrics",
    "InboxAdmitStatus",
    "InboxDirectionError",
)
