"""Small deterministic helpers shared by SQLite Memory mixins."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Mapping


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
    "stable_id",
    "utc_now",
]
