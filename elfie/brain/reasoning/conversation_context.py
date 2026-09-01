"""Bounded conversation history and trusted endpoint resolution for Brain."""

from __future__ import annotations

import json
from collections import OrderedDict, deque
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from threading import Lock
from typing import Deque, Mapping, Tuple

from elfie.brain.memory.memory_records import (
    ClosedEpisode,
    JsonValue,
    MediaReference,
    SourceReference,
)
from elfie.brain.reasoning.context_types import (
    CompletedConversationInteraction,
    ContextSummary,
    ConversationContext,
    ConversationContextCheckpoint,
    ConversationMessage,
    ConversationThreadCheckpoint,
    ConversationTopicCheckpoint,
    PendingReplyProjection,
)
from elfie.brain.workspace.contracts import ExecutionStatus, SocialPayload, TurnFrame
from elfie.message_types import ActorRef, EventId, IntentId, UTCDateTime


@dataclass
class _TopicThread:
    """Mutable working-context topic owned by the Brain owner thread."""

    channel_id: str
    conversation_id: str
    thread_id: str
    lineage_id: str
    messages: list[ConversationMessage] = field(default_factory=list)
    summaries: list[ContextSummary] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    started_at: UTCDateTime | None = None
    last_activity_at: UTCDateTime | None = None
    close_after_event_id: EventId | None = None


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


