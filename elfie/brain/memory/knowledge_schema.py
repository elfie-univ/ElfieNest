"""Final nine-table schema for per-Elfie knowledge storage."""

from __future__ import annotations

from typing import Final

KNOWLEDGE_TABLES: Final[tuple[str, ...]] = (
    "entities",
    "people",
    "known_elfies",
    "concepts",
    "places",
    "events",
    "entity_edges",
    "memory_notes",
    "source_evidence_links",
)

KNOWLEDGE_SCHEMA_SQL: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS entities (
        entity_id TEXT PRIMARY KEY NOT NULL,
        entity_type TEXT NOT NULL CHECK (
            entity_type IN ('person', 'elfie', 'concept', 'place', 'event', 'object')
        ),
        name TEXT NOT NULL CHECK (length(trim(name)) > 0),
        aliases_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(aliases_json)),
        summary TEXT,
        confidence REAL NOT NULL DEFAULT 0.5
            CHECK (confidence >= 0.0 AND confidence <= 1.0),
        first_seen_at TEXT,
        last_seen_at TEXT,
        updated_at TEXT,
        meta_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(meta_json))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS people (
        entity_id TEXT PRIMARY KEY NOT NULL
            REFERENCES entities(entity_id) ON DELETE CASCADE,
        display_name TEXT,
        relationship_label TEXT,
        closeness_score REAL NOT NULL DEFAULT 0.5
            CHECK (closeness_score >= 0.0 AND closeness_score <= 1.0),
        trust_score REAL NOT NULL DEFAULT 0.5
            CHECK (trust_score >= 0.0 AND trust_score <= 1.0),
        importance_score REAL NOT NULL DEFAULT 0.5
            CHECK (importance_score >= 0.0 AND importance_score <= 1.0),
        is_owner INTEGER NOT NULL DEFAULT 0 CHECK (is_owner IN (0, 1)),
        profile_summary TEXT,
        preferences_json TEXT NOT NULL DEFAULT '{}'
            CHECK (json_valid(preferences_json)),
        updated_at TEXT
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_people_single_owner
    ON people(is_owner) WHERE is_owner = 1
    """,
    """
    CREATE TABLE IF NOT EXISTS known_elfies (
        entity_id TEXT PRIMARY KEY NOT NULL
            REFERENCES entities(entity_id) ON DELETE CASCADE,
        elfie_id TEXT CHECK (elfie_id IS NULL OR length(trim(elfie_id)) > 0),
        display_name TEXT,
        species TEXT,
        is_self INTEGER NOT NULL DEFAULT 0 CHECK (is_self IN (0, 1)),
        relationship_label TEXT,
        closeness_score REAL NOT NULL DEFAULT 0.5
            CHECK (closeness_score >= 0.0 AND closeness_score <= 1.0),
        profile_summary TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_known_elfies_known_id
    ON known_elfies(elfie_id) WHERE elfie_id IS NOT NULL
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_known_elfies_single_self
    ON known_elfies(is_self) WHERE is_self = 1
    """,
    """
    CREATE TABLE IF NOT EXISTS concepts (
        entity_id TEXT PRIMARY KEY NOT NULL
            REFERENCES entities(entity_id) ON DELETE CASCADE,
        concept_type TEXT,
        definition TEXT,
        confidence REAL NOT NULL DEFAULT 0.5
            CHECK (confidence >= 0.0 AND confidence <= 1.0),
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS places (
        entity_id TEXT PRIMARY KEY NOT NULL
            REFERENCES entities(entity_id) ON DELETE CASCADE,
        place_type TEXT,
        description TEXT,
        meta_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(meta_json)),
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        entity_id TEXT PRIMARY KEY NOT NULL
            REFERENCES entities(entity_id) ON DELETE CASCADE,
        event_time TEXT,
        event_type TEXT,
        description TEXT,
        importance_score REAL NOT NULL DEFAULT 0.5
            CHECK (importance_score >= 0.0 AND importance_score <= 1.0),
        meta_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(meta_json)),
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS entity_edges (
        edge_id TEXT PRIMARY KEY NOT NULL,
        source_entity_id TEXT NOT NULL
            REFERENCES entities(entity_id) ON DELETE CASCADE,
        target_entity_id TEXT NOT NULL
            REFERENCES entities(entity_id) ON DELETE CASCADE,
        relation_type TEXT NOT NULL CHECK (length(trim(relation_type)) > 0),
        summary TEXT,
        weight REAL NOT NULL DEFAULT 0.5
            CHECK (weight >= 0.0 AND weight <= 1.0),
        confidence REAL NOT NULL DEFAULT 0.5
            CHECK (confidence >= 0.0 AND confidence <= 1.0),
        updated_at TEXT,
        UNIQUE (source_entity_id, target_entity_id, relation_type)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_entity_edges_sensory_relation
    ON entity_edges(relation_type, source_entity_id, target_entity_id, weight)
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_notes (
        note_id TEXT PRIMARY KEY NOT NULL,
        entity_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
        note_type TEXT NOT NULL CHECK (length(trim(note_type)) > 0),
        title TEXT,
        path TEXT NOT NULL CHECK (
            length(trim(path)) > 0
            AND instr(path, ':') = 0
            AND instr(path, char(92)) = 0
            AND path NOT LIKE '/%'
            AND path NOT LIKE '../%'
            AND path NOT LIKE '%/../%'
            AND path NOT LIKE '..'
            AND path NOT LIKE '%/..'
        ),
        summary TEXT,
        created_at TEXT,
        updated_at TEXT,
        meta_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(meta_json))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_evidence_links (
        link_id TEXT PRIMARY KEY NOT NULL,
        target_type TEXT NOT NULL CHECK (target_type IN ('entity', 'edge', 'note')),
        target_id TEXT NOT NULL CHECK (length(trim(target_id)) > 0),
        source_db TEXT NOT NULL CHECK (source_db = 'history'),
        source_type TEXT NOT NULL CHECK (source_type IN ('message', 'conversation')),
        source_id TEXT NOT NULL CHECK (length(trim(source_id)) > 0),
        weight REAL NOT NULL DEFAULT 0.5
            CHECK (weight >= 0.0 AND weight <= 1.0),
        created_at TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_entities_sensory_lookup
    ON entities(entity_type, name)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_source_evidence_target
    ON source_evidence_links(target_type, target_id)
    """,
)
