"""Message, attachment, and offset DDL for history v2."""

from __future__ import annotations

from typing import Final

MESSAGE_STATEMENTS: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS messages (
        message_id TEXT NOT NULL PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        channel TEXT NOT NULL,
        source_message_key TEXT NOT NULL,
        sender_type TEXT NOT NULL CHECK(sender_type IN ('self', 'external', 'internal')),
        self_account_id TEXT,
        channel_account_id TEXT,
        direction TEXT NOT NULL CHECK(direction IN ('inbound', 'outbound', 'internal')),
        message_type TEXT NOT NULL,
        text TEXT,
        created_at TEXT NOT NULL,
        ingested_at TEXT NOT NULL,
        reply_to_message_id TEXT,
        meta_json TEXT NOT NULL DEFAULT '{}'
            CHECK(json_valid(meta_json) AND json_type(meta_json) = 'object'),
        CHECK(
            (
                sender_type = 'self'
                AND direction = 'outbound'
                AND self_account_id IS NOT NULL
                AND channel_account_id IS NULL
            )
            OR (
                sender_type = 'external'
                AND direction = 'inbound'
                AND self_account_id IS NULL
                AND channel_account_id IS NOT NULL
            )
            OR (
                sender_type = 'internal'
                AND direction = 'internal'
                AND self_account_id IS NULL
                AND channel_account_id IS NULL
            )
        ),
        UNIQUE(channel, source_message_key),
        UNIQUE(message_id, conversation_id),
        FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id),
        FOREIGN KEY(conversation_id, channel) REFERENCES conversations(conversation_id, channel),
        FOREIGN KEY(self_account_id) REFERENCES self_channel_accounts(self_account_id),
        FOREIGN KEY(self_account_id, channel)
            REFERENCES self_channel_accounts(self_account_id, channel),
        FOREIGN KEY(channel_account_id) REFERENCES external_channel_accounts(channel_account_id),
        FOREIGN KEY(channel_account_id, channel)
            REFERENCES external_channel_accounts(channel_account_id, channel),
        FOREIGN KEY(reply_to_message_id) REFERENCES messages(message_id),
        FOREIGN KEY(reply_to_message_id, conversation_id)
            REFERENCES messages(message_id, conversation_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attachments (
        attachment_id TEXT NOT NULL PRIMARY KEY,
        message_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        filename TEXT,
        mime_type TEXT,
        local_path TEXT,
        external_url TEXT,
        size_bytes INTEGER,
        sha256 TEXT,
        meta_json TEXT NOT NULL DEFAULT '{}'
            CHECK(json_valid(meta_json) AND json_type(meta_json) = 'object'),
        created_at TEXT NOT NULL,
        CHECK(NOT (local_path IS NOT NULL AND external_url IS NOT NULL)),
        CHECK(size_bytes IS NULL OR size_bytes >= 0),
        CHECK(
            local_path IS NULL
            OR (
                local_path <> '.'
                AND local_path <> '..'
                AND local_path NOT LIKE '/%'
                AND local_path NOT LIKE '\\%'
                AND local_path NOT LIKE '../%'
                AND local_path NOT LIKE '%/../%'
                AND local_path NOT LIKE '%/..'
                AND local_path NOT LIKE '%\\%'
                AND local_path NOT LIKE '%://%'
                AND local_path NOT GLOB '[A-Za-z]:*'
            )
        ),
        FOREIGN KEY(message_id) REFERENCES messages(message_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingestion_offsets (
        offset_id TEXT NOT NULL PRIMARY KEY,
        channel TEXT NOT NULL,
        self_account_id TEXT NOT NULL,
        external_thread_id TEXT NOT NULL,
        cursor TEXT NOT NULL,
        last_synced_at TEXT NOT NULL,
        meta_json TEXT NOT NULL DEFAULT '{}'
            CHECK(json_valid(meta_json) AND json_type(meta_json) = 'object'),
        UNIQUE(channel, self_account_id, external_thread_id),
        FOREIGN KEY(self_account_id) REFERENCES self_channel_accounts(self_account_id),
        FOREIGN KEY(self_account_id, channel)
            REFERENCES self_channel_accounts(self_account_id, channel)
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_messages_membership_insert
    BEFORE INSERT ON messages
    WHEN
        (
            NEW.sender_type = 'self'
            AND NOT EXISTS (
                SELECT 1
                FROM conversations AS c
                WHERE c.conversation_id = NEW.conversation_id
                    AND c.self_account_id = NEW.self_account_id
            )
        )
        OR (
            NEW.sender_type = 'external'
            AND NOT EXISTS (
                SELECT 1
                FROM conversation_participants AS p
                WHERE p.conversation_id = NEW.conversation_id
                    AND p.participant_type = 'external'
                    AND p.channel_account_id = NEW.channel_account_id
                    AND p.left_at IS NULL
            )
        )
    BEGIN
        SELECT RAISE(ABORT, 'message sender is not a conversation member');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_messages_membership_update
    BEFORE UPDATE OF conversation_id, sender_type, self_account_id, channel_account_id
    ON messages
    WHEN
        (
            NEW.sender_type = 'self'
            AND NOT EXISTS (
                SELECT 1
                FROM conversations AS c
                WHERE c.conversation_id = NEW.conversation_id
                    AND c.self_account_id = NEW.self_account_id
            )
        )
        OR (
            NEW.sender_type = 'external'
            AND NOT EXISTS (
                SELECT 1
                FROM conversation_participants AS p
                WHERE p.conversation_id = NEW.conversation_id
                    AND p.participant_type = 'external'
                    AND p.channel_account_id = NEW.channel_account_id
                    AND p.left_at IS NULL
            )
        )
    BEGIN
        SELECT RAISE(ABORT, 'message sender is not a conversation member');
    END
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
    ON messages(conversation_id, created_at, message_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_messages_reply_to_message
    ON messages(reply_to_message_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_messages_sender_self
    ON messages(self_account_id, created_at)
    WHERE self_account_id IS NOT NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_attachments_message_id
    ON attachments(message_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ingestion_offsets_self_account
    ON ingestion_offsets(self_account_id)
    """,
)
