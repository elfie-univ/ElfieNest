"""Review-block row fixtures for history v2 schema tests."""

from __future__ import annotations


def null_identity_rows() -> tuple[tuple[str, tuple[str | int | None, ...]], ...]:
    """Return full-row inserts with NULL identity keys for every PK identity table."""
    timestamp = "2026-07-29T00:00:00Z"
    return (
        (
            "self_channel_accounts",
            (None, "web", "elfie:null", "Null", "active", "{}", timestamp, timestamp),
        ),
        (
            "external_channel_accounts",
            (None, None, "web", "user:null", "Null", "{}", timestamp, None, timestamp),
        ),
        (
            "conversations",
            (
                None,
                "web",
                "thread_null",
                "direct",
                None,
                "self_1",
                timestamp,
                None,
                "active",
                "{}",
            ),
        ),
        (
            "messages",
            (
                None,
                "conv_1",
                "web",
                "source_null",
                "self",
                "self_1",
                None,
                "outbound",
                "text",
                "bad",
                timestamp,
                timestamp,
                None,
                "{}",
            ),
        ),
        (
            "attachments",
            (
                None,
                "msg_1",
                "image",
                "a.png",
                "image/png",
                None,
                None,
                12,
                None,
                "{}",
                timestamp,
            ),
        ),
        (
            "ingestion_offsets",
            (None, "web", "self_1", "thread_null", "cursor-null", timestamp, "{}"),
        ),
    )


def array_json_rows() -> tuple[tuple[str, tuple[str | int | None, ...]], ...]:
    """Return full-row inserts with array JSON for every object JSON field."""
    timestamp = "2026-07-29T00:00:00Z"
    return (
        (
            "self_channel_accounts",
            ("self_array", "web", "elfie:array", "Array", "active", "[]", timestamp, timestamp),
        ),
        (
            "external_channel_accounts",
            ("external_array", None, "web", "user:array", "Array", "[]", timestamp, None, timestamp),
        ),
        (
            "conversations",
            (
                "conv_array",
                "web",
                "thread_array",
                "direct",
                None,
                "self_1",
                timestamp,
                None,
                "active",
                "[]",
            ),
        ),
        (
            "messages",
            (
                "msg_json_array",
                "conv_1",
                "web",
                "source_json_array",
                "self",
                "self_1",
                None,
                "outbound",
                "text",
                "bad",
                timestamp,
                timestamp,
                None,
                "[]",
            ),
        ),
        (
            "attachments",
            ("att_array", "msg_1", "image", "a.png", "image/png", None, None, 12, None, "[]", timestamp),
        ),
        (
            "ingestion_offsets",
            ("offset_array", "web", "self_1", "thread_array", "cursor-array", timestamp, "[]"),
        ),
    )