class ReasoningContextWorkspace:
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
        summary_capacity: int = 8,
    ) -> None:
        self._history_capacity = history_capacity
        self._event_identity_capacity = event_identity_capacity
        self._conversations_per_channel = conversations_per_channel
        if topic_idle_seconds <= 0:
            raise ValueError("topic_idle_seconds must be positive")
        if history_capacity < 1 or summary_capacity < 1:
            raise ValueError("history and summary capacities must be positive")
        if topic_max_messages < 2 or topic_max_characters < 1:
            raise ValueError("topic limits must be positive")
        self._topic_idle = timedelta(seconds=topic_idle_seconds)
        self._topic_max_messages = topic_max_messages
        self._topic_max_characters = topic_max_characters
        self._summary_capacity = summary_capacity
        self._histories: dict[tuple[str, str], Deque[ConversationMessage]] = {}
        self._summaries: dict[tuple[str, str], list[ContextSummary]] = {}
        self._topics: dict[tuple[str, str], _TopicThread] = {}
        self._pending_topics: dict[
            tuple[str, str], OrderedDict[EventId, _TopicThread]
        ] = {}
        self._pending_replies: OrderedDict[str, PendingReplyProjection] = OrderedDict()
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
                close_after_reply = topic is not None and self._starts_new_topic(
                    topic, payload.content, event.meta.occurred_at
                )
                if topic is None:
                    thread_id = f"topic:{event.meta.event_id}"
                    topic = _TopicThread(
                        channel_id=payload.channel_id,
                        conversation_id=payload.conversation_id,
                        thread_id=thread_id,
                        lineage_id=thread_id,
                        started_at=event.meta.occurred_at,
                    )
                    self._topics[active_key] = topic
                message = ConversationMessage(
                    event_id=event.meta.event_id,
                    sender=payload.sender,
                    occurred_at=event.meta.occurred_at,
                    content=payload.content,
                )
                topic.messages.append(message)
                participant = str(payload.sender.actor_id)
                if participant not in topic.participants:
                    topic.participants.append(participant)
                topic.last_activity_at = event.meta.occurred_at
                self._compact_topic(active_key, topic)
                self._append_history(active_key, message)
                self._remember_seen(event.meta.event_id)
                if close_after_reply or self._ends_topic(payload.content):
                    self._mark_topic_pending_close(topic, event.meta.event_id)
            messages = tuple(self._histories.get(active_key, ())) if active_key else ()
            summaries = tuple(self._summaries.get(active_key, ())) if active_key else ()
            active_topic = self._topics.get(active_key) if active_key else None
        unique = tuple(dict.fromkeys(conversation_ids))
        return ConversationContext(
            revision=frame.revision,
            captured_at=captured_at,
            conversation_id=unique[0] if len(unique) == 1 else None,
            messages=messages,
            summaries=summaries,
            active_topic_messages=(
                tuple(active_topic.messages) if active_topic is not None else ()
            ),
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
            topics = tuple(self._topics.values()) + tuple(
                topic
                for pending in self._pending_topics.values()
                for topic in pending.values()
            )
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

    def prepare_reply(
        self,
        *,
        intent_id: IntentId,
        channel_id: str,
        conversation_id: str,
        reply_event_id: EventId,
        content: str,
        cause_event_ids: Tuple[EventId, ...],
        prepared_at: UTCDateTime,
    ) -> bool:
        """Persist one reply proposal before external execution begins."""
        projection = PendingReplyProjection(
            intent_id=intent_id,
            channel_id=channel_id,
            conversation_id=conversation_id,
            reply_event_id=reply_event_id,
            content=content,
            cause_event_ids=cause_event_ids,
            prepared_at=prepared_at,
        )
        key = str(intent_id)
        with self._lock:
            existing = self._pending_replies.get(key)
            if existing is not None:
                if existing != projection:
                    raise ValueError(
                        "reply intent ID was reused with different content"
                    )
                return False
            self._pending_replies[key] = projection
            return True

    def settle_reply(
        self,
        *,
        intent_id: IntentId,
        status: ExecutionStatus,
        receipt_id: EventId,
        occurred_at: UTCDateTime,
        sender: ActorRef,
    ) -> CompletedConversationInteraction | None:
        """Join a prepared reply to history only after a terminal Receipt."""
        terminal = {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.REJECTED,
            ExecutionStatus.FAILED,
            ExecutionStatus.INTERRUPTED,
            ExecutionStatus.TIMED_OUT,
            ExecutionStatus.CANCELLED,
        }
        if status not in terminal:
            return None
        with self._lock:
            projection = self._pending_replies.pop(str(intent_id), None)
            if projection is None:
                return None
            interaction = self._settle_projection_locked(
                projection,
                completed=status is ExecutionStatus.COMPLETED,
                receipt_id=receipt_id,
                occurred_at=occurred_at,
                sender=sender,
            )
            self._close_pending_topics_for(projection.cause_event_ids, occurred_at)
            return interaction

    def discard_pending_reply(
        self,
        intent_id: IntentId,
        *,
        occurred_at: UTCDateTime,
    ) -> bool:
        """Close an uncertain restart projection without inventing delivery."""
        with self._lock:
            projection = self._pending_replies.pop(str(intent_id), None)
            if projection is None:
                return False
            self._close_pending_topics_for(projection.cause_event_ids, occurred_at)
            return True

    def pending_reply_ids(self) -> Tuple[str, ...]:
        """Return stable pending identities for restart reconciliation."""
        with self._lock:
            return tuple(self._pending_replies)

    def _settle_projection_locked(
        self,
        projection: PendingReplyProjection,
        *,
        completed: bool,
        receipt_id: EventId,
        occurred_at: UTCDateTime,
        sender: ActorRef,
    ) -> CompletedConversationInteraction | None:
        if not completed:
            return None
        channel_id = projection.channel_id
        conversation_id = projection.conversation_id
        reply_event_id = projection.reply_event_id
        content = projection.content
        cause_event_ids = projection.cause_event_ids
        key = (channel_id, conversation_id)
        causes = set(cause_event_ids)
        if reply_event_id in self._seen_events:
            return None
        history = self._histories.get(key)
        if history is None:
            return None
        owner = next(
            (message for message in reversed(history) if message.event_id in causes),
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
        self._append_history(key, reply)
        topic = self._topic_for_causes(key, causes)
        if topic is not None:
            topic.messages.append(reply)
            participant = str(sender.actor_id)
            if participant not in topic.participants:
                topic.participants.append(participant)
            topic.last_activity_at = occurred_at
            self._compact_topic(key, topic)
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
            keys = set(self._histories) | set(self._summaries) | set(self._topics)
            keys.update(self._pending_topics)
            threads = tuple(
                ConversationThreadCheckpoint(
                    channel_id=channel_id,
                    conversation_id=conversation_id,
                    messages=tuple(
                        self._histories.get((channel_id, conversation_id), ())
                    ),
                    summaries=tuple(
                        self._summaries.get((channel_id, conversation_id), ())
                    ),
                    active_topic=(
                        self._topic_checkpoint(
                            self._topics[(channel_id, conversation_id)]
                        )
                        if (channel_id, conversation_id) in self._topics
                        else None
                    ),
                    pending_topics=tuple(
                        self._topic_checkpoint(topic)
                        for topic in self._pending_topics.get(
                            (channel_id, conversation_id), {}
                        ).values()
                    ),
                )
                for channel_id, conversation_id in sorted(keys)
            )
            pending_replies = tuple(self._pending_replies.values())
            pending_episode_payloads = tuple(
                self._episode_payload(episode)
                for episode in self._closed_episodes.values()
            )
        return ConversationContextCheckpoint(
            threads=threads,
            pending_replies=pending_replies,
            pending_closed_episode_payloads=pending_episode_payloads,
        )

    @staticmethod
    def _topic_checkpoint(topic: _TopicThread) -> ConversationTopicCheckpoint:
        return ConversationTopicCheckpoint(
            thread_id=topic.thread_id,
            lineage_id=topic.lineage_id,
            messages=tuple(topic.messages),
            summaries=tuple(topic.summaries),
            started_at=topic.started_at,
            last_activity_at=topic.last_activity_at,
            close_after_event_id=topic.close_after_event_id,
            participants=tuple(topic.participants),
        )

    @staticmethod
    def _restore_topic(
        channel_id: str,
        conversation_id: str,
        checkpoint: ConversationTopicCheckpoint,
    ) -> _TopicThread:
        return _TopicThread(
            channel_id=channel_id,
            conversation_id=conversation_id,
            thread_id=checkpoint.thread_id,
            lineage_id=checkpoint.lineage_id,
            messages=list(checkpoint.messages),
            summaries=list(checkpoint.summaries),
            participants=list(checkpoint.participants),
            started_at=checkpoint.started_at,
            last_activity_at=checkpoint.last_activity_at,
            close_after_event_id=checkpoint.close_after_event_id,
        )

    def validate_checkpoint(self, checkpoint: ConversationContextCheckpoint) -> None:
        """Reject duplicate endpoints or state beyond configured bounds."""
        keys = tuple(
            (thread.channel_id, thread.conversation_id) for thread in checkpoint.threads
        )
        if len(keys) != len(set(keys)):
            raise ValueError("conversation checkpoint endpoints must be unique")
        if any(
            len(thread.messages) > self._history_capacity
            or len(thread.summaries) > self._summary_capacity
            for thread in checkpoint.threads
        ):
            raise ValueError("conversation checkpoint exceeds context capacity")
        topics = tuple(
            topic
            for thread in checkpoint.threads
            for topic in (
                ((thread.active_topic,) if thread.active_topic is not None else ())
                + thread.pending_topics
            )
        )
        if any(
            len(topic.messages) > self._topic_max_messages
            or sum(len(message.content) for message in topic.messages)
            > self._topic_max_characters
            or len(topic.summaries) > self._summary_capacity
            for topic in topics
        ):
            raise ValueError("conversation checkpoint exceeds topic capacity")
        topic_ids = tuple(topic.thread_id for topic in topics)
        if len(topic_ids) != len(set(topic_ids)):
            raise ValueError("conversation checkpoint topic IDs must be unique")
        pending_close_ids = tuple(
            topic.close_after_event_id
            for topic in topics
            if topic.close_after_event_id is not None
        )
        if len(pending_close_ids) != len(set(pending_close_ids)):
            raise ValueError("pending topic close event IDs must be unique")
        pending_reply_ids = tuple(
            str(reply.intent_id) for reply in checkpoint.pending_replies
        )
        if len(pending_reply_ids) != len(set(pending_reply_ids)):
            raise ValueError("pending reply intent IDs must be unique")
        episodes = tuple(
            self._episode_from_payload(payload)
            for payload in checkpoint.pending_closed_episode_payloads
        )
        episode_ids = tuple(episode.episode_id for episode in episodes)
        if len(episode_ids) != len(set(episode_ids)):
            raise ValueError("pending closed Episode IDs must be unique")
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
            self._summaries.clear()
            self._seen_events.clear()
            self._seen_order.clear()
            self._authorized_conversations.clear()
            self._authorized_targets.clear()
            self._topics.clear()
            self._pending_topics.clear()
            self._pending_replies = OrderedDict(
                (str(reply.intent_id), reply) for reply in checkpoint.pending_replies
            )
            self._closed_episodes = OrderedDict(
                (episode.episode_id, episode)
                for episode in (
                    self._episode_from_payload(payload)
                    for payload in checkpoint.pending_closed_episode_payloads
                )
            )
            for thread in checkpoint.threads:
                key = (thread.channel_id, thread.conversation_id)
                self._histories[key] = deque(thread.messages)
                self._summaries[key] = list(thread.summaries)
                if thread.active_topic is not None:
                    self._topics[key] = self._restore_topic(
                        thread.channel_id,
                        thread.conversation_id,
                        thread.active_topic,
                    )
                if thread.pending_topics:
                    pending: OrderedDict[EventId, _TopicThread] = OrderedDict()
                    for topic_checkpoint in thread.pending_topics:
                        if topic_checkpoint.close_after_event_id is None:
                            raise ValueError("pending topic requires a close event")
                        pending[topic_checkpoint.close_after_event_id] = (
                            self._restore_topic(
                                thread.channel_id,
                                thread.conversation_id,
                                topic_checkpoint,
                            )
                        )
                    self._pending_topics[key] = pending
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

    @staticmethod
    def _episode_payload(episode: ClosedEpisode) -> str:
        return json.dumps(
            asdict(episode),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _episode_from_payload(payload: str) -> ClosedEpisode:
        values = json.loads(payload)
        if not isinstance(values, dict):
            raise ValueError("closed Episode checkpoint must be an object")
        values["source_refs"] = tuple(
            SourceReference(**item) for item in values.get("source_refs", ())
        )
        values["media_refs"] = tuple(
            MediaReference(**item) for item in values.get("media_refs", ())
        )
        values["source_event_ids"] = tuple(values.get("source_event_ids", ()))
        values["sensory"] = tuple(tuple(item) for item in values.get("sensory", ()))
        return ClosedEpisode(**values)

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

    def _append_history(
        self,
        key: tuple[str, str],
        message: ConversationMessage,
    ) -> None:
        history = self._histories.setdefault(key, deque())
        history.append(message)
        if len(history) <= self._history_capacity:
            return
        compact_count = max(1, len(history) - self._history_capacity)
        if len(history) - compact_count > 1:
            compact_count = max(2, compact_count)
        compacted = [history.popleft() for _ in range(compact_count)]
        self._add_summary(key, self._summary_from_messages(compacted))

    def _add_summary(
        self,
        key: tuple[str, str],
        summary: ContextSummary,
    ) -> None:
        summaries = self._summaries.setdefault(key, [])
        if any(item.summary_id == summary.summary_id for item in summaries):
            return
        summaries.append(summary)
        while len(summaries) > self._summary_capacity:
            merged = self._merge_summaries(summaries[0], summaries[1])
            summaries[:2] = [merged]

    @staticmethod
    def _summary_from_messages(
        messages: list[ConversationMessage],
    ) -> ContextSummary:
        if not messages:
            raise ValueError("cannot summarize an empty conversation range")
        unresolved = tuple(
            message.content
            for message in messages
            if "?" in message.content
            or "？" in message.content
            or any(
                marker in message.content
                for marker in ("纠正", "更正", "不是", "其实", "冲突", "矛盾")
            )
        )
        first = messages[0]
        last = messages[-1]
        return ContextSummary(
            summary_id=f"context-summary:{first.event_id}:{last.event_id}:v1",
            source_event_ids=tuple(message.event_id for message in messages),
            occurred_from=first.occurred_at,
            occurred_to=last.occurred_at,
            content="\n".join(
                f"[{message.sender.source_kind}:{message.sender.actor_id}] "
                f"{message.content}"
                for message in messages
            ),
            unresolved_items=tuple(dict.fromkeys(unresolved)),
        )

    @staticmethod
    def _merge_summaries(
        first: ContextSummary,
        second: ContextSummary,
    ) -> ContextSummary:
        source_ids = tuple(
            dict.fromkeys(first.source_event_ids + second.source_event_ids)
        )
        return ContextSummary(
            summary_id=(
                f"context-summary:{source_ids[0]}:{source_ids[-1]}:"
                f"v{max(first.version, second.version) + 1}"
            ),
            version=max(first.version, second.version) + 1,
            source_event_ids=source_ids,
            occurred_from=min(first.occurred_from, second.occurred_from),
            occurred_to=max(first.occurred_to, second.occurred_to),
            content=f"{first.content}\n{second.content}",
            unresolved_items=tuple(
                dict.fromkeys(first.unresolved_items + second.unresolved_items)
            ),
        )

    def _compact_topic(
        self,
        key: tuple[str, str],
        topic: _TopicThread,
    ) -> None:
        while topic.messages and (
            len(topic.messages) > self._topic_max_messages
            or sum(len(message.content) for message in topic.messages)
            > self._topic_max_characters
        ):
            compact_count = max(1, len(topic.messages) // 2)
            compacted = topic.messages[:compact_count]
            del topic.messages[:compact_count]
            summary = self._summary_from_messages(compacted)
            topic.summaries.append(summary)
            while len(topic.summaries) > self._summary_capacity:
                merged = self._merge_summaries(topic.summaries[0], topic.summaries[1])
                topic.summaries[:2] = [merged]
            self._add_summary(key, summary)

    def _mark_topic_pending_close(
        self,
        topic: _TopicThread,
        cause_event_id: EventId,
    ) -> None:
        key = (topic.channel_id, topic.conversation_id)
        topic.close_after_event_id = cause_event_id
        self._topics.pop(key, None)
        self._pending_topics.setdefault(key, OrderedDict())[cause_event_id] = topic

    def _topic_for_causes(
        self,
        key: tuple[str, str],
        causes: set[EventId],
    ) -> _TopicThread | None:
        candidates = ((self._topics[key],) if key in self._topics else ()) + tuple(
            self._pending_topics.get(key, {}).values()
        )
        for topic in candidates:
            source_ids = {message.event_id for message in topic.messages} | {
                event_id
                for summary in topic.summaries
                for event_id in summary.source_event_ids
            }
            if source_ids & causes:
                return topic
        return None

    def _close_pending_topics_for(
        self,
        cause_event_ids: Tuple[EventId, ...],
        occurred_at: UTCDateTime,
    ) -> None:
        for cause_event_id in cause_event_ids:
            for key, pending in tuple(self._pending_topics.items()):
                topic = pending.get(cause_event_id)
                if topic is None:
                    continue
                self._close_topic(topic, closed_at=occurred_at)
                if not pending:
                    self._pending_topics.pop(key, None)

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
        if not topic.messages and not topic.summaries:
            self._remove_topic(topic)
            return
        occurred_from = (
            topic.summaries[0].occurred_from
            if topic.summaries
            else topic.messages[0].occurred_at
        )
        occurred_to = (
            topic.messages[-1].occurred_at
            if topic.messages
            else topic.summaries[-1].occurred_to
        )
        end = closed_at or occurred_to
        episode_id = f"episode:{topic.thread_id}"
        participants: list[JsonValue] = list(topic.participants)
        source_event_ids = tuple(
            dict.fromkeys(
                tuple(
                    event_id
                    for summary in topic.summaries
                    for event_id in summary.source_event_ids
                )
                + tuple(message.event_id for message in topic.messages)
            )
        )
        content = "\n".join(
            tuple(summary.content for summary in topic.summaries)
            + tuple(
                f"[{message.sender.source_kind}:{message.sender.actor_id}] "
                f"{message.content}"
                for message in topic.messages
            )
        )
        self._closed_episodes.setdefault(
            episode_id,
            ClosedEpisode(
                episode_id=episode_id,
                idempotency_key=episode_id,
                occurred_from=occurred_from.isoformat(),
                occurred_to=end.isoformat(),
                occurrence_precision="range",
                content_text=content,
                event_kind="conversation_episode",
                source_refs=tuple(
                    SourceReference(
                        source_id=str(event_id),
                        source_kind="conversation",
                        locator=f"{topic.channel_id}:{topic.conversation_id}",
                    )
                    for event_id in source_event_ids
                ),
                source_event_ids=tuple(str(event_id) for event_id in source_event_ids),
                metadata={
                    "channel_id": topic.channel_id,
                    "conversation_id": topic.conversation_id,
                    "topic_id": topic.thread_id,
                    "topic_lineage_id": topic.lineage_id,
                    "participants": participants,
                },
            ),
        )
        self._remove_topic(topic)

    def _remove_topic(self, topic: _TopicThread) -> None:
        key = (topic.channel_id, topic.conversation_id)
        if self._topics.get(key) is topic:
            self._topics.pop(key, None)
        pending = self._pending_topics.get(key)
        if pending is None:
            return
        for event_id, candidate in tuple(pending.items()):
            if candidate is topic:
                pending.pop(event_id, None)
        if not pending:
            self._pending_topics.pop(key, None)

    def _remember_conversation(self, channel_id: str, conversation_id: str) -> None:
        conversations = self._authorized_conversations.setdefault(channel_id, deque())
        if conversation_id in conversations:
            return
        conversations.append(conversation_id)
        while len(conversations) > self._conversations_per_channel:
            conversations.popleft()


__all__ = ("ReasoningContextWorkspace",)
