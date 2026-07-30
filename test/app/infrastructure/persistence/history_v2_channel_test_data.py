"""SQL statement sets for history v2 channel integrity tests."""

from __future__ import annotations


def same_channel_insert_bypass_statements() -> tuple[str, ...]:
    """Return same-channel nonmember INSERT attempts."""
    return (
        """
        INSERT INTO conversation_participants VALUES (
            'conv_1', 'self', 'self_other_web', NULL, 'wrong owner',
            'self', '2026-07-29T00:00:00Z', NULL
        )
        """,
        """
        INSERT INTO messages VALUES (
            'msg_wrong_self', 'conv_1', 'web', 'source_wrong_self',
            'self', 'self_other_web', NULL, 'outbound', 'text', 'bad',
            '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', NULL, '{}'
        )
        """,
        """
        INSERT INTO messages VALUES (
            'msg_nonparticipant_external', 'conv_1', 'web', 'source_wrong_external',
            'external', NULL, 'external_other_web', 'inbound', 'text', 'bad',
            '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', NULL, '{}'
        )
        """,
    )


def same_channel_update_bypass_statements() -> tuple[str, ...]:
    """Return same-channel nonmember UPDATE attempts."""
    return (
        "UPDATE conversations SET self_account_id = 'self_other_web' WHERE conversation_id = 'conv_1'",
        "UPDATE conversation_participants SET self_account_id = 'self_other_web' WHERE conversation_id = 'conv_1' AND participant_type = 'self'",
        "UPDATE messages SET self_account_id = 'self_other_web' WHERE message_id = 'msg_1'",
        "UPDATE messages SET channel_account_id = 'external_other_web' WHERE message_id = 'msg_external'",
    )


def cross_channel_insert_statements() -> tuple[str, ...]:
    """Return cross-channel INSERT attempts."""
    return (
        """
        INSERT INTO conversations VALUES (
            'conv_bad_channel', 'feishu', 'thread_bad', 'direct',
            NULL, 'self_1', '2026-07-29T00:00:00Z', NULL, 'active', '{}'
        )
        """,
        """
        INSERT INTO conversation_participants VALUES (
            'conv_1', 'self', 'self_feishu', NULL, 'wrong', 'self',
            '2026-07-29T00:00:00Z', NULL
        )
        """,
        """
        INSERT INTO conversation_participants VALUES (
            'conv_1', 'external', NULL, 'external_feishu', 'wrong', 'owner',
            '2026-07-29T00:00:00Z', NULL
        )
        """,
        """
        INSERT INTO messages VALUES (
            'msg_bad_channel', 'conv_1', 'feishu', 'source_bad_channel',
            'self', 'self_feishu', NULL, 'outbound', 'text', 'bad',
            '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', NULL, '{}'
        )
        """,
        """
        INSERT INTO messages VALUES (
            'msg_bad_self_account', 'conv_1', 'web', 'source_bad_self',
            'self', 'self_feishu', NULL, 'outbound', 'text', 'bad',
            '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', NULL, '{}'
        )
        """,
        """
        INSERT INTO ingestion_offsets VALUES (
            'offset_bad', 'feishu', 'self_1', 'thread_1', 'cursor-bad',
            '2026-07-29T00:00:00Z', '{}'
        )
        """,
    )


def cross_channel_update_statements() -> tuple[str, ...]:
    """Return cross-channel UPDATE attempts."""
    return (
        "UPDATE conversations SET channel = 'feishu' WHERE conversation_id = 'conv_1'",
        "UPDATE conversation_participants SET self_account_id = 'self_feishu' WHERE conversation_id = 'conv_1'",
        "UPDATE messages SET channel = 'feishu' WHERE message_id = 'msg_1'",
        "UPDATE messages SET self_account_id = 'self_feishu' WHERE message_id = 'msg_1'",
        "UPDATE ingestion_offsets SET channel = 'feishu' WHERE offset_id = 'offset_1'",
    )
