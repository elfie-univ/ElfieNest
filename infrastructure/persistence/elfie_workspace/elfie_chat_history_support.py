"""Root persistence setup for final Elfie chat conversations."""

from __future__ import annotations

import hashlib
import sqlite3


def ensure_chat_conversation(
    connection: sqlite3.Connection,
    *,
    elfie_id: str,
    conversation_id: str,
    channel: str,
    user_id: int | None,
    created_at: str,
    needs_external_account: bool,
    external_actor_id: str | None = None,
    external_actor_display_name: str | None = None,
) -> tuple[str, str, str]:
    """Create stable final-schema accounts and active participants idempotently."""
    self_account_id = f"self:{channel}:{elfie_id}"
    external_identity = (
        external_actor_id
        if external_actor_id is not None
        else ("anonymous" if user_id is None else f"user:{user_id}")
    )
    external_display_name = external_actor_display_name or external_identity
    external_account_id = f"external:{channel}:{external_identity}"
    storage_conversation_id = (
        "conversation:"
        + hashlib.sha256(f"{channel}\0{conversation_id}".encode()).hexdigest()
    )
    connection.execute(
        "INSERT OR IGNORE INTO self_channel_accounts VALUES "
        "(?, ?, ?, ?, 'active', '{}', ?, ?)",
        (
            self_account_id,
            channel,
            f"elfie:{elfie_id}",
            elfie_id,
            created_at,
            created_at,
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO conversations VALUES "
        "(?, ?, ?, 'direct', NULL, ?, ?, NULL, 'active', '{}')",
        (
            storage_conversation_id,
            channel,
            conversation_id,
            self_account_id,
            created_at,
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO conversation_participants VALUES "
        "(?, 'self', ?, NULL, ?, 'self', ?, NULL)",
        (storage_conversation_id, self_account_id, elfie_id, created_at),
    )
    if needs_external_account:
        connection.execute(
            "INSERT OR IGNORE INTO external_channel_accounts VALUES "
            "(?, NULL, ?, ?, ?, '{}', ?, ?, ?)",
            (
                external_account_id,
                channel,
                external_identity,
                external_display_name,
                created_at,
                created_at,
                created_at,
            ),
        )
        connection.execute(
            "INSERT OR IGNORE INTO conversation_participants VALUES "
            "(?, 'external', NULL, ?, ?, 'owner', ?, NULL)",
            (
                storage_conversation_id,
                external_account_id,
                external_display_name,
                created_at,
            ),
        )
    return self_account_id, external_account_id, storage_conversation_id
