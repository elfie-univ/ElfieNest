"""Bounded conversation history and trusted endpoint resolution for Brain."""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import timedelta
from threading import Lock
from typing import Deque, Mapping, Tuple

from elfie.brain.memory.memory_records import ClosedEpisode, SourceReference
from elfie.brain.memory.node_types import JsonValue
from elfie.brain.reasoning.context_types import (
    CompletedConversationInteraction,
    ConversationContext,
    ConversationContextCheckpoint,
    ConversationMessage,
    ConversationThreadCheckpoint,
)
from elfie.brain.workspace.contracts import SocialPayload, TurnFrame
from elfie.message_types import ActorRef, EventId, UTCDateTime


@dataclass
class _TopicThread:
    """Mutable working-context topic owned by the Brain owner thread."""

    channel_id: str
    conversation_id: str
    thread_id: str
    messages: list[ConversationMessage] = field(default_factory=list)
    started_at: UTCDateTime | None = None
    last_activity_at: UTCDateTime | None = None


_TOPIC_SHIFT_MARKERS = (
    "换个话题",
    "换一个话题",
    "另外说",
    "另外聊",
    "顺便问",
    "说到另一个",
    "new topic",
    "change the subject",
)
_TOPIC_END_MARKERS = (
    "先这样",
    "就这样吧",
    "聊到这里",
    "结束这个话题",
    "bye",
    "goodbye",
)


