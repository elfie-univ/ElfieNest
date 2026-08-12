"""Bounded conversation history and trusted endpoint resolution for Brain."""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Deque, Mapping, Tuple

from elfie.brain.reasoning.context_types import ConversationContext, ConversationMessage
from elfie.brain.workspace.contracts import SocialPayload, TurnFrame
from elfie.message_types import EventId, UTCDateTime


class ConversationContextStore:
    """Own short conversation history without becoming long-term Memory."""

    def __init__(
        self,
        *,
        history_capacity: int = 32,
        event_identity_capacity: int = 2048,
        conversations_per_channel: int = 128,
    ) -> None:
        self._history_capacity = history_capacity
        self._event_identity_capacity = event_identity_capacity
        self._conversations_per_channel = conversations_per_channel
        self._histories: dict[tuple[str, str], Deque[ConversationMessage]] = {}
        self._seen_events: set[EventId] = set()
        self._seen_order: Deque[EventId] = deque()
        self._authorized_conversations: dict[str, Deque[str]] = {}
        self._authorized_targets: dict[tuple[str, str], set[str]] = {}
        self._lock = Lock()

    def observe(
        self,
        frame: TurnFrame,
        captured_at: UTCDateTime,
    ) -> ConversationContext:
        """Record admitted conversation events once and return bounded history."""
        conversation_ids: list[str] = []
        active_key: tuple[str, str] | None = None
        with self._lock:
            for event in frame.events:
                payload = event.payload
                if not isinstance(payload, SocialPayload):
                    continue
                conversation_ids.append(payload.conversation_id)
                active_key = (payload.channel_id, payload.conversation_id)
                self._remember_conversation(*active_key)
                self._authorized_targets.setdefault(active_key, set()).add(
                    str(payload.sender.actor_id)
                )
                if event.meta.event_id in self._seen_events:
                    continue
                history = self._histories.setdefault(
                    active_key,
                    deque(maxlen=self._history_capacity),
                )
                history.append(
                    ConversationMessage(
                        event_id=event.meta.event_id,
                        sender=payload.sender,
                        occurred_at=event.meta.occurred_at,
                        content=payload.content,
                    )
                )
                self._remember_seen(event.meta.event_id)
            messages = tuple(self._histories.get(active_key, ())) if active_key else ()
        unique = tuple(dict.fromkeys(conversation_ids))
        return ConversationContext(
            revision=frame.revision,
            captured_at=captured_at,
            conversation_id=unique[0] if len(unique) == 1 else None,
            messages=messages,
        )

    def authorization_map(self) -> Mapping[str, Tuple[str, ...]]:
        """Return a copy safe for capability projection."""
        with self._lock:
            return {
                channel_id: tuple(conversations)
                for channel_id, conversations in self._authorized_conversations.items()
            }

    def can_reach_actor(
        self,
        actor_id: str,
        channel_id: str,
        conversation_id: str,
    ) -> bool:
        with self._lock:
            return actor_id in self._authorized_targets.get(
                (channel_id, conversation_id), set()
            )

    def _remember_seen(self, event_id: EventId) -> None:
        self._seen_events.add(event_id)
        self._seen_order.append(event_id)
        while len(self._seen_order) > self._event_identity_capacity:
            self._seen_events.discard(self._seen_order.popleft())

    def _remember_conversation(self, channel_id: str, conversation_id: str) -> None:
        conversations = self._authorized_conversations.setdefault(channel_id, deque())
        if conversation_id in conversations:
            return
        conversations.append(conversation_id)
        while len(conversations) > self._conversations_per_channel:
            conversations.popleft()


__all__ = ("ConversationContextStore",)
