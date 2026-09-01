"""Receipt-backed working conversation history and restart continuity."""

from datetime import datetime, timedelta, timezone

from elfie.brain.reasoning.conversation_context import ReasoningContextWorkspace
from elfie.brain.workspace.contracts import (
    CommunicationScope,
    ExecutionStatus,
    ExternalExecutionDomain,
    PerceptionEvent,
    ResponseScope,
    SocialPayload,
    SourceDomain,
    TriggerReason,
    TurnFrame,
)
from elfie.message_types import ActorRef, IntentId, MessageMeta

NOW = datetime(2026, 8, 22, 8, 0, tzinfo=timezone.utc)


def _frame(
    index: int,
    text: str,
    *,
    at: datetime,
    channel_id: str = "chat",
    conversation_id: str = "owner-chat",
) -> TurnFrame:
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
            channel_id=channel_id,
            conversation_id=conversation_id,
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
            channel_id=channel_id,
            conversation_id=conversation_id,
        ),
        response_scope=ResponseScope(
            external_domain=ExternalExecutionDomain.COMMUNICATION,
            channel_id=channel_id,
            conversation_id=conversation_id,
        ),
        events=(event,),
    )


def test_completed_reply_forms_alternating_history_and_survives_checkpoint() -> None:
    store = ReasoningContextWorkspace()
    first = _frame(1, "我喜欢蓝色。", at=NOW)
    store.observe(first, NOW)

    assert store.prepare_reply(
        intent_id=IntentId("reply-intent-1"),
        channel_id="chat",
        conversation_id="owner-chat",
        reply_event_id="elfie-reply-1",
        content="我记住啦。",
        cause_event_ids=("owner-message-1",),
        prepared_at=NOW,
    )
    interaction = store.settle_reply(
        intent_id=IntentId("reply-intent-1"),
        status=ExecutionStatus.COMPLETED,
        receipt_id="delivery-receipt-1",
        occurred_at=NOW + timedelta(seconds=1),
        sender=ActorRef(actor_id="elfie-1", source_kind="elfie"),
    )

    assert interaction is not None
    assert interaction.owner.content == "我喜欢蓝色。"
    assert interaction.reply.content == "我记住啦。"
    assert store.pending_closed_episodes() == ()
    restored = ReasoningContextWorkspace()
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
    store = ReasoningContextWorkspace()
    frame = _frame(1, "你好", at=NOW)
    store.observe(frame, NOW)
    prepared = {
        "intent_id": IntentId("reply-intent-1"),
        "channel_id": "chat",
        "conversation_id": "owner-chat",
        "reply_event_id": "elfie-reply-1",
        "content": "你好呀",
        "cause_event_ids": ("owner-message-1",),
        "prepared_at": NOW,
    }
    settled = {
        "intent_id": IntentId("reply-intent-1"),
        "status": ExecutionStatus.COMPLETED,
        "receipt_id": "delivery-receipt-1",
        "occurred_at": NOW + timedelta(seconds=1),
        "sender": ActorRef(actor_id="elfie-1", source_kind="elfie"),
    }

    assert store.prepare_reply(**prepared)
    assert store.settle_reply(**settled) is not None
    assert store.settle_reply(**settled) is None
    context = store.observe(frame, NOW + timedelta(seconds=2))
    assert [message.content for message in context.messages] == ["你好", "你好呀"]


def test_failed_and_timed_out_replies_never_enter_confirmed_history() -> None:
    store = ReasoningContextWorkspace()
    frame = _frame(1, "你好", at=NOW)
    store.observe(frame, NOW)

    for index, status in enumerate(
        (ExecutionStatus.FAILED, ExecutionStatus.TIMED_OUT), start=1
    ):
        intent_id = IntentId(f"failed-reply-{index}")
        assert store.prepare_reply(
            intent_id=intent_id,
            channel_id="chat",
            conversation_id="owner-chat",
            reply_event_id=f"failed-reply-event-{index}",
            content="这条没有真实投递。",
            cause_event_ids=("owner-message-1",),
            prepared_at=NOW,
        )
        assert (
            store.settle_reply(
                intent_id=intent_id,
                status=status,
                receipt_id=f"failed-receipt-{index}",
                occurred_at=NOW + timedelta(seconds=index),
                sender=ActorRef(actor_id="elfie-1", source_kind="elfie"),
            )
            is None
        )

    context = store.observe(frame, NOW + timedelta(seconds=3))
    assert [message.content for message in context.messages] == ["你好"]


def test_pronoun_continuation_and_two_conversations_remain_isolated() -> None:
    store = ReasoningContextWorkspace()
    store.observe(
        _frame(1, "我最近在养一盆薄荷。", at=NOW, conversation_id="owner-a"),
        NOW,
    )
    store.observe(
        _frame(
            2,
            "另一条会话只讨论跑步。",
            at=NOW + timedelta(seconds=1),
            conversation_id="owner-b",
        ),
        NOW + timedelta(seconds=1),
    )

    context = store.observe(
        _frame(
            3,
            "那个现在要怎么照顾？",
            at=NOW + timedelta(seconds=2),
            conversation_id="owner-a",
        ),
        NOW + timedelta(seconds=2),
    )

    assert [message.content for message in context.messages] == [
        "我最近在养一盆薄荷。",
        "那个现在要怎么照顾？",
    ]
    assert all("跑步" not in message.content for message in context.messages)
    assert len(store.checkpoint().threads) == 2


