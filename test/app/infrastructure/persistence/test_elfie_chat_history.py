"""精灵工作区聊天历史持久化测试。"""

from __future__ import annotations

from ai_runtime.storage.data_home import get_elfie_conversations_dir
from app.infrastructure.persistence.elfie_chat_history import (
    ElfieChatMessageInput,
    ElfieChatSender,
    list_elfie_chat_history,
    record_elfie_chat_message,
)


def test_records_multi_channel_history_in_the_elfie_workspace(
    monkeypatch, tmp_path
) -> None:
    """同一精灵的不同渠道消息按时间保存在同一工作区。"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "production"))

    record_elfie_chat_message(
        "elfie_alpha",
        ElfieChatMessageInput(
            message_id="msg_web_1",
            conversation_id="conv_owner",
            sender=ElfieChatSender.USER,
            text="网页来的消息",
            channel="web",
            created_at="2026-07-24T09:00:00.000Z",
        ),
    )
    record_elfie_chat_message(
        "elfie_alpha",
        ElfieChatMessageInput(
            message_id="msg_feishu_1",
            conversation_id="conv_owner",
            sender=ElfieChatSender.ELFIE,
            text="飞书回复",
            channel="feishu",
            created_at="2026-07-24T09:01:00.000Z",
        ),
    )

    history = list_elfie_chat_history("elfie_alpha", "conv_owner")

    assert [record.text for record in history] == ["网页来的消息", "飞书回复"]
    assert [record.channel for record in history] == ["web", "feishu"]
    assert (
        get_elfie_conversations_dir("elfie_alpha") / "history.sqlite"
    ).is_file()


def test_retries_are_idempotent_and_elfies_are_isolated(monkeypatch, tmp_path) -> None:
    """同一消息重试不重复，另一只精灵没有读取权限。"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "production"))
    message = ElfieChatMessageInput(
        message_id="msg_retry_1",
        conversation_id="conv_owner",
        sender=ElfieChatSender.USER,
        text="只应出现一次",
        channel="desktop",
        created_at="2026-07-24T09:00:00.000Z",
    )

    first = record_elfie_chat_message("elfie_alpha", message)
    second = record_elfie_chat_message("elfie_alpha", message)

    assert first == second
    assert len(list_elfie_chat_history("elfie_alpha")) == 1
    assert list_elfie_chat_history("elfie_beta") == []


def test_preserves_attachment_references_without_storing_binary_content(
    monkeypatch, tmp_path
) -> None:
    """附件只作为精灵工作区聊天记录的引用保存。"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "production"))

    record = record_elfie_chat_message(
        "elfie_alpha",
        ElfieChatMessageInput(
            message_id="msg_attachment_1",
            conversation_id="conv_owner",
            sender=ElfieChatSender.USER,
            text="请看看这张图",
            channel="web",
            attachment_refs=("sha256:abc123",),
        ),
    )

    assert record.attachment_refs_json == '["sha256:abc123"]'


def test_uses_the_explicit_nest_data_root_for_embedded_application(tmp_path) -> None:
    """嵌入式应用可将精灵聊天与其 Nest 数据根共同定位。"""
    data_home = tmp_path / "embedded-nest"

    record_elfie_chat_message(
        "elfie_alpha",
        ElfieChatMessageInput(
            message_id="msg_embedded_1",
            conversation_id="conv_owner",
            sender=ElfieChatSender.USER,
            text="嵌入式消息",
            channel="web",
        ),
        data_home=data_home,
    )

    assert (
        data_home / "elfies" / "elfie_alpha" / "conversations" / "history.sqlite"
    ).is_file()
