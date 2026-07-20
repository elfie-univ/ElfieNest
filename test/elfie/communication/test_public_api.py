from elfie.communication import CommunicationHub, TelegramConnector, WeChatConnector


def test_communication_is_the_canonical_social_channel_api() -> None:
    assert WeChatConnector.__module__ == "elfie.communication.channels.wechat"
    assert TelegramConnector.__module__ == "elfie.communication.channels.telegram"
    assert CommunicationHub.__module__ == "elfie.communication.hub"
