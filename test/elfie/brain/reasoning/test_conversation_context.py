"""Receipt-backed working conversation history and restart continuity."""

from datetime import datetime, timedelta, timezone

from elfie.brain.reasoning.conversation_context import ConversationContextStore
from elfie.brain.workspace.contracts import (
    CommunicationScope,
    ExternalExecutionDomain,
    PerceptionEvent,
    ResponseScope,
    SocialPayload,
    SourceDomain,
    TriggerReason,
    TurnFrame,
)
from elfie.message_types import ActorRef, MessageMeta

NOW = datetime(2026, 8, 22, 8, 0, tzinfo=timezone.utc)


def _frame(index: int, text: str, *, at: datetime) -> TurnFrame:
    owner = ActorRef(actor_id="owner-1", source_kind="owner")
    event_id = f"owner-message-{index}"
    event = PerceptionEvent(
        meta=MessageMeta(
            event_id=event_id,
            elfie_id="elfie-1",
            source=owner,
            occurred_at=at,
            received_at=at,
            trace_id=f"trace-{index}",
        ),
        payload=SocialPayload(
            type="social",
            channel_id="chat",
            conversation_id="owner-chat",
            sender=owner,
            content=text,
        ),
    )
    return TurnFrame(
        frame_id=f"frame-{index}",
        elfie_id="elfie-1",
        revision=index,
        captured_at=at,
        cutoff_seq=index,
        trigger_reason=TriggerReason.CONVERSATION_QUIET,
        source_domain=SourceDomain.COMMUNICATION,
        interaction_scope=CommunicationScope(
            channel_id="chat",
            conversation_id="owner-chat",
        ),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.COMMUNICATION,
            channel_id="chat",
            conversation_id="owner-chat",
        ),
        events=(event,),
    )


def test_completed_reply_forms_alternating_history_and_survives_checkpoint() -> None:
    store = ConversationContextStore()
    first = _frame(1, "我喜欢蓝色。", at=NOW)
    store.observe(first, NOW)

    interaction = store.record_completed_reply(
        channel_id="chat",
        conversation_id="owner-chat",
        reply_event_id="elfie-reply-1",
        sender=ActorRef(actor_id="elfie-1", source_kind="elfie"),
        occurred_at=NOW + timedelta(seconds=1),
        content="我记住啦。",
        cause_event_ids=("owner-message-1",),
        receipt_id="delivery-receipt-1",
    )

    assert interaction is not None
    assert interaction.owner.content == "我喜欢蓝色。"
    assert interaction.reply.content == "我记住啦。"
    restored = ConversationContextStore()
    restored.restore(store.checkpoint())

    second = _frame(2, "我刚才说喜欢什么颜色？", at=NOW + timedelta(seconds=2))
    context = restored.observe(second, NOW + timedelta(seconds=2))

    assert [message.sender.source_kind for message in context.messages] == [
        "owner",
        "elfie",
        "owner",
    ]
    assert [message.content for message in context.messages] == [
        "我喜欢蓝色。",
        "我记住啦。",
        "我刚才说喜欢什么颜色？",
    ]


def test_failed_or_duplicate_reply_is_not_added_twice() -> None:
    store = ConversationContextStore()
    frame = _frame(1, "你好", at=NOW)
    store.observe(frame, NOW)
    values = {
        "channel_id": "chat",
        "conversation_id": "owner-chat",
        "reply_event_id": "elfie-reply-1",
        "sender": ActorRef(actor_id="elfie-1", source_kind="elfie"),
        "occurred_at": NOW + timedelta(seconds=1),
        "content": "你好呀",
        "cause_event_ids": ("owner-message-1",),
        "receipt_id": "delivery-receipt-1",
    }

    assert store.record_completed_reply(**values) is not None
    assert store.record_completed_reply(**values) is None
    context = store.observe(frame, NOW + timedelta(seconds=2))
    assert [message.content for message in context.messages] == ["你好", "你好呀"]


def test_working_context_closes_topic_threads_without_owner_pairing() -> None:
    store = ConversationContextStore(topic_idle_seconds=60)
    first = _frame(1, "我们讨论周末去爬山。", at=NOW)
    second = _frame(2, "换个话题，厨房要买什么？", at=NOW + timedelta(seconds=5))

    store.observe(first, NOW)
    store.observe(second, NOW + timedelta(seconds=5))

    episodes = store.pending_closed_episodes()
    assert len(episodes) == 1
    assert episodes[0].source_event_ids == ("owner-message-1",)
    assert episodes[0].metadata["topic_id"]
    assert episodes[0].metadata["participants"] == ["owner-1"]


def test_working_context_closes_after_idle_and_ack_is_idempotent() -> None:
    store = ConversationContextStore(topic_idle_seconds=60)
    store.observe(_frame(1, "我叫小林。", at=NOW), NOW)
    store.observe(
        _frame(2, "继续聊。", at=NOW + timedelta(seconds=61)),
        NOW + timedelta(seconds=61),
    )

    episodes = store.pending_closed_episodes()
    assert len(episodes) == 1
    store.ack_closed_episodes((episodes[0].episode_id,))


def test_completed_reply_can_join_a_non_owner_participant() -> None:
    store = ConversationContextStore()
    frame = _frame(1, "小鹿说它明天来。", at=NOW).model_copy(
        update={
            "events": (
                _frame(1, "小鹿说它明天来。", at=NOW)
                .events[0]
                .model_copy(
                    update={
                        "meta": _frame(1, "小鹿说它明天来。", at=NOW)
                        .events[0]
                        .meta.model_copy(
                            update={
                                "source": ActorRef(
                                    actor_id="guest-1", source_kind="participant"
                                )
                            }
                        ),
                        "payload": _frame(1, "小鹿说它明天来。", at=NOW)
                        .events[0]
                        .payload.model_copy(
                            update={
                                "sender": ActorRef(
                                    actor_id="guest-1", source_kind="participant"
                                )
                            }
                        ),
                    }
                ),
            )
        }
    )
    store.observe(frame, NOW)
    interaction = store.record_completed_reply(
        channel_id="chat",
        conversation_id="owner-chat",
        reply_event_id="elfie-reply-guest-1",
        sender=ActorRef(actor_id="elfie-1", source_kind="elfie"),
        occurred_at=NOW + timedelta(seconds=1),
        content="我会记得。",
        cause_event_ids=("owner-message-1",),
        receipt_id="delivery-receipt-guest-1",
    )
    assert interaction is not None
    assert interaction.owner.sender.source_kind == "participant"
