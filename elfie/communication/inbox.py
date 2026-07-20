"""精灵的网络消息收件箱。"""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Deque, List, Optional

from elfie.communication.channel import CommunicationMessage, MessageDirection


class CommunicationInbox:
    def __init__(self) -> None:
        self._pending: Deque[CommunicationMessage] = deque()
        self._history: List[CommunicationMessage] = []
        self._lock = Lock()

    def receive(self, message: CommunicationMessage) -> None:
        if message.direction is not MessageDirection.INBOUND:
            raise ValueError("收件箱只接受 inbound 消息")
        with self._lock:
            self._pending.append(message)
            self._history.append(message)

    def drain(self, limit: Optional[int] = None) -> List[CommunicationMessage]:
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
    def history(self) -> List[CommunicationMessage]:
        with self._lock:
            return list(self._history)
