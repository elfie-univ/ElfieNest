"""Shared channel-integrity fixtures for history v2 tests."""

from __future__ import annotations

import sqlite3


def insert_cross_channel_accounts(connection: sqlite3.Connection) -> None:
    """Insert same owner accounts on another channel."""
    connection.execute(
        """
        INSERT INTO self_channel_accounts VALUES (
            'self_feishu', 'feishu', 'elfie:00000001', 'Elfie', 'active',
            '{}', '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO external_channel_accounts VALUES (
            'external_feishu', NULL, 'feishu', 'user:1',
            'Owner', '{}', '2026-07-29T00:00:00Z', NULL, '2026-07-29T00:00:00Z'
        )
        """
    )


def insert_same_channel_nonmember_accounts(connection: sqlite3.Connection) -> None:
    """Insert same-channel accounts that are not participants of conv_1."""
    connection.execute(
        """
        INSERT INTO self_channel_accounts VALUES (
            'self_other_web', 'web', 'elfie:other', 'Other', 'active',
            '{}', '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO external_channel_accounts VALUES (
            'external_other_web', NULL, 'web', 'user:other',
            'Other', '{}', '2026-07-29T00:00:00Z', NULL, '2026-07-29T00:00:00Z'
        )
        """
    )


def insert_owner_and_external_participants(connection: sqlite3.Connection) -> None:
    """Insert the canonical self owner and external participant for conv_1."""
    connection.execute(
        """
        INSERT INTO conversation_participants VALUES (
            'conv_1', 'self', 'self_1', NULL, 'Elfie', 'self',
            '2026-07-29T00:00:00Z', NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO conversation_participants VALUES (
            'conv_1', 'external', NULL, 'external_1', 'Owner', 'owner',
            '2026-07-29T00:00:00Z', NULL
        )
        """
    )


def insert_external_message(connection: sqlite3.Connection) -> None:
    """Insert a valid external participant message."""
    connection.execute(
        """
        INSERT INTO messages VALUES (
            'msg_external', 'conv_1', 'web', 'source_external',
            'external', NULL, 'external_1', 'inbound', 'text', 'hello',
            '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', NULL, '{}'
        )
        """
    )


def insert_second_conversation_with_message(connection: sqlite3.Connection) -> None:
    """Insert a second conversation and a message for cross-reply checks."""
    connection.execute(
        """
        INSERT INTO conversations VALUES (
            'conv_2', 'web', 'thread_2', 'direct', NULL, 'self_1',
            '2026-07-29T00:00:00Z', NULL, 'active', '{}'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO messages VALUES (
            'msg_other', 'conv_2', 'web', 'source_other',
            'self', 'self_1', NULL, 'outbound', 'text', 'other',
            '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', NULL, '{}'
        )
        """
    )
