"""Account, conversation, and participant DDL for history v2."""

from __future__ import annotations

from typing import Final

ACCOUNT_CONVERSATION_STATEMENTS: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS self_channel_accounts (
        self_account_id TEXT NOT NULL PRIMARY KEY,
        channel TEXT NOT NULL,
        external_account_id TEXT NOT NULL,
        display_name TEXT,
        status TEXT NOT NULL,
        meta_json TEXT NOT NULL DEFAULT '{}'
            CHECK(json_valid(meta_json) AND json_type(meta_json) = 'object'),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(channel, external_account_id),
        UNIQUE(self_account_id, channel)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS external_channel_accounts (
        channel_account_id TEXT NOT NULL PRIMARY KEY,
        knowledge_entity_id TEXT,
        channel TEXT NOT NULL,
        external_account_id TEXT NOT NULL,
        display_name TEXT,
        profile_json TEXT NOT NULL DEFAULT '{}'
            CHECK(json_valid(profile_json) AND json_type(profile_json) = 'object'),
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT,
        updated_at TEXT NOT NULL,
        UNIQUE(channel, external_account_id),
        UNIQUE(channel_account_id, channel)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversations (
        conversation_id TEXT NOT NULL PRIMARY KEY,
        channel TEXT NOT NULL,
        external_thread_id TEXT NOT NULL,
        conversation_type TEXT NOT NULL CHECK(conversation_type IN ('direct', 'group')),
        title TEXT,
        self_account_id TEXT NOT NULL,
        started_at TEXT NOT NULL,
        last_message_at TEXT,
        status TEXT NOT NULL,
        meta_json TEXT NOT NULL DEFAULT '{}'
            CHECK(json_valid(meta_json) AND json_type(meta_json) = 'object'),
        UNIQUE(channel, external_thread_id),
        UNIQUE(conversation_id, channel),
        FOREIGN KEY(self_account_id) REFERENCES self_channel_accounts(self_account_id),
        FOREIGN KEY(self_account_id, channel)
            REFERENCES self_channel_accounts(self_account_id, channel)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_participants (
        conversation_id TEXT NOT NULL,
        participant_type TEXT NOT NULL CHECK(participant_type IN ('self', 'external')),
        self_account_id TEXT,
        channel_account_id TEXT,
        display_name_snapshot TEXT,
        role TEXT NOT NULL,
        joined_at TEXT NOT NULL,
        left_at TEXT,
        CHECK(
            (participant_type = 'self' AND self_account_id IS NOT NULL AND channel_account_id IS NULL)
            OR (participant_type = 'external' AND self_account_id IS NULL AND channel_account_id IS NOT NULL)
        ),
        FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id),
        FOREIGN KEY(self_account_id) REFERENCES self_channel_accounts(self_account_id),
        FOREIGN KEY(channel_account_id) REFERENCES external_channel_accounts(channel_account_id)
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_participants_channel_insert
    BEFORE INSERT ON conversation_participants
    WHEN
        (
            NEW.self_account_id IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM conversations AS c
                JOIN self_channel_accounts AS a
                    ON a.self_account_id = NEW.self_account_id
                WHERE c.conversation_id = NEW.conversation_id
                    AND a.channel <> c.channel
            )
        )
        OR (
            NEW.channel_account_id IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM conversations AS c
                JOIN external_channel_accounts AS a
                    ON a.channel_account_id = NEW.channel_account_id
                WHERE c.conversation_id = NEW.conversation_id
                    AND a.channel <> c.channel
            )
        )
    BEGIN
        SELECT RAISE(ABORT, 'conversation participant channel mismatch');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_participants_self_owner_insert
    BEFORE INSERT ON conversation_participants
    WHEN
        NEW.participant_type = 'self'
        AND NOT EXISTS (
            SELECT 1
            FROM conversations AS c
            WHERE c.conversation_id = NEW.conversation_id
                AND c.self_account_id = NEW.self_account_id
        )
    BEGIN
        SELECT RAISE(ABORT, 'conversation self participant must be owner');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_participants_channel_update
    BEFORE UPDATE OF conversation_id, self_account_id, channel_account_id
    ON conversation_participants
    WHEN
        (
            NEW.self_account_id IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM conversations AS c
                JOIN self_channel_accounts AS a
                    ON a.self_account_id = NEW.self_account_id
                WHERE c.conversation_id = NEW.conversation_id
                    AND a.channel <> c.channel
            )
        )
        OR (
            NEW.channel_account_id IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM conversations AS c
                JOIN external_channel_accounts AS a
                    ON a.channel_account_id = NEW.channel_account_id
                WHERE c.conversation_id = NEW.conversation_id
                    AND a.channel <> c.channel
            )
        )
    BEGIN
        SELECT RAISE(ABORT, 'conversation participant channel mismatch');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_participants_self_owner_update
    BEFORE UPDATE OF conversation_id, participant_type, self_account_id
    ON conversation_participants
    WHEN
        NEW.participant_type = 'self'
        AND NOT EXISTS (
            SELECT 1
            FROM conversations AS c
            WHERE c.conversation_id = NEW.conversation_id
                AND c.self_account_id = NEW.self_account_id
        )
    BEGIN
        SELECT RAISE(ABORT, 'conversation self participant must be owner');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversations_channel_update
    BEFORE UPDATE OF channel ON conversations
    WHEN EXISTS (
        SELECT 1
        FROM conversation_participants AS p
        LEFT JOIN self_channel_accounts AS self_account
            ON self_account.self_account_id = p.self_account_id
        LEFT JOIN external_channel_accounts AS external_account
            ON external_account.channel_account_id = p.channel_account_id
        WHERE p.conversation_id = NEW.conversation_id
            AND COALESCE(self_account.channel, external_account.channel) <> NEW.channel
    )
    BEGIN
        SELECT RAISE(ABORT, 'conversation channel participant mismatch');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversations_self_account_immutable
    BEFORE UPDATE OF self_account_id ON conversations
    BEGIN
        SELECT RAISE(ABORT, 'conversation self account is immutable');
    END
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_participants_self_unique
    ON conversation_participants(conversation_id, self_account_id)
    WHERE self_account_id IS NOT NULL
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_participants_external_unique
    ON conversation_participants(conversation_id, channel_account_id)
    WHERE channel_account_id IS NOT NULL
    """,
)
