from elfie.communication import (
    CommunicationEnvelope,
    CommunicationHub,
    DeliveryReceipt,
    TelegramConnector,
    WeChatConnector,
    channel,
    router,
)


def test_communication_is_the_canonical_social_channel_api() -> None:
    assert WeChatConnector.__module__ == "elfie.communication.channels.wechat"
    assert TelegramConnector.__module__ == "elfie.communication.channels.telegram"
    assert CommunicationHub.__module__ == "elfie.communication.hub"


def test_legacy_communication_api_is_removed() -> None:
    # Given: the canonical communication package and its public contract models.
    legacy_symbols = (
        (channel, "CommunicationMessage"),
        (channel, "MessageKind"),
        (channel, "LegacyCommunicationChannel"),
        (router, "LegacyChannelAdapter"),
    )
    compatibility_properties = (
        (CommunicationEnvelope, "message_id"),
        (CommunicationEnvelope, "sender_id"),
        (CommunicationEnvelope, "recipient_id"),
        (CommunicationEnvelope, "timestamp"),
        (DeliveryReceipt, "delivered"),
    )

    # When: callers inspect the communication API after the envelope migration.
    exposed_legacy_names = [
        name for module, name in legacy_symbols if hasattr(module, name)
    ]
    exposed_compatibility_properties = [
        name for model, name in compatibility_properties if hasattr(model, name)
    ]

    # Then: no bool-channel or compatibility-only surface remains.
    assert exposed_legacy_names == []
    assert exposed_compatibility_properties == []
