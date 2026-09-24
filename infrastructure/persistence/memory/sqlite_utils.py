"""Small deterministic helpers shared by SQLite Memory mixins."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Mapping

_NON_SEARCHABLE_NODE_PROPERTY_KEYS = frozenset(
    {
        "elfie_id",
        "genesis_submission_id",
        "source_id",
        "source_ref",
        "source_version",
        "seed_id",
        "knowledge_id",
        "relationship_id",
        "person_id",
        "person_species_id",
        "episode_id",
        "episode_ids",
        "related_ids",
        "prerequisite_ids",
        "consultable_target_ids",
        "privacy_scope",
        "recall_eligible",
        "confidence_class",
        "initial_confidence",
        "policy_version",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def normalize_text(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_id(prefix: str, *parts: object, length: int = 32) -> str:
    """Build a deterministic local identifier from semantic parts.

    Runtime retries and process restarts must address the same projection row;
    UUIDs are reserved for genuinely new external events, not derived facts.
    """
    if not prefix.strip():
        raise ValueError("identifier prefix must not be blank")
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:length]}"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return result if isinstance(result, dict) else {}


def json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        return []
    return result if isinstance(result, list) else []


def searchable_node_property_text(properties: Mapping[str, Any] | None) -> str:
    """Flatten user-facing Node properties into a rebuildable text projection.

    Properties remain structured facts in ``nodes.properties_json``.  This
    projection is only for lexical candidate search, so technical identifiers
    and provenance fields are deliberately excluded.
    """

    values: list[str] = []

    def visit(value: Any, key: str | None = None) -> None:
        if key is not None and key in _NON_SEARCHABLE_NODE_PROPERTY_KEYS:
            return
        if isinstance(value, Mapping):
            for child_key, child_value in value.items():
                visit(child_value, str(child_key))
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                visit(item, key)
            return
        if isinstance(value, bool) or value is None:
            return
        text = str(value).strip()
        if text:
            values.append(text)

    visit(properties or {})
    return "\n".join(dict.fromkeys(values))


def bounded_score(value: object, default: float = 0.5) -> float:
    try:
        score = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if not math.isfinite(score):
        return default
    return min(1.0, max(0.0, score))


def normalized_tokens(value: str) -> list[str]:
    """Return searchable tokens while preserving rare Chinese characters."""
    cleaned = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", "", value.casefold())
    tokens: list[str] = []
    for part in cleaned.split():
        if any("\u4e00" <= char <= "\u9fff" for char in part):
            chars = list(part)
            tokens.extend(chars)
            tokens.extend(part[index : index + 2] for index in range(len(part) - 1))
        else:
            tokens.append(part)
    return [token for token in tokens if token]


def safe_json_mapping(value: Mapping[str, object] | None) -> dict[str, Any]:
    return dict(value or {})


__all__ = [
    "bounded_score",
    "canonical_json",
    "content_hash",
    "json_list",
    "json_object",
    "normalize_text",
    "normalized_tokens",
    "safe_json_mapping",
    "searchable_node_property_text",
    "stable_id",
    "utc_now",
]