class ConversationContextStore:
    """Own short conversation history without becoming long-term Memory."""

    def __init__(
        self,
        *,
        history_capacity: int = 32,
        event_identity_capacity: int = 2048,
        conversations_per_channel: int = 128,
        topic_idle_seconds: float = 1800.0,
        topic_max_messages: int = 24,
        topic_max_characters: int = 12000,
    ) -> None:
        self._history_capacity = history_capacity
        self._event_identity_capacity = event_identity_capacity
        self._conversations_per_channel = conversations_per_channel
        if topic_idle_seconds <= 0:
            raise ValueError("topic_idle_seconds must be positive")
        if topic_max_messages < 1 or topic_max_characters < 1:
            raise ValueError("topic limits must be positive")
        self._topic_idle = timedelta(seconds=topic_idle_seconds)
        self._topic_max_messages = topic_max_messages
        self._topic_max_characters = topic_max_characters
        self._histories: dict[tuple[str, str], Deque[ConversationMessage]] = {}
        self._topics: dict[tuple[str, str], _TopicThread] = {}
        self._closed_episodes: OrderedDict[str, ClosedEpisode] = OrderedDict()
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
                self._close_idle_topics(event.meta.occurred_at)
                topic = self._topics.get(active_key)
                if topic is not None and self._starts_new_topic(
                    topic, payload.content, event.meta.occurred_at
                ):
                    self._close_topic(topic)
                    topic = None
                if topic is None:
                    topic = _TopicThread(
                        channel_id=payload.channel_id,
                        conversation_id=payload.conversation_id,
                        thread_id=f"topic:{event.meta.event_id}",
                        started_at=event.meta.occurred_at,
                    )
                    self._topics[active_key] = topic
                message = ConversationMessage(
                    event_id=event.meta.event_id,
                    sender=payload.sender,
                    occurred_at=event.meta.occurred_at,
                    content=payload.content,
                )
                if self._topic_would_overflow(topic, payload.content):
                    self._close_topic(topic)
                    topic = _TopicThread(
                        channel_id=payload.channel_id,
                        conversation_id=payload.conversation_id,
                        thread_id=f"topic:{event.meta.event_id}",
                        started_at=event.meta.occurred_at,
                    )
                    self._topics[active_key] = topic
                topic.messages.append(message)
                topic.last_activity_at = event.meta.occurred_at
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
                if self._ends_topic(payload.content):
                    self._close_topic(topic)
            messages = tuple(self._histories.get(active_key, ())) if active_key else ()
        unique = tuple(dict.fromkeys(conversation_ids))
        return ConversationContext(
            revision=frame.revision,
            captured_at=captured_at,
            conversation_id=unique[0] if len(unique) == 1 else None,
            messages=messages,
        )

    def pending_closed_episodes(self) -> Tuple[ClosedEpisode, ...]:
        """Return closed source Episodes awaiting acknowledgement by Memory."""
        with self._lock:
            return tuple(self._closed_episodes.values())

    def ack_closed_episodes(self, episode_ids: Tuple[str, ...]) -> None:
        """Remove only source Episodes successfully handed to Memory."""
        with self._lock:
            for episode_id in episode_ids:
                self._closed_episodes.pop(episode_id, None)

    def close_topics(
        self, *, captured_at: UTCDateTime | None = None
    ) -> Tuple[ClosedEpisode, ...]:
        """Explicitly close active topics at an upstream boundary."""
        with self._lock:
            topics = tuple(self._topics.values())
            for topic in topics:
                self._close_topic(topic, closed_at=captured_at)
            return tuple(self._closed_episodes.values())

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

        The causal conversation participant may be the owner, another person,
        or another Elfie.  Attribution is retained on the source message;
        delivery success, rather than a hard-coded owner check, decides
        whether the interaction can enter working history.
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
                    topic_thread_id=(
                        self._topics[(channel_id, conversation_id)].thread_id
                        if (channel_id, conversation_id) in self._topics
                        else None
                    ),
                    topic_messages=(
                        tuple(self._topics[(channel_id, conversation_id)].messages)
                        if (channel_id, conversation_id) in self._topics
                        else ()
                    ),
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
        if any(
            len(thread.topic_messages) > self._topic_max_messages
            or sum(len(message.content) for message in thread.topic_messages)
            > self._topic_max_characters
            for thread in checkpoint.threads
        ):
            raise ValueError("conversation checkpoint exceeds topic capacity")
        topic_ids = tuple(
            thread.topic_thread_id
            for thread in checkpoint.threads
            if thread.topic_thread_id is not None
        )
        if len(topic_ids) != len(set(topic_ids)):
            raise ValueError("conversation checkpoint topic IDs must be unique")
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
            self._topics.clear()
            for thread in checkpoint.threads:
                key = (thread.channel_id, thread.conversation_id)
                self._histories[key] = deque(
                    thread.messages,
                    maxlen=self._history_capacity,
                )
                if thread.topic_thread_id is not None and thread.topic_messages:
                    self._topics[key] = _TopicThread(
                        channel_id=thread.channel_id,
                        conversation_id=thread.conversation_id,
                        thread_id=thread.topic_thread_id,
                        messages=list(thread.topic_messages),
                        started_at=thread.topic_messages[0].occurred_at,
                        last_activity_at=thread.topic_messages[-1].occurred_at,
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

    def _close_idle_topics(self, at: UTCDateTime) -> None:
        for topic in tuple(self._topics.values()):
            if topic.last_activity_at is None:
                continue
            if at - topic.last_activity_at >= self._topic_idle:
                self._close_topic(topic, closed_at=topic.last_activity_at)

    def _starts_new_topic(
        self,
        topic: _TopicThread,
        content: str,
        at: UTCDateTime,
    ) -> bool:
        if (
            topic.last_activity_at is not None
            and at - topic.last_activity_at >= self._topic_idle
        ):
            return True
        folded = content.casefold()
        return any(marker.casefold() in folded for marker in _TOPIC_SHIFT_MARKERS)

    def _topic_would_overflow(self, topic: _TopicThread, content: str) -> bool:
        return len(topic.messages) >= self._topic_max_messages or (
            sum(len(message.content) for message in topic.messages) + len(content)
            > self._topic_max_characters
        )

    @staticmethod
    def _ends_topic(content: str) -> bool:
        folded = content.casefold().strip()
        return any(folded.endswith(marker.casefold()) for marker in _TOPIC_END_MARKERS)

    def _close_topic(
        self,
        topic: _TopicThread,
        *,
        closed_at: UTCDateTime | None = None,
    ) -> None:
        if not topic.messages:
            self._topics.pop((topic.channel_id, topic.conversation_id), None)
            return
        first = topic.messages[0]
        last = topic.messages[-1]
        end = closed_at or last.occurred_at
        episode_id = f"episode:{topic.thread_id}"
        participants: list[JsonValue] = list(
            dict.fromkeys(str(message.sender.actor_id) for message in topic.messages)
        )
        content = "\n".join(
            f"[{message.sender.source_kind}:{message.sender.actor_id}] {message.content}"
            for message in topic.messages
        )
        self._closed_episodes.setdefault(
            episode_id,
            ClosedEpisode(
                episode_id=episode_id,
                idempotency_key=episode_id,
                occurred_from=first.occurred_at.isoformat(),
                occurred_to=end.isoformat(),
                occurrence_precision="range",
                content_text=content,
                event_kind="conversation_episode",
                source_refs=tuple(
                    SourceReference(
                        source_id=str(message.event_id),
                        source_kind=message.sender.source_kind,
                        locator=f"{topic.channel_id}:{topic.conversation_id}",
                    )
                    for message in topic.messages
                ),
                source_event_ids=tuple(
                    str(message.event_id) for message in topic.messages
                ),
                metadata={
                    "channel_id": topic.channel_id,
                    "conversation_id": topic.conversation_id,
                    "topic_id": topic.thread_id,
                    "participants": participants,
                },
            ),
        )
        self._topics.pop((topic.channel_id, topic.conversation_id), None)

    def _remember_conversation(self, channel_id: str, conversation_id: str) -> None:
        conversations = self._authorized_conversations.setdefault(channel_id, deque())
        if conversation_id in conversations:
            return
        conversations.append(conversation_id)
        while len(conversations) > self._conversations_per_channel:
            conversations.popleft()


__all__ = ("ConversationContextStore",)
