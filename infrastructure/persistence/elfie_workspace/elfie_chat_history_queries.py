"""Root persistence queries for the final per-Elfie chat history database."""

from __future__ import annotations

import sqlite3


def select_history_rows(
    connection: sqlite3.Connection,
    *,
    conversation_id: str | None,
    user_id: int | None,
    range_start: str | None,
    keyword: str,
    limit: int,
) -> list[sqlite3.Row]:
    """Select public message rows using final columns and metadata names."""
    clauses: list[str] = []
    parameters: list[str | int] = []
    if conversation_id is not None:
        clauses.append("conversation.external_thread_id = ?")
        parameters.append(conversation_id)
    if user_id is not None:
        clauses.append("json_extract(message.meta_json, '$.user_id') = ?")
        parameters.append(user_id)
    if range_start is not None:
        clauses.append("message.created_at >= ?")
        parameters.append(range_start)
    normalized_keyword = keyword.strip()
    if normalized_keyword:
        pattern = f"%{normalized_keyword}%"
        clauses.append(
            "(message.text LIKE ? OR json_extract(message.meta_json, '$.meta') LIKE ? "
            "OR CASE message.sender_type WHEN 'external' THEN 'user' "
            "WHEN 'self' THEN 'elfie' ELSE 'system' END LIKE ? "
            "OR message.channel LIKE ?)"
        )
        parameters.extend((pattern, pattern, pattern, pattern))
    parameters.append(max(1, min(200, limit)))
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return connection.execute(
        f"""SELECT message.rowid AS id, message.message_id,
                   conversation.external_thread_id,
                   message.sender_type, message.text, message.channel,
                   message.created_at, message.meta_json
            FROM messages AS message
            JOIN conversations AS conversation
              ON conversation.conversation_id = message.conversation_id
            {where_clause}
            ORDER BY message.created_at ASC, message.message_id ASC LIMIT ?""",
        tuple(parameters),
    ).fetchall()


def select_source_message(
    connection: sqlite3.Connection,
    channel: str,
    source_message_key: str,
) -> sqlite3.Row | None:
    """Read one idempotently written source message through final relations."""
    return connection.execute(
        """SELECT message.rowid AS id, message.message_id,
                  conversation.external_thread_id,
                  message.sender_type, message.text, message.channel,
                  message.created_at, message.meta_json
           FROM messages AS message
           JOIN conversations AS conversation
             ON conversation.conversation_id = message.conversation_id
           WHERE message.channel = ? AND message.source_message_key = ?""",
        (channel, source_message_key),
    ).fetchone()
