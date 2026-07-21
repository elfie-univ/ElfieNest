"""精灵完整通信 envelope 的线程安全收件箱。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Deque, List, Optional, Set, Tuple

from elfie.communication.contracts import CommunicationEnvelope, MessageDirection


@dataclass(frozen=True, slots=True)
class InboxDirectionError(ValueError):
    """An outbound envelope was offered to the inbound store."""

    direction: MessageDirection

    def __str__(self) -> str:
        return f"inbox only accepts inbound envelopes, got {self.direction.value}"


class CommunicationInbox:
    """Canonical envelope storage with an atomic replay identity boundary."""

    def __init__(self) -> None:
        self._pending: Deque[CommunicationEnvelope] = deque()
        self._history: List[CommunicationEnvelope] = []
        self._seen_identities: Set[Tuple[str, str]] = set()
        self._lock = Lock()

    def claim_identity(self, envelope: CommunicationEnvelope) -> bool:
        """Atomically reserve dedupe and external identities once."""
        identities = [("dedupe", envelope.dedupe_key)]
        if envelope.external_message_id is not None:
            identities.append(("external", envelope.external_message_id))
        with self._lock:
            if any(identity in self._seen_identities for identity in identities):
                return False
            self._seen_identities.update(identities)
        return True

    def receive(self, envelope: CommunicationEnvelope) -> None:
        """Store a validated, admitted inbound envelope."""
        if envelope.direction is not MessageDirection.INBOUND:
            raise InboxDirectionError(direction=envelope.direction)
        with self._lock:
            self._pending.append(envelope)
            self._history.append(envelope)

    def mark_cognitive_delivery(self, envelope: CommunicationEnvelope) -> bool:
        """Remove an envelope after the perception boundary retains it."""
        with self._lock:
            try:
                self._pending.remove(envelope)
            except ValueError:
                return False
        return True

    def drain(self, limit: Optional[int] = None) -> List[CommunicationEnvelope]:
        """Remove up to ``limit`` pending envelopes in arrival order."""
        with self._lock:
            count = len(self._pending) if limit is None else max(0, limit)
            messages = []
            while self._pending and len(messages) < count:
                messages.append(self._pending.popleft())
        return messages

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    @property
    def history(self) -> List[CommunicationEnvelope]:
        with self._lock:
            return list(self._history)


__all__ = ("CommunicationInbox", "InboxDirectionError")
