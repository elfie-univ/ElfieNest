"""Episode source-line operations for the SQLite Memory adapter."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

from elfie.brain.memory.memory_records import (
    ClosedEpisode,
    EpisodeReceipt,
    MediaReference,
    OccurrencePrecision,
    RetentionProfile,
    SourceReference,
)
from elfie.brain.memory.score_policy import ImportanceEvent, MemoryScorePolicy

from .sqlite_mixin_base import SQLiteMemoryMixinBase
from .sqlite_utils import (
    canonical_json,
    content_hash,
    json_list,
    json_object,
    stable_id,
    utc_now,
)


class EpisodeIdempotencyError(ValueError):
    """The same idempotency key was submitted with different source content."""


class SQLiteEpisodeStoreMixin(SQLiteMemoryMixinBase):
    conn: sqlite3.Connection

    def record_episode(self, episode: ClosedEpisode) -> EpisodeReceipt:
        configured_elfie = getattr(self, "elfie_id", None)
        if configured_elfie is not None:
            supplied_elfie = episode.metadata.get("elfie_id")
            if supplied_elfie is not None and str(supplied_elfie) != str(
                configured_elfie
            ):
                raise ValueError("Episode belongs to a different Elfie namespace")
        digest = _episode_hash(episode)
        if episode.content_sha256 is not None and episode.content_sha256 != digest:
            raise ValueError(
                "content_sha256 does not match the complete Episode source"
            )
        with self._lock:
            now = utc_now()
            active_submission = getattr(self, "_active_genesis_submission_id", None)
            retention_profile: RetentionProfile = (
                "genesis"
                if active_submission is not None
                else episode.retention_profile
            )
            half_life_days = MemoryScorePolicy.admission_half_life(
                retention_profile,
                emotion_intensity=episode.emotion_intensity,
                sensory_present=bool(episode.sensory),
                genesis=active_submission is not None,
            )
            # Genesis stores historical occurrence separately but starts the
            # retention clock at this admission.  Otherwise a seed written
            # with an old historical date would already be archival on its
            # first read despite the fixed ten-year Genesis span.
            anchor = (
                episode.last_reinforced_at
                or (now if active_submission is not None else episode.occurred_from)
                or now
            )
            if episode.occurred_from is not None:
                MemoryScorePolicy.validate_event_time(
                    now=now, occurred_at=episode.occurred_from
                )
            if episode.occurred_to is not None:
                MemoryScorePolicy.validate_event_time(
                    now=now, occurred_at=episode.occurred_to
                )
            MemoryScorePolicy.validate_event_time(now=now, occurred_at=anchor)
            # ``next_review_at`` is derived state.  Ignore a caller-supplied
            # stale value so lifecycle scheduling cannot be forged independently
            # of the immutable retention anchor.
            next_review_at = MemoryScorePolicy.next_review_at(
                anchor,
                half_life_days,
                MemoryScorePolicy.active_freshness_threshold,
            ).isoformat(timespec="milliseconds")
            metadata = {
                **dict(episode.metadata),
                "emotion": episode.emotion,
                "emotion_intensity": episode.emotion_intensity,
                "stimulus": episode.stimulus,
                "sensory": dict(episode.sensory),
            }
            if configured_elfie is not None:
                metadata["elfie_id"] = str(configured_elfie)
            if (
                active_submission is not None
                and episode.genesis_submission_id is not None
                and episode.genesis_submission_id != active_submission
            ):
                raise ValueError(
                    "Episode genesis submission does not match the active submission"
                )
            genesis_submission_id = active_submission or episode.genesis_submission_id
            owns = self._begin_write_transaction()
            try:
                # The read belongs inside the write transaction.  Otherwise
                # two connections can both observe "missing" and race into a
                # misleading UNIQUE failure instead of returning the same
                # idempotent receipt.
                existing = self.conn.execute(
                    "SELECT episode_id, idempotency_key, content_sha256, metadata_json FROM episodes "
                    "WHERE idempotency_key=? OR episode_id=?",
                    (episode.idempotency_key, episode.episode_id),
                ).fetchone()
                if existing is not None:
                    if configured_elfie is not None:
                        stored_metadata = json_object(existing["metadata_json"])
                        if stored_metadata.get("elfie_id") not in {
                            str(configured_elfie),
                        }:
                            raise ValueError(
                                "episode identity belongs to a different Elfie namespace"
                            )
                    if str(existing["idempotency_key"]) != episode.idempotency_key:
                        raise ValueError(
                            "episode_id was already used with a different idempotency key"
                        )
                    if str(existing["content_sha256"]) != digest:
                        raise EpisodeIdempotencyError(
                            "idempotency key was already used for different content"
                        )
                    self._commit_write_transaction(owns)
                    return EpisodeReceipt(
                        episode_id=str(existing["episode_id"]),
                        idempotency_key=episode.idempotency_key,
                        status="duplicate",
                        content_sha256=digest,
                    )
                self.conn.execute(
                    """INSERT INTO episodes (
                        episode_id, idempotency_key, occurred_from, occurred_to,
                        occurrence_precision, content_text, summary_text, event_kind,
                        source_refs_json, media_refs_json, source_event_ids_json,
                        life_stage, temporal_label, context_text, attribution,
                        privacy_scope, source_version, importance, initial_importance,
                        half_life_days, retention_profile,
                        detail_level,
                        content_sha256, projection_revision, projection_source_sha256,
                        last_reinforced_at, last_reviewed_at, next_review_at,
                        lifecycle_changed_at, policy_version, genesis_submission_id, metadata_json,
                        created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?
                    )""",
                    (
                        episode.episode_id,
                        episode.idempotency_key,
                        episode.occurred_from,
                        episode.occurred_to,
                        episode.occurrence_precision,
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
                        episode.life_stage,
                        episode.temporal_label,
                        episode.context_text,
                        episode.attribution,
                        episode.privacy_scope,
                        episode.source_version,
                        episode.importance,
                        episode.initial_importance,
                        half_life_days,
                        retention_profile,
                        episode.detail_level,
                        digest,
                        episode.projection_revision,
                        episode.projection_source_sha256,
                        anchor,
                        episode.last_reviewed_at,
                        next_review_at,
                        now,
                        MemoryScorePolicy.version,
                        genesis_submission_id,
                        canonical_json(metadata),
                        now,
                        now,
                    ),
                )
                self._record_importance_event_locked(
                    ImportanceEvent(
                        event_id=stable_id(
                            "importance-event:",
                            "episode",
                            episode.episode_id,
                            "admission",
                            length=48,
                        ),
                        target_kind="episode",
                        target_id=episode.episode_id,
                        direction="raise",
                        event_class="admission",
                        source_episode_id=None,
                        occurred_at=anchor,
                    ),
                    now,
                )
                self._upsert_episode_fts(episode.episode_id, episode)
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
        return EpisodeReceipt(
            episode_id=episode.episode_id,
            idempotency_key=episode.idempotency_key,
            status="committed",
            content_sha256=digest,
        )

    def get_episode(self, episode_id: str) -> Optional[ClosedEpisode]:
        with self._lock:
            scope = ""
            params: list[object] = [episode_id]
            if getattr(self, "elfie_id", None) is not None:
                scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                params.append(str(self.elfie_id))
            visibility, visibility_params = self._genesis_visibility("e")
            params.extend(visibility_params)
            row = self.conn.execute(
                "SELECT e.* FROM episodes AS e WHERE e.episode_id=?"
                + scope
                + " AND "
                + visibility,
                params,
            ).fetchone()
        return None if row is None else _row_to_episode(row)

    def list_episodes(
        self, limit: int = 1000, *, include_forgotten: bool = False
    ) -> tuple[ClosedEpisode, ...]:
        """Return a bounded, typed read-only view of the Episode source line."""
        bounded_limit = max(0, min(int(limit), 10_000))
        if bounded_limit == 0:
            return ()
        with self._lock:
            scope = ""
            params: list[object] = []
            if not include_forgotten:
                scope += " AND e.lifecycle <> 'forgotten'"
            if getattr(self, "elfie_id", None) is not None:
                scope += " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                params.append(str(self.elfie_id))
            visibility, visibility_params = self._genesis_visibility("e")
            params.extend(visibility_params)
            params.append(bounded_limit)
            rows = self.conn.execute(
                """SELECT e.* FROM episodes AS e
                   WHERE 1=1"""
                + scope
                + " AND "
                + visibility
                + " ORDER BY e.occurred_from IS NULL, e.occurred_from, e.episode_id LIMIT ?",
                params,
            ).fetchall()
        return tuple(_row_to_episode(row) for row in rows)

    def pending_episodes(self, limit: int = 8) -> tuple[ClosedEpisode, ...]:
        if limit < 1:
            return ()
        now = utc_now()
        with self._lock:
            scope = ""
            params: list[object] = [now, limit]
            if getattr(self, "elfie_id", None) is not None:
                scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                params = [now, str(self.elfie_id), limit]
            visibility, visibility_params = self._genesis_visibility("e")
            params[-1:-1] = visibility_params
            rows = self.conn.execute(
                """SELECT e.* FROM episodes AS e
                   WHERE e.lifecycle='active'
                     AND e.consolidation_state IN ('pending', 'failed')
                     AND (e.projection_revision IS NULL OR e.projection_source_sha256 IS NULL
                          OR e.projection_source_sha256 <> e.content_sha256)
                     AND (e.next_attempt_at IS NULL OR e.next_attempt_at <= ?)"""
                + scope
                + " AND "
                + visibility
                + " ORDER BY occurred_from IS NULL, occurred_from, episode_id LIMIT ?",
                params,
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
            owns = self._begin_write_transaction()
            try:
                scope = ""
                select_params: list[object] = [now_text, now_text]
                if getattr(self, "elfie_id", None) is not None:
                    scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                    select_params.append(str(self.elfie_id))
                visibility, visibility_params = self._genesis_visibility("e")
                select_params.extend(visibility_params)
                select_params.append(limit)
                rows = self.conn.execute(
                    """SELECT e.episode_id, e.consolidation_attempts FROM episodes AS e
                       WHERE e.lifecycle='active'
                         AND e.consolidation_state IN ('pending', 'failed')
                         AND (e.projection_revision IS NULL OR e.projection_source_sha256 IS NULL
                              OR e.projection_source_sha256 <> e.content_sha256)
                         AND (e.next_attempt_at IS NULL OR e.next_attempt_at <= ?)
                         AND (e.lease_until IS NULL OR e.lease_until < ?)"""
                    + scope
                    + " AND "
                    + visibility
                    + " ORDER BY occurred_from IS NULL, occurred_from, episode_id LIMIT ?",
                    select_params,
                ).fetchall()
                episode_attempts = {
                    str(row["episode_id"]): int(row["consolidation_attempts"] or 0) + 1
                    for row in rows
                }
                episode_ids = list(episode_attempts)
                for episode_id in episode_ids:
                    self.conn.execute(
                        """UPDATE episodes SET consolidation_state='processing',
                               lease_owner=?, lease_until=?,
                               consolidation_attempts=consolidation_attempts+1,
                               updated_at=? WHERE episode_id=?""",
                        (owner, lease_until, now_text, episode_id),
                    )
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
        claimed: list[ClosedEpisode] = []
        for episode_id in episode_ids:
            episode = self.get_episode(episode_id)
            if episode is None:
                continue
            claimed.append(
                replace(
                    episode,
                    metadata={
                        **dict(episode.metadata),
                        "_memory_claim_owner": owner,
                        "_memory_claim_attempt": episode_attempts[episode_id],
                    },
                )
            )
        return tuple(claimed)

    def mark_episode_consolidated(self, episode_id: str) -> bool:
        return self._update_episode_state(episode_id, "consolidated", None)

    def mark_episode_failed(
        self,
        episode_id: str,
        error: str,
        *,
        owner: str | None = None,
        attempt: int | None = None,
    ) -> bool:
        return self._update_episode_state(
            episode_id,
            "failed",
            error,
            owner=owner,
            attempt=attempt,
        )

    def archive_episode(self, episode_id: str, summary_text: str | None = None) -> bool:
        """Retain a compact searchable Episode without deleting its source row."""
        with self._lock:
            scope = ""
            select_params: list[object] = [episode_id]
            if getattr(self, "elfie_id", None) is not None:
                scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                select_params.append(str(self.elfie_id))
            visibility, visibility_params = self._genesis_visibility("e")
            select_params.extend(visibility_params)
            row = self.conn.execute(
                "SELECT e.content_text, e.summary_text FROM episodes AS e "
                "WHERE e.episode_id=?" + scope + " AND " + visibility,
                select_params,
            ).fetchone()
            if row is None:
                return False
            summary = (
                summary_text or row["summary_text"] or str(row["content_text"])[:512]
            )
            owns = self._begin_write_transaction()
            try:
                cursor = self.conn.execute(
                    """UPDATE episodes SET lifecycle='archived', detail_level='compressed',
                           summary_text=?, updated_at=?, last_reviewed_at=?,
                           lifecycle_changed_at=CASE WHEN lifecycle<>'archived' THEN ? ELSE lifecycle_changed_at END,
                           next_review_at=NULL, policy_version=? WHERE episode_id=?""",
                    (
                        summary,
                        utc_now(),
                        utc_now(),
                        utc_now(),
                        MemoryScorePolicy.version,
                        episode_id,
                    ),
                )
                self._upsert_episode_fts_from_values(
                    episode_id, str(row["content_text"]), summary
                )
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
        return cursor.rowcount > 0

    def recover_expired_leases(self) -> int:
        """Return abandoned Episode projection work to the retryable queue."""
        now = utc_now()
        with self._lock:
            owns = self._begin_write_transaction()
            try:
                scope = ""
                params: list[object] = [now, now, now]
                if getattr(self, "elfie_id", None) is not None:
                    scope = " AND json_extract(metadata_json, '$.elfie_id')=?"
                    params.append(str(self.elfie_id))
                visibility, visibility_params = self._genesis_visibility("episodes")
                params.extend(visibility_params)
                cursor = self.conn.execute(
                    """UPDATE episodes SET consolidation_state='failed', lease_owner=NULL,
                           lease_until=NULL, next_attempt_at=?, updated_at=?
                       WHERE consolidation_state='processing'
                         AND (lease_until IS NULL OR lease_until < ?)"""
                    + scope
                    + " AND "
                    + visibility,
                    params,
                )
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
        return cursor.rowcount

    def forget_episode(self, episode_id: str, *, retain_digest: bool = True) -> bool:
        """Forget detail while retaining an auditable source stub when needed."""
        with self._lock:
            scope = ""
            select_params: list[object] = [episode_id]
            if getattr(self, "elfie_id", None) is not None:
                scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                select_params.append(str(self.elfie_id))
            visibility, visibility_params = self._genesis_visibility("e")
            select_params.extend(visibility_params)
            row = self.conn.execute(
                """SELECT e.content_sha256, e.projection_revision,
                          e.projection_source_sha256,
                          (SELECT COUNT(*) FROM evidence AS ev
                             WHERE ev.source_type='episode' AND ev.source_id=e.episode_id)
                             AS evidence_count,
                          (SELECT COUNT(*) FROM evidence AS ev
                             WHERE ev.source_type='episode' AND ev.source_id=e.episode_id
                               AND (ev.source_sha256 IS NULL
                                    OR ev.source_sha256 <> e.content_sha256))
                             AS ungrounded_evidence_count
                     FROM episodes AS e WHERE e.episode_id=?"""
                + scope
                + " AND "
                + visibility,
                select_params,
            ).fetchone()
            if row is None:
                return False
            if (
                row["projection_revision"] is None
                or row["projection_source_sha256"] != row["content_sha256"]
                or int(row["evidence_count"] or 0) < 1
                or int(row["ungrounded_evidence_count"] or 0) > 0
            ):
                # Forgetting is allowed only after the current source has a
                # complete, hash-bound Evidence audit trail.  An unprojected
                # or partially grounded Episode remains the source of truth.
                return False
            content = (
                f"[forgotten:{row['content_sha256']}]"
                if retain_digest
                else "[forgotten]"
            )
            owns = self._begin_write_transaction()
            try:
                self.conn.execute(
                    """UPDATE episodes SET content_text=?, summary_text=NULL,
                           detail_level='digest', lifecycle='forgotten',
                           lifecycle_changed_at=CASE WHEN lifecycle<>'forgotten' THEN ? ELSE lifecycle_changed_at END,
                           next_review_at=NULL, policy_version=?, updated_at=?
                       WHERE episode_id=?""",
                    (
                        content,
                        utc_now(),
                        MemoryScorePolicy.version,
                        utc_now(),
                        episode_id,
                    ),
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
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
        return True

    def _update_episode_state(
        self,
        episode_id: str,
        state: str,
        error: Optional[str],
        *,
        owner: str | None = None,
        attempt: int | None = None,
    ) -> bool:
        if (owner is None) != (attempt is None):
            raise ValueError("owner and attempt must be supplied together")
        with self._lock:
            scope = ""
            select_params: list[object] = [episode_id]
            if getattr(self, "elfie_id", None) is not None:
                scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                select_params.append(str(self.elfie_id))
            visibility, visibility_params = self._genesis_visibility("e")
            select_params.extend(visibility_params)
            metadata_row = self.conn.execute(
                "SELECT e.metadata_json, e.consolidation_attempts, "
                "e.consolidation_state, e.lease_owner, e.lease_until "
                "FROM episodes AS e WHERE e.episode_id=?"
                + scope
                + " AND "
                + visibility,
                select_params,
            ).fetchone()
            if metadata_row is None:
                return False
            if owner is not None:
                if (
                    str(metadata_row["consolidation_state"]) != "processing"
                    or str(metadata_row["lease_owner"] or "") != owner
                    or int(metadata_row["consolidation_attempts"] or 0) != attempt
                    or metadata_row["lease_until"] is None
                    or str(metadata_row["lease_until"]) <= utc_now()
                ):
                    # A worker that lost its lease must not overwrite the
                    # retry state written by a newer claimant.
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
            owns = self._begin_write_transaction()
            try:
                update_scope = ""
                update_params: list[object] = [
                    state,
                    retry_at,
                    canonical_json(metadata),
                    utc_now(),
                    episode_id,
                ]
                if getattr(self, "elfie_id", None) is not None:
                    update_scope = " AND json_extract(metadata_json, '$.elfie_id')=?"
                    update_params.append(str(self.elfie_id))
                if owner is not None:
                    update_scope += (
                        " AND consolidation_state='processing'"
                        " AND lease_owner=?"
                        " AND consolidation_attempts=?"
                        " AND lease_until>?"
                    )
                    update_params.extend((owner, attempt, utc_now()))
                cursor = self.conn.execute(
                    """UPDATE episodes SET consolidation_state=?, lease_owner=NULL,
                           lease_until=NULL, next_attempt_at=?, metadata_json=?, updated_at=?
                       WHERE episode_id=?"""
                    + update_scope,
                    update_params,
                )
                changed = cursor.rowcount > 0
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                raise
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

    def _upsert_episode_fts_from_values(
        self, episode_id: str, content: str, summary: str | None
    ) -> None:
        searchable = "\n".join(value for value in (content, summary or "") if value)
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
        "source_version": ref.source_version,
        "source_sha256": ref.source_sha256,
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
            source_version=item.get("source_version"),
            source_sha256=item.get("source_sha256"),
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
        occurred_from=(
            None if row["occurred_from"] is None else str(row["occurred_from"])
        ),
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
        initial_importance=float(row["initial_importance"] or row["importance"]),
        half_life_days=float(
            row["half_life_days"]
            or MemoryScorePolicy.initial_half_life_days["ordinary"]
        ),
        retention_profile=str(row["retention_profile"] or "ordinary"),  # type: ignore[arg-type]
        detail_level=str(row["detail_level"]),
        lifecycle=str(row["lifecycle"] or "active"),  # type: ignore[arg-type]
        emotion=metadata.get("emotion"),
        emotion_intensity=metadata.get("emotion_intensity"),
        stimulus=metadata.get("stimulus"),
        sensory=pairs,
        metadata={
            str(key): value
            for key, value in metadata.items()
            if key not in {"emotion", "emotion_intensity", "stimulus", "sensory"}
        },
        occurrence_precision=cast(
            OccurrencePrecision, str(row["occurrence_precision"] or "exact")
        ),
        life_stage=row["life_stage"],
        temporal_label=row["temporal_label"],
        context_text=row["context_text"],
        attribution=str(row["attribution"] or "observed"),  # type: ignore[arg-type]
        privacy_scope=str(row["privacy_scope"] or "private"),
        source_version=row["source_version"],
        projection_revision=row["projection_revision"],
        projection_source_sha256=row["projection_source_sha256"],
        last_reinforced_at=row["last_reinforced_at"],
        last_reviewed_at=row["last_reviewed_at"],
        next_review_at=row["next_review_at"],
        policy_version=str(row["policy_version"] or MemoryScorePolicy.version),
        genesis_submission_id=row["genesis_submission_id"],
        content_sha256=str(row["content_sha256"]),
    )


def _episode_hash(episode: ClosedEpisode) -> str:
    """Hash the complete source payload, never only its displayed text."""
    # These keys are adapter-owned derived fields.  They are persisted in
    # ``metadata_json`` for inspection, but are also stored in typed
    # columns/fields and removed again when an Episode is read back.  Exclude
    # them from the source digest so a caller can submit a read-back Episode
    # with the same source content and still receive the same idempotent hash.
    adapter_metadata_keys = {
        "elfie_id",
        "emotion",
        "emotion_intensity",
        "stimulus",
        "sensory",
        # Runtime bookkeeping must not turn a retry into a new source.
        "last_error",
        "written_at",
        "_memory_claim_owner",
        "_memory_claim_attempt",
    }
    source_metadata = {
        str(key): value
        for key, value in episode.metadata.items()
        if str(key) not in adapter_metadata_keys
    }
    payload = {
        "occurred_from": episode.occurred_from,
        "occurred_to": episode.occurred_to,
        "occurrence_precision": episode.occurrence_precision,
        "content_text": episode.content_text,
        "event_kind": episode.event_kind,
        "source_refs": [_source_to_dict(ref) for ref in episode.source_refs],
        "media_refs": [_media_to_dict(ref) for ref in episode.media_refs],
        "source_event_ids": list(episode.source_event_ids),
        "life_stage": episode.life_stage,
        "temporal_label": episode.temporal_label,
        "context_text": episode.context_text,
        "attribution": episode.attribution,
        "privacy_scope": episode.privacy_scope,
        "source_version": episode.source_version,
        "emotion": episode.emotion,
        "emotion_intensity": episode.emotion_intensity,
        "stimulus": episode.stimulus,
        "sensory": dict(episode.sensory),
        "metadata": source_metadata,
    }
    return content_hash(canonical_json(payload))


__all__ = ["EpisodeIdempotencyError", "SQLiteEpisodeStoreMixin"]
