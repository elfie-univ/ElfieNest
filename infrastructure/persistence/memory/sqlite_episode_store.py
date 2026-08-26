"""Episode source-line operations for the SQLite Memory adapter."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from elfie.brain.memory.memory_records import (
    ClosedEpisode,
    EpisodeReceipt,
    MediaReference,
    SourceReference,
)

from .sqlite_utils import canonical_json, content_hash, json_list, json_object, utc_now


class EpisodeIdempotencyError(ValueError):
    """The same idempotency key was submitted with different source content."""


class SQLiteEpisodeStoreMixin:
    conn: sqlite3.Connection

    def record_episode(self, episode: ClosedEpisode) -> EpisodeReceipt:
        digest = content_hash(episode.content_text)
        with self._lock:
            now = utc_now()
            metadata = {
                **dict(episode.metadata),
                "emotion": episode.emotion,
                "emotion_intensity": episode.emotion_intensity,
                "stimulus": episode.stimulus,
                "sensory": dict(episode.sensory),
            }
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                # The read belongs inside the write transaction.  Otherwise
                # two connections can both observe "missing" and race into a
                # misleading UNIQUE failure instead of returning the same
                # idempotent receipt.
                existing = self.conn.execute(
                    "SELECT episode_id, idempotency_key, content_sha256 FROM episodes "
                    "WHERE idempotency_key=? OR episode_id=?",
                    (episode.idempotency_key, episode.episode_id),
                ).fetchone()
                if existing is not None:
                    if str(existing["idempotency_key"]) != episode.idempotency_key:
                        raise ValueError(
                            "episode_id was already used with a different idempotency key"
                        )
                    if str(existing["content_sha256"]) != digest:
                        raise EpisodeIdempotencyError(
                            "idempotency key was already used for different content"
                        )
                    self.conn.commit()
                    return EpisodeReceipt(
                        episode_id=str(existing["episode_id"]),
                        idempotency_key=episode.idempotency_key,
                        status="duplicate",
                        content_sha256=digest,
                    )
                self.conn.execute(
                    """INSERT INTO episodes (
                        episode_id, idempotency_key, occurred_from, occurred_to,
                        content_text, summary_text, event_kind, source_refs_json,
                        media_refs_json, source_event_ids_json, importance,
                        detail_level, content_sha256, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        episode.episode_id,
                        episode.idempotency_key,
                        episode.occurred_from,
                        episode.occurred_to,
                        episode.content_text,
                        episode.summary_text,
                        episode.event_kind,
                        canonical_json(
                            [_source_to_dict(ref) for ref in episode.source_refs]
                        ),
                        canonical_json(
                            [_media_to_dict(ref) for ref in episode.media_refs]
                        ),
                        canonical_json(list(episode.source_event_ids)),
                        episode.importance,
                        episode.detail_level,
                        digest,
                        canonical_json(metadata),
                        now,
                        now,
                    ),
                )
                self._upsert_episode_fts(episode.episode_id, episode)
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        return EpisodeReceipt(
            episode_id=episode.episode_id,
            idempotency_key=episode.idempotency_key,
            status="committed",
            content_sha256=digest,
        )

    def get_episode(self, episode_id: str) -> Optional[ClosedEpisode]:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM episodes WHERE episode_id=?", (episode_id,)
            ).fetchone()
        return None if row is None else _row_to_episode(row)

    def pending_episodes(self, limit: int = 8) -> tuple[ClosedEpisode, ...]:
        if limit < 1:
            return ()
        now = utc_now()
        with self._lock:
            rows = self.conn.execute(
                """SELECT * FROM episodes
                   WHERE lifecycle='active'
                     AND consolidation_state IN ('pending', 'failed')
                     AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                   ORDER BY occurred_from, episode_id LIMIT ?""",
                (now, limit),
            ).fetchall()
        return tuple(_row_to_episode(row) for row in rows)

    def claim_episodes(
        self,
        limit: int = 8,
        *,
        owner: str = "memory-worker",
        lease_seconds: int = 120,
    ) -> tuple[ClosedEpisode, ...]:
        if limit < 1:
            return ()
        now = datetime.now(timezone.utc)
        now_text = now.isoformat(timespec="milliseconds")
        lease_until = (now + timedelta(seconds=max(1, lease_seconds))).isoformat(
            timespec="milliseconds"
        )
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                rows = self.conn.execute(
                    """SELECT episode_id FROM episodes
                       WHERE lifecycle='active'
                         AND consolidation_state IN ('pending', 'failed')
                         AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                         AND (lease_until IS NULL OR lease_until < ?)
                       ORDER BY occurred_from, episode_id LIMIT ?""",
                    (now_text, now_text, limit),
                ).fetchall()
                episode_ids = [str(row["episode_id"]) for row in rows]
                for episode_id in episode_ids:
                    self.conn.execute(
                        """UPDATE episodes SET consolidation_state='processing',
                               lease_owner=?, lease_until=?,
                               consolidation_attempts=consolidation_attempts+1,
                               updated_at=? WHERE episode_id=?""",
                        (owner, lease_until, now_text, episode_id),
                    )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        return tuple(
            episode
            for episode_id in episode_ids
            if (episode := self.get_episode(episode_id)) is not None
        )

    def mark_episode_consolidated(self, episode_id: str) -> bool:
        return self._update_episode_state(episode_id, "consolidated", None)

    def mark_episode_failed(self, episode_id: str, error: str) -> bool:
        return self._update_episode_state(episode_id, "failed", error)

    def archive_episode(self, episode_id: str, summary_text: str | None = None) -> bool:
        """Retain a compact searchable Episode without deleting its source row."""
        with self._lock:
            row = self.conn.execute(
                "SELECT content_text, summary_text FROM episodes WHERE episode_id=?",
                (episode_id,),
            ).fetchone()
            if row is None:
                return False
            summary = (
                summary_text or row["summary_text"] or str(row["content_text"])[:512]
            )
            cursor = self.conn.execute(
                """UPDATE episodes SET lifecycle='archived', detail_level='compressed',
                       summary_text=?, updated_at=? WHERE episode_id=?""",
                (summary, utc_now(), episode_id),
            )
            self._upsert_episode_fts_from_values(
                episode_id, str(row["content_text"]), summary
            )
            self.conn.commit()
        return cursor.rowcount > 0

    def recover_expired_leases(self) -> int:
        """Return abandoned processing work to the retryable queue."""
        now = utc_now()
        with self._lock:
            cursor = self.conn.execute(
                """UPDATE episodes SET consolidation_state='failed', lease_owner=NULL,
                       lease_until=NULL, next_attempt_at=?, updated_at=?
                   WHERE consolidation_state='processing'
                     AND (lease_until IS NULL OR lease_until < ?)""",
                (now, now, now),
            )
            self.conn.commit()
        return cursor.rowcount

    def forget_episode(self, episode_id: str, *, retain_digest: bool = True) -> bool:
        """Forget detail while retaining an auditable source stub when needed."""
        with self._lock:
            row = self.conn.execute(
                "SELECT content_sha256 FROM episodes WHERE episode_id=?", (episode_id,)
            ).fetchone()
            if row is None:
                return False
            content = (
                f"[forgotten:{row['content_sha256']}]"
                if retain_digest
                else "[forgotten]"
            )
            self.conn.execute(
                """UPDATE episodes SET content_text=?, summary_text=NULL,
                       detail_level='digest', lifecycle='forgotten', updated_at=?
                   WHERE episode_id=?""",
                (content, utc_now(), episode_id),
            )
            self._upsert_episode_fts(
                episode_id,
                ClosedEpisode(
                    episode_id=episode_id,
                    idempotency_key=f"forget:{episode_id}",
                    occurred_from="1970-01-01T00:00:00+00:00",
                    content_text=content,
                ),
            )
            self.conn.commit()
        return True

    def _update_episode_state(
        self,
        episode_id: str,
        state: str,
        error: Optional[str],
    ) -> bool:
        with self._lock:
            metadata_row = self.conn.execute(
                "SELECT metadata_json, consolidation_attempts FROM episodes WHERE episode_id=?",
                (episode_id,),
            ).fetchone()
            if metadata_row is None:
                return False
            metadata = json_object(metadata_row["metadata_json"])
            if error:
                metadata["last_error"] = error
            else:
                metadata.pop("last_error", None)
            attempts = int(metadata_row["consolidation_attempts"] or 0)
            retry_at = None
            if state != "consolidated":
                delay = min(3600, 2 ** min(attempts, 10))
                retry_at = (
                    datetime.now(timezone.utc) + timedelta(seconds=delay)
                ).isoformat(timespec="milliseconds")
            cursor = self.conn.execute(
                """UPDATE episodes SET consolidation_state=?, lease_owner=NULL,
                       lease_until=NULL, next_attempt_at=?, metadata_json=?, updated_at=?
                   WHERE episode_id=?""",
                (
                    state,
                    retry_at,
                    canonical_json(metadata),
                    utc_now(),
                    episode_id,
                ),
            )
            changed = cursor.rowcount > 0
            self.conn.commit()
        return changed

    def _upsert_episode_fts(self, episode_id: str, episode: ClosedEpisode) -> None:
        searchable = "\n".join(
            value
            for value in (episode.content_text, episode.summary_text or "")
            if value
        )
        self.conn.execute(
            """INSERT INTO episodes_fts(episode_id, searchable_text) VALUES (?, ?)
               ON CONFLICT(episode_id) DO UPDATE SET searchable_text=excluded.searchable_text""",
            (episode_id, searchable),
        )


