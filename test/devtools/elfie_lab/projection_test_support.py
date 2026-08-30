"""Shared typed-storage builders for memory projection tests."""

from elfie.brain.memory.memory_records import (
    AssertionInput,
    ClosedEpisode,
    EvidenceInput,
    NodeInput,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def add_node(
    storage: SQLiteMemoryStoreAdapter,
    node_id: str,
    node_type: str,
    content: str,
    metadata: dict = None,
    created_at: str = None,
) -> None:
    properties = dict(metadata or {})
    if node_type == "episodic":
        timestamp = created_at or str(
            properties.get("timestamp") or "2026-01-01T00:00:00+00:00"
        )
        importance = properties.get(
            "importance", properties.get("emotion_intensity", 0.5)
        )
        importance = float(importance) if isinstance(importance, (int, float)) else 0.5
        storage.record_episode(
            ClosedEpisode(
                episode_id=node_id,
                idempotency_key=f"test:{node_id}",
                occurred_from=timestamp,
                content_text=content,
                importance=max(0.0, min(1.0, importance)),
                emotion=(
                    properties.get("emotion")
                    if isinstance(properties.get("emotion"), str)
                    else None
                ),
                emotion_intensity=(
                    properties.get("emotion_intensity")
                    if isinstance(properties.get("emotion_intensity"), (int, float))
                    else None
                ),
                metadata=properties,
            )
        )
        return
    confidence = properties.get("confidence", 0.5)
    confidence = float(confidence) if isinstance(confidence, (int, float)) else 0.5
    importance = properties.get("importance", 0.5)
    importance = float(importance) if isinstance(importance, (int, float)) else 0.5
    storage.upsert_node_record(
        NodeInput(
            node_id=node_id,
            node_type=node_type,
            canonical_label=content,
            description=content,
            properties=properties,
            confidence=max(0.0, min(1.0, confidence)),
            importance=max(0.0, min(1.0, importance)),
        )
    )


def add_edge(
    storage: SQLiteMemoryStoreAdapter,
    source_id: str,
    target_id: str,
    predicate: str,
    weight: float = 0.5,
) -> None:
    evidence_id = f"test:evidence:{source_id}:{target_id}:{predicate}"
    storage.record_sourced_assertion(
        AssertionInput(
            subject_id=source_id,
            predicate=predicate,
            object_node_id=target_id,
            confidence=max(0.0, min(1.0, weight)),
            importance=max(0.0, min(1.0, weight)),
            evidence_ids=(evidence_id,),
        ),
        EvidenceInput(
            evidence_id=evidence_id,
            source_type="seed",
            source_id="projection-test",
            excerpt=f"{source_id} {predicate} {target_id}",
        ),
    )
