from elfie.communication import (
    CommunicationMessage,
    MessageDirection,
    TelegramChannel,
    TelegramConnector,
    WeChatChannel,
    WeChatConnector,
)


def outbound(channel_id: str, recipient_id: str) -> CommunicationMessage:
    return CommunicationMessage(
        channel_id=channel_id,
        direction=MessageDirection.OUTBOUND,
        sender_id="elfie-1",
        recipient_id=recipient_id,
        content="你好",
    )


def test_wechat_adapter_preserves_existing_connector_api() -> None:
    connector = WeChatConnector()
    channel = WeChatChannel(connector)

    assert channel.connect() is True
    assert channel.send(outbound("wechat", "owner")) is True
    assert connector.send_message("旧调用仍可用") is True
    channel.disconnect()
    assert connector.is_connected is False


def test_telegram_adapter_preserves_existing_connector_api() -> None:
    connector = TelegramConnector()
    channel = TelegramChannel(connector)

    assert channel.connect() is True
    assert channel.send(outbound("telegram", "chat-1")) is True
    assert connector.send_message("chat-1", "旧调用仍可用") is True
    channel.disconnect()
    assert connector.is_connected is False