def _source_to_dict(ref: SourceReference) -> dict[str, Optional[str]]:
    return {
        "source_id": ref.source_id,
        "source_kind": ref.source_kind,
        "locator": ref.locator,
    }


def _media_to_dict(ref: MediaReference) -> dict[str, Any]:
    return {
        "media_id": ref.media_id,
        "uri": ref.uri,
        "mime_type": ref.mime_type,
        "size_bytes": ref.size_bytes,
        "sha256": ref.sha256,
    }


def _row_to_episode(row: sqlite3.Row) -> ClosedEpisode:
    metadata = json_object(row["metadata_json"])
    sources = tuple(
        SourceReference(
            source_id=str(item.get("source_id", "")),
            source_kind=str(item.get("source_kind", "event")),
            locator=item.get("locator"),
        )
        for item in json_list(row["source_refs_json"])
        if isinstance(item, dict) and str(item.get("source_id", "")).strip()
    )
    media = tuple(
        MediaReference(
            media_id=str(item.get("media_id", "")),
            uri=str(item.get("uri", "")),
            mime_type=str(item.get("mime_type", "application/octet-stream")),
            size_bytes=item.get("size_bytes"),
            sha256=item.get("sha256"),
        )
        for item in json_list(row["media_refs_json"])
        if isinstance(item, dict) and str(item.get("media_id", "")).strip()
    )
    sensory = metadata.get("sensory", {})
    pairs = (
        tuple((str(key), str(value)) for key, value in sensory.items())
        if isinstance(sensory, dict)
        else ()
    )
    return ClosedEpisode(
        episode_id=str(row["episode_id"]),
        idempotency_key=str(row["idempotency_key"]),
        occurred_from=str(row["occurred_from"]),
        occurred_to=row["occurred_to"],
        content_text=str(row["content_text"]),
        summary_text=row["summary_text"],
        event_kind=str(row["event_kind"]),
        source_refs=sources,
        media_refs=media,
        source_event_ids=tuple(
            str(value) for value in json_list(row["source_event_ids_json"])
        ),
        importance=float(row["importance"]),
        detail_level=str(row["detail_level"]),
        emotion=metadata.get("emotion"),
        emotion_intensity=metadata.get("emotion_intensity"),
        stimulus=metadata.get("stimulus"),
        sensory=pairs,
        metadata={
            str(key): value
            for key, value in metadata.items()
            if key not in {"emotion", "emotion_intensity", "stimulus", "sensory"}
        },
    )


__all__ = ["EpisodeIdempotencyError", "SQLiteEpisodeStoreMixin"]