def test_topic_close_waits_for_causal_reply_terminal_and_keeps_full_sources() -> None:
    store = ReasoningContextWorkspace(topic_idle_seconds=60)
    first = _frame(1, "我们讨论周末去爬山。", at=NOW)
    second = _frame(2, "换个话题，厨房要买什么？", at=NOW + timedelta(seconds=5))

    store.observe(first, NOW)
    store.observe(second, NOW + timedelta(seconds=5))

    assert store.pending_closed_episodes() == ()
    assert store.prepare_reply(
        intent_id=IntentId("reply-intent-2"),
        channel_id="chat",
        conversation_id="owner-chat",
        reply_event_id="elfie-reply-2",
        content="先说厨房采购，再继续新话题。",
        cause_event_ids=("owner-message-2",),
        prepared_at=NOW + timedelta(seconds=5),
    )
    store.settle_reply(
        intent_id=IntentId("reply-intent-2"),
        status=ExecutionStatus.COMPLETED,
        receipt_id="delivery-receipt-2",
        occurred_at=NOW + timedelta(seconds=6),
        sender=ActorRef(actor_id="elfie-1", source_kind="elfie"),
    )

    episodes = store.pending_closed_episodes()
    assert len(episodes) == 1
    assert episodes[0].source_event_ids == (
        "owner-message-1",
        "owner-message-2",
        "elfie-reply-2",
    )
    assert episodes[0].metadata["topic_id"]
    assert episodes[0].metadata["participants"] == ["owner-1", "elfie-1"]


def test_working_context_closes_after_idle_and_ack_is_idempotent() -> None:
    store = ReasoningContextWorkspace(topic_idle_seconds=60)
    store.observe(_frame(1, "我叫小林。", at=NOW), NOW)
    store.observe(
        _frame(2, "继续聊。", at=NOW + timedelta(seconds=61)),
        NOW + timedelta(seconds=61),
    )

    episodes = store.pending_closed_episodes()
    assert len(episodes) == 1
    store.ack_closed_episodes((episodes[0].episode_id,))


def test_completed_reply_can_join_a_non_owner_participant() -> None:
    store = ReasoningContextWorkspace()
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
    assert store.prepare_reply(
        intent_id=IntentId("reply-intent-guest-1"),
        channel_id="chat",
        conversation_id="owner-chat",
        reply_event_id="elfie-reply-guest-1",
        content="我会记得。",
        cause_event_ids=("owner-message-1",),
        prepared_at=NOW,
    )
    interaction = store.settle_reply(
        intent_id=IntentId("reply-intent-guest-1"),
        status=ExecutionStatus.COMPLETED,
        receipt_id="delivery-receipt-guest-1",
        occurred_at=NOW + timedelta(seconds=1),
        sender=ActorRef(actor_id="elfie-1", source_kind="elfie"),
    )
    assert interaction is not None
    assert interaction.owner.sender.source_kind == "participant"


def test_pending_reply_topic_and_episode_handoff_survive_checkpoint() -> None:
    store = ReasoningContextWorkspace()
    frame = _frame(1, "这个话题先这样", at=NOW)
    store.observe(frame, NOW)
    assert store.prepare_reply(
        intent_id=IntentId("reply-intent-restart"),
        channel_id="chat",
        conversation_id="owner-chat",
        reply_event_id="elfie-reply-restart",
        content="好，我们先停在这里。",
        cause_event_ids=("owner-message-1",),
        prepared_at=NOW,
    )

    restored = ReasoningContextWorkspace()
    restored.restore(store.checkpoint())
    assert restored.pending_reply_ids() == ("reply-intent-restart",)
    assert restored.pending_closed_episodes() == ()

    interaction = restored.settle_reply(
        intent_id=IntentId("reply-intent-restart"),
        status=ExecutionStatus.COMPLETED,
        receipt_id="receipt-restart",
        occurred_at=NOW + timedelta(seconds=1),
        sender=ActorRef(actor_id="elfie-1", source_kind="elfie"),
    )
    assert interaction is not None
    episode = restored.pending_closed_episodes()[0]
    assert episode.source_event_ids == (
        "owner-message-1",
        "elfie-reply-restart",
    )

    replayed = ReasoningContextWorkspace()
    replayed.restore(restored.checkpoint())
    assert replayed.pending_closed_episodes()[0] == episode


def test_history_pressure_creates_source_backed_summary_before_raw_eviction() -> None:
    store = ReasoningContextWorkspace(history_capacity=4, summary_capacity=3)
    for index, text in enumerate(
        (
            "我先说喜欢红色。",
            "纠正一下，我真正喜欢的是蓝色。",
            "这个偏好以后还记得吗？",
            "最后再确认一遍。",
            "现在告诉我我喜欢什么颜色？",
        ),
        start=1,
    ):
        at = NOW + timedelta(seconds=index)
        store.observe(_frame(index, text, at=at), at)

    context = store.observe(
        _frame(5, "现在告诉我我喜欢什么颜色？", at=NOW + timedelta(seconds=5)),
        NOW + timedelta(seconds=5),
    )
    assert len(context.messages) <= 4
    assert context.messages[-1].content == "现在告诉我我喜欢什么颜色？"
    assert context.summaries
    covered = {
        str(event_id)
        for summary in context.summaries
        for event_id in summary.source_event_ids
    }
    assert "owner-message-1" in covered
    assert any("纠正一下" in item for item in context.summaries[0].unresolved_items)

    restored = ReasoningContextWorkspace(history_capacity=4, summary_capacity=3)
    restored.restore(store.checkpoint())
    restored_context = restored.observe(
        _frame(5, "现在告诉我我喜欢什么颜色？", at=NOW + timedelta(seconds=5)),
        NOW + timedelta(seconds=6),
    )
    assert restored_context.summaries == context.summaries
