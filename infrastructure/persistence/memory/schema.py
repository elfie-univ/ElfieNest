"""Target SQLite schema for one Elfie's episodic and graph Memory.

Episodes are the durable source line. Nodes, assertions and evidence are
qualified projections and every derived text index can be rebuilt.
"""

from __future__ import annotations

from typing import Final

SCHEMA_VERSION: Final[int] = 5

KNOWLEDGE_TABLES: Final[tuple[str, ...]] = (
    "episodes",
    "nodes",
    "node_aliases",
    "node_descriptions",
    "episode_mentions",
    "assertions",
    "evidence",
    "assertion_evidence",
    # Adapter-private operational/package metadata.  These are intentionally
    # not semantic Memory records and are never returned by Recall.
    "memory_genesis_submissions",
    "memory_maintenance",
    "projection_diagnostics",
)

SCHEMA_SQL: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS episodes (
        episode_id TEXT PRIMARY KEY NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE,
        occurred_from TEXT,
        occurred_to TEXT,
        occurrence_precision TEXT NOT NULL DEFAULT 'exact'
            CHECK (occurrence_precision IN ('exact', 'range', 'unknown')),
        content_text TEXT NOT NULL CHECK (length(trim(content_text)) > 0),
        summary_text TEXT,
        event_kind TEXT NOT NULL DEFAULT 'interaction'
            CHECK (length(trim(event_kind)) > 0),
        source_refs_json TEXT NOT NULL DEFAULT '[]'
            CHECK (json_valid(source_refs_json)),
        media_refs_json TEXT NOT NULL DEFAULT '[]'
            CHECK (json_valid(media_refs_json)),
        source_event_ids_json TEXT NOT NULL DEFAULT '[]'
            CHECK (json_valid(source_event_ids_json)),
        life_stage TEXT,
        temporal_label TEXT,
        context_text TEXT,
        attribution TEXT NOT NULL DEFAULT 'observed'
            CHECK (attribution IN ('observed', 'told', 'inferred', 'felt')),
        privacy_scope TEXT NOT NULL DEFAULT 'private'
            CHECK (length(trim(privacy_scope)) > 0),
        source_version TEXT,
        importance REAL NOT NULL DEFAULT 0.5
            CHECK (importance >= 0.0 AND importance <= 1.0),
        detail_level TEXT NOT NULL DEFAULT 'full'
            CHECK (detail_level IN ('full', 'compressed', 'digest', 'incomplete')),
        lifecycle TEXT NOT NULL DEFAULT 'active'
            CHECK (lifecycle IN ('active', 'archived', 'forgotten')),
        consolidation_state TEXT NOT NULL DEFAULT 'pending'
            CHECK (consolidation_state IN ('pending', 'processing', 'consolidated', 'failed')),
        consolidation_attempts INTEGER NOT NULL DEFAULT 0
            CHECK (consolidation_attempts >= 0),
        next_attempt_at TEXT,
        lease_owner TEXT,
        lease_until TEXT,
        content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
        projection_revision TEXT,
        projection_source_sha256 TEXT
            CHECK (projection_source_sha256 IS NULL OR length(projection_source_sha256) = 64),
        last_reinforced_at TEXT,
        last_reviewed_at TEXT,
        next_review_at TEXT,
        policy_version TEXT NOT NULL DEFAULT 'memory.v1'
            CHECK (length(trim(policy_version)) > 0),
        genesis_submission_id TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}'
            CHECK (json_valid(metadata_json)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (
            (occurrence_precision = 'unknown' AND occurred_from IS NULL)
            OR (occurrence_precision IN ('exact', 'range') AND occurred_from IS NOT NULL)
        )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nodes (
        node_id TEXT PRIMARY KEY NOT NULL,
        node_type TEXT NOT NULL CHECK (length(trim(node_type)) > 0),
        canonical_label TEXT NOT NULL CHECK (length(trim(canonical_label)) > 0),
        normalized_label TEXT NOT NULL CHECK (length(trim(normalized_label)) > 0),
        description TEXT,
        scope TEXT NOT NULL DEFAULT 'elfie'
            CHECK (length(trim(scope)) > 0),
        status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'candidate', 'unresolved', 'forgotten')),
        confidence REAL NOT NULL DEFAULT 0.5
            CHECK (confidence >= 0.0 AND confidence <= 1.0),
        importance REAL NOT NULL DEFAULT 0.5
            CHECK (importance >= 0.0 AND importance <= 1.0),
        properties_json TEXT NOT NULL DEFAULT '{}'
            CHECK (json_valid(properties_json)),
        merged_into TEXT REFERENCES nodes(node_id) ON DELETE RESTRICT,
        first_seen_at TEXT,
        last_seen_at TEXT,
        updated_at TEXT NOT NULL,
        privacy_scope TEXT NOT NULL DEFAULT 'private'
            CHECK (length(trim(privacy_scope)) > 0),
        genesis_submission_id TEXT,
        last_reinforced_at TEXT,
        last_reviewed_at TEXT,
        next_review_at TEXT,
        policy_version TEXT NOT NULL DEFAULT 'memory.v1'
            CHECK (length(trim(policy_version)) > 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS node_aliases (
        alias_id TEXT PRIMARY KEY NOT NULL,
        node_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE RESTRICT,
        alias TEXT NOT NULL CHECK (length(trim(alias)) > 0),
        normalized_alias TEXT NOT NULL CHECK (length(trim(normalized_alias)) > 0),
        scope TEXT NOT NULL DEFAULT 'elfie',
        evidence_id TEXT REFERENCES evidence(evidence_id) ON DELETE RESTRICT,
        confidence REAL NOT NULL DEFAULT 0.5
            CHECK (confidence >= 0.0 AND confidence <= 1.0),
        genesis_submission_id TEXT,
        created_at TEXT NOT NULL,
        UNIQUE (node_id, normalized_alias, scope)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS node_descriptions (
        description_id TEXT PRIMARY KEY NOT NULL,
        node_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE RESTRICT,
        text TEXT NOT NULL CHECK (length(trim(text)) > 0),
        language TEXT NOT NULL DEFAULT 'und',
        kind TEXT NOT NULL DEFAULT 'description',
        content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
        evidence_id TEXT REFERENCES evidence(evidence_id) ON DELETE RESTRICT,
        confidence REAL NOT NULL DEFAULT 0.5,
        genesis_submission_id TEXT,
        created_at TEXT NOT NULL,
        UNIQUE (node_id, language, kind, content_sha256)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS episode_mentions (
        mention_id TEXT PRIMARY KEY NOT NULL,
        episode_id TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE RESTRICT,
        node_id TEXT REFERENCES nodes(node_id) ON DELETE RESTRICT,
        resolution_state TEXT NOT NULL DEFAULT 'unresolved'
            CHECK (resolution_state IN ('resolved', 'ambiguous', 'unresolved')),
        role TEXT,
        surface_text TEXT NOT NULL CHECK (length(trim(surface_text)) > 0),
        span_start INTEGER CHECK (span_start IS NULL OR span_start >= 0),
        span_end INTEGER CHECK (span_end IS NULL OR span_end >= span_start),
        confidence REAL NOT NULL DEFAULT 0.5,
        genesis_submission_id TEXT,
        created_at TEXT NOT NULL,
        UNIQUE (episode_id, surface_text, span_start, span_end)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assertions (
        assertion_id TEXT PRIMARY KEY NOT NULL,
        subject_node_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE RESTRICT,
        predicate TEXT NOT NULL CHECK (length(trim(predicate)) > 0),
        object_node_id TEXT REFERENCES nodes(node_id) ON DELETE RESTRICT,
        object_literal_json TEXT,
        object_unit TEXT,
        polarity TEXT NOT NULL DEFAULT 'positive'
            CHECK (polarity IN ('positive', 'negative')),
        epistemic_status TEXT NOT NULL DEFAULT 'known'
            CHECK (epistemic_status IN ('known', 'believed', 'uncertain', 'reported')),
        viewpoint TEXT,
        context TEXT,
        valid_from TEXT,
        valid_to TEXT,
        object_literal_type TEXT,
        confidence REAL NOT NULL DEFAULT 0.5
            CHECK (confidence >= 0.0 AND confidence <= 1.0),
        importance REAL NOT NULL DEFAULT 0.5
            CHECK (importance >= 0.0 AND importance <= 1.0),
        conflict_group TEXT,
        supersedes_assertion_id TEXT REFERENCES assertions(assertion_id) ON DELETE RESTRICT,
        predicate_registry_version TEXT NOT NULL DEFAULT 'memory.predicates.v1'
            CHECK (length(trim(predicate_registry_version)) > 0),
        policy_version TEXT NOT NULL DEFAULT 'memory.v1'
            CHECK (length(trim(policy_version)) > 0),
        genesis_submission_id TEXT,
        last_reinforced_at TEXT,
        last_reviewed_at TEXT,
        next_review_at TEXT,
        fingerprint TEXT NOT NULL UNIQUE,
        lifecycle TEXT NOT NULL DEFAULT 'active'
            CHECK (lifecycle IN ('active', 'superseded', 'forgotten')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (
            (object_node_id IS NOT NULL AND object_literal_json IS NULL)
            OR (object_node_id IS NULL AND object_literal_json IS NOT NULL)
        ),
        CHECK (object_literal_json IS NULL OR json_valid(object_literal_json))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence (
        evidence_id TEXT PRIMARY KEY NOT NULL,
        source_type TEXT NOT NULL CHECK (source_type IN ('episode', 'seed')),
        source_id TEXT NOT NULL CHECK (length(trim(source_id)) > 0),
        excerpt TEXT,
        media_locator TEXT,
        modality TEXT NOT NULL DEFAULT 'text',
        span_start INTEGER CHECK (span_start IS NULL OR span_start >= 0),
        span_end INTEGER CHECK (span_end IS NULL OR span_end >= span_start),
        speaker TEXT,
        viewpoint TEXT,
        captured_at TEXT,
        extraction_run_id TEXT,
        source_sha256 TEXT,
        source_version TEXT,
        attribution TEXT
            CHECK (attribution IS NULL OR attribution IN ('observed', 'told', 'inferred', 'felt')),
        genesis_submission_id TEXT,
        created_at TEXT NOT NULL,
        UNIQUE (source_type, source_id, source_version, modality, span_start, span_end, media_locator)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assertion_evidence (
        assertion_id TEXT NOT NULL REFERENCES assertions(assertion_id) ON DELETE RESTRICT,
        evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id) ON DELETE RESTRICT,
        stance TEXT NOT NULL DEFAULT 'supports'
            CHECK (stance IN ('supports', 'contradicts', 'context')),
        genesis_submission_id TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY (assertion_id, evidence_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_genesis_submissions (
        submission_id TEXT NOT NULL,
        elfie_id TEXT NOT NULL,
        manifest_id TEXT NOT NULL,
        source_version TEXT NOT NULL,
        content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
        expected_counts_json TEXT NOT NULL DEFAULT '{}'
            CHECK (json_valid(expected_counts_json)),
        expected_ids_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'committed'
            CHECK (status IN ('committed')),
        committed_at TEXT NOT NULL,
        PRIMARY KEY (elfie_id, submission_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_maintenance (
        work_id TEXT PRIMARY KEY NOT NULL,
        elfie_id TEXT NOT NULL,
        stage TEXT NOT NULL CHECK (stage IN ('consolidation', 'lifecycle')),
        target_id TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('pending', 'processing', 'completed', 'failed', 'skipped')),
        attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
        next_attempt_at TEXT,
        lease_owner TEXT,
        lease_until TEXT,
        last_error TEXT,
        checkpoint_json TEXT NOT NULL DEFAULT '{}'
            CHECK (json_valid(checkpoint_json)),
        updated_at TEXT NOT NULL,
        UNIQUE (elfie_id, stage, target_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS projection_diagnostics (
        diagnostic_id TEXT PRIMARY KEY NOT NULL,
        elfie_id TEXT NOT NULL,
        episode_id TEXT,
        predicate TEXT,
        reason TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}'
            CHECK (json_valid(payload_json)),
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS episodes_fts (
        episode_id TEXT PRIMARY KEY NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
        searchable_text TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nodes_fts (
        node_id TEXT PRIMARY KEY NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
        searchable_text TEXT NOT NULL
    )
    """,
)

INDEX_SQL: Final[tuple[str, ...]] = (
    "CREATE INDEX IF NOT EXISTS idx_episodes_lifecycle_attempt ON episodes(lifecycle, consolidation_state, next_attempt_at)",
    "CREATE INDEX IF NOT EXISTS idx_episodes_time ON episodes(occurred_from, occurred_to, occurrence_precision)",
    "CREATE INDEX IF NOT EXISTS idx_episodes_hash ON episodes(content_sha256)",
    "CREATE INDEX IF NOT EXISTS idx_episodes_review ON episodes(lifecycle, next_review_at, importance)",
    "CREATE INDEX IF NOT EXISTS idx_episodes_projection ON episodes(projection_revision, projection_source_sha256)",
    "CREATE INDEX IF NOT EXISTS idx_episodes_stage ON episodes(life_stage, temporal_label)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_label_type ON nodes(normalized_label, node_type, status)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_merged_into ON nodes(merged_into)",
    "CREATE INDEX IF NOT EXISTS idx_aliases_normalized ON node_aliases(normalized_alias, scope)",
    "CREATE INDEX IF NOT EXISTS idx_descriptions_node ON node_descriptions(node_id, language, kind)",
    "CREATE INDEX IF NOT EXISTS idx_mentions_node ON episode_mentions(node_id, resolution_state)",
    "CREATE INDEX IF NOT EXISTS idx_mentions_episode ON episode_mentions(episode_id)",
    "CREATE INDEX IF NOT EXISTS idx_assertions_subject_predicate ON assertions(subject_node_id, predicate, lifecycle)",
    "CREATE INDEX IF NOT EXISTS idx_assertions_object_predicate ON assertions(object_node_id, predicate, lifecycle)",
    # Recall is seed-driven and does not always constrain ``predicate``.
    # Keep lifecycle and deterministic ranking next to each endpoint so a
    # large graph does not fall back to scanning the lifecycle index for every
    # local-walk hop.
    "CREATE INDEX IF NOT EXISTS idx_assertions_subject_lifecycle ON assertions(subject_node_id, lifecycle, importance DESC, confidence DESC, assertion_id)",
    "CREATE INDEX IF NOT EXISTS idx_assertions_object_lifecycle ON assertions(object_node_id, lifecycle, importance DESC, confidence DESC, assertion_id)",
    "CREATE INDEX IF NOT EXISTS idx_assertions_conflict ON assertions(conflict_group, lifecycle)",
    "CREATE INDEX IF NOT EXISTS idx_assertions_supersedes ON assertions(supersedes_assertion_id)",
    "CREATE INDEX IF NOT EXISTS idx_assertions_review ON assertions(lifecycle, importance, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source_type, source_id, source_version)",
    "CREATE INDEX IF NOT EXISTS idx_assertion_evidence_assertion ON assertion_evidence(assertion_id, stance)",
    "CREATE INDEX IF NOT EXISTS idx_assertion_evidence_evidence ON assertion_evidence(evidence_id)",
    "CREATE INDEX IF NOT EXISTS idx_genesis_submission_elfie ON memory_genesis_submissions(elfie_id, manifest_id)",
    "CREATE INDEX IF NOT EXISTS idx_maintenance_due ON memory_maintenance(elfie_id, stage, state, next_attempt_at)",
    "CREATE INDEX IF NOT EXISTS idx_diagnostics_episode ON projection_diagnostics(elfie_id, episode_id, created_at)",
)


__all__ = ["INDEX_SQL", "KNOWLEDGE_TABLES", "SCHEMA_SQL", "SCHEMA_VERSION"]
