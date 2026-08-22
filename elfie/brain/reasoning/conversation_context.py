"""Bounded conversation history and trusted endpoint resolution for Brain."""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Deque, Mapping, Tuple

from elfie.brain.reasoning.context_types import (
    CompletedConversationInteraction,
    ConversationContext,
    ConversationContextCheckpoint,
    ConversationMessage,
    ConversationThreadCheckpoint,
)
from elfie.brain.workspace.contracts import SocialPayload, TurnFrame
from elfie.message_types import ActorRef, EventId, UTCDateTime


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

    def record_completed_reply(
        self,
        *,
        channel_id: str,
        conversation_id: str,
        reply_event_id: EventId,
        sender: ActorRef,
        occurred_at: UTCDateTime,
        content: str,
        cause_event_ids: Tuple[EventId, ...],
        receipt_id: EventId,
    ) -> CompletedConversationInteraction | None:
        """Append one reply only after its communication receipt completed.

        A reply without a causal owner message is intentionally excluded from
        owner-chat continuity and long-term interaction Memory.
        """
        key = (channel_id, conversation_id)
        causes = set(cause_event_ids)
        with self._lock:
            if reply_event_id in self._seen_events:
                return None
            history = self._histories.get(key)
            if history is None:
                return None
            owner = next(
                (
                    message
                    for message in reversed(history)
                    if message.event_id in causes
                    and message.sender.source_kind == "owner"
                ),
                None,
            )
            if owner is None:
                return None
            reply = ConversationMessage(
                event_id=reply_event_id,
                sender=sender,
                occurred_at=occurred_at,
                content=content,
            )
            history.append(reply)
            self._remember_seen(reply_event_id)
            self._remember_conversation(channel_id, conversation_id)
        return CompletedConversationInteraction(
            channel_id=channel_id,
            conversation_id=conversation_id,
            owner=owner,
            reply=reply,
            receipt_id=receipt_id,
        )

    def checkpoint(self) -> ConversationContextCheckpoint:
        """Capture bounded alternating history for restart continuity."""
        with self._lock:
            threads = tuple(
                ConversationThreadCheckpoint(
                    channel_id=channel_id,
                    conversation_id=conversation_id,
                    messages=tuple(messages),
                )
                for (channel_id, conversation_id), messages in sorted(
                    self._histories.items()
                )
            )
        return ConversationContextCheckpoint(threads=threads)

    def validate_checkpoint(self, checkpoint: ConversationContextCheckpoint) -> None:
        """Reject duplicate endpoints or histories beyond configured bounds."""
        keys = tuple(
            (thread.channel_id, thread.conversation_id) for thread in checkpoint.threads
        )
        if len(keys) != len(set(keys)):
            raise ValueError("conversation checkpoint endpoints must be unique")
        if any(
            len(thread.messages) > self._history_capacity
            for thread in checkpoint.threads
        ):
            raise ValueError("conversation checkpoint exceeds history capacity")
        per_channel: dict[str, int] = {}
        for channel_id, _conversation_id in keys:
            per_channel[channel_id] = per_channel.get(channel_id, 0) + 1
        if any(
            count > self._conversations_per_channel for count in per_channel.values()
        ):
            raise ValueError("conversation checkpoint exceeds channel capacity")
        event_ids = tuple(
            message.event_id
            for thread in checkpoint.threads
            for message in thread.messages
        )
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("conversation checkpoint event IDs must be unique")

    def restore(self, checkpoint: ConversationContextCheckpoint) -> None:
        """Replace stopped-store state from one validated checkpoint."""
        self.validate_checkpoint(checkpoint)
        with self._lock:
            self._histories.clear()
            self._seen_events.clear()
            self._seen_order.clear()
            self._authorized_conversations.clear()
            self._authorized_targets.clear()
            for thread in checkpoint.threads:
                key = (thread.channel_id, thread.conversation_id)
                self._histories[key] = deque(
                    thread.messages,
                    maxlen=self._history_capacity,
                )
                self._remember_conversation(*key)
                targets = self._authorized_targets.setdefault(key, set())
                targets.update(
                    str(message.sender.actor_id)
                    for message in thread.messages
                    if message.sender.source_kind != "elfie"
                )
            messages = sorted(
                (
                    message
                    for thread in checkpoint.threads
                    for message in thread.messages
                ),
                key=lambda message: message.occurred_at,
            )
            for message in messages:
                self._remember_seen(message.event_id)

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
