"""Relationship, world, and knowledge projections for the private profile."""

from __future__ import annotations

from typing import Final

from app.features.elfie_profile.private_cognition_types import (
    KnowledgeBeliefsPayload,
    KnowledgeEdgePayload,
    KnowledgeNodePayload,
    RelationshipEdgePayload,
    RelationshipNodePayload,
    RelationshipWorldPayload,
    WorldNodePayload,
    WorldRingPayload,
    WorldUnderstandingPayload,
)
from app.infrastructure.persistence.elfie_cognition_reader import (
    CognitionEdge,
    CognitionEntity,
)

_RINGS: Final[tuple[str, ...]] = ("self", "family", "nest", "society", "outside")
_KNOWLEDGE_RELATIONS: Final[frozenset[str]] = frozenset(
    {"derived_from", "supports", "conflicts", "revises"}
)


def relationship_world(
    entities: tuple[CognitionEntity, ...],
    edges: tuple[CognitionEdge, ...],
    elfie_id: str,
    elfie_name: str,
) -> RelationshipWorldPayload:
    """Keep self plus the nineteen most important visible people or Elfies."""
    del elfie_id
    candidates = [entity for entity in entities if _relationship_kind(entity) and not entity.is_self]
    candidates.sort(key=lambda entity: (-entity.weight, entity.name, entity.id))
    selected = candidates[:19]
    visible = {entity.id for entity in selected}
    self_ids = {entity.id for entity in entities if entity.is_self}
    nodes: list[RelationshipNodePayload] = [
        {"id": "self", "label": elfie_name, "kind": "self", "weight": 1.0}
    ]
    nodes.extend(
        {"id": entity.id, "label": entity.name or entity.id, "kind": _relationship_kind(entity) or "human", "weight": round(entity.weight, 6)}
        for entity in selected
    )
    relation_rows: dict[tuple[str, str, str], RelationshipEdgePayload] = {}
    for entity in selected:
        if entity.relationship_label or entity.relation_key:
            key = entity.relation_key or "relationship"
            relation_rows[("self", entity.id, key)] = {
                "source": "self", "target": entity.id, "relation_key": key,
                "display_label": entity.relationship_label, "weight": round(entity.weight, 6),
            }
    for edge in edges:
        source = "self" if edge.source in self_ids else edge.source
        target = "self" if edge.target in self_ids else edge.target
        if (source != "self" and source not in visible) or (target != "self" and target not in visible):
            continue
        if source == "self" and target == "self":
            continue
        key = edge.relation_type or "relationship"
        relation_rows[(source, target, key)] = {
            "source": source, "target": target, "relation_key": key,
            "display_label": edge.summary, "weight": round(edge.weight, 6),
        }
    relation_edges: list[RelationshipEdgePayload] = [
        relation_rows[key] for key in sorted(relation_rows)
    ]
    return {"nodes": nodes, "edges": relation_edges}


def world_understanding(
    entities: tuple[CognitionEntity, ...], summary: str
) -> WorldUnderstandingPayload:
    """Place at most twelve world facts in the five fixed semantic rings."""
    candidates = [entity for entity in entities if entity.metadata.get("world_ring") in _RINGS]
    ranked = sorted(candidates, key=lambda entity: (-entity.weight, entity.name, entity.id))[:12]
    rings: list[WorldRingPayload] = []
    for key in _RINGS:
        ring_nodes: list[WorldNodePayload] = [
            {"id": entity.id, "label": entity.name or entity.id, "kind": entity.entity_type, "weight": round(entity.weight, 6)}
            for entity in ranked
            if entity.metadata.get("world_ring") == key
        ]
        rings.append({"key": key, "nodes": ring_nodes})
    return {"summary": summary, "rings": rings}


def knowledge_beliefs(
    entities: tuple[CognitionEntity, ...], edges: tuple[CognitionEdge, ...]
) -> KnowledgeBeliefsPayload:
    """Keep only connected source-to-knowledge-to-belief paths, capped at ten."""
    candidates = {entity.id: entity for entity in entities if _knowledge_kind(entity)}
    valid_edges = [edge for edge in edges if edge.relation_type in _KNOWLEDGE_RELATIONS and edge.source in candidates and edge.target in candidates]
    connected = {edge.source for edge in valid_edges} | {edge.target for edge in valid_edges}
    selected = sorted((candidates[node_id] for node_id in connected), key=lambda entity: (-entity.weight, entity.name, entity.id))[:10]
    selected_ids = {entity.id for entity in selected}
    nodes: list[KnowledgeNodePayload] = [
        {"id": entity.id, "label": entity.name or entity.id, "kind": _knowledge_kind(entity) or "knowledge", "weight": round(entity.weight, 6)}
        for entity in sorted(selected, key=lambda entity: (_knowledge_order(entity), entity.name, entity.id))
    ]
    output_edges: list[KnowledgeEdgePayload] = [
        {"source": edge.source, "target": edge.target, "relation_key": edge.relation_type, "display_label": edge.summary, "weight": round(edge.weight, 6)}
        for edge in sorted(valid_edges, key=lambda edge: (edge.source, edge.target, edge.relation_type))
        if edge.source in selected_ids and edge.target in selected_ids
    ]
    return {"nodes": nodes, "edges": output_edges}


def _relationship_kind(entity: CognitionEntity) -> str | None:
    if entity.entity_type in {"person", "human"}:
        return "human"
    if entity.entity_type in {"elfie", "pet", "animal"}:
        return "elfie"
    return None


def _knowledge_kind(entity: CognitionEntity) -> str | None:
    value = entity.metadata.get("kind", entity.metadata.get("concept_type"))
    if value == "source":
        return "source"
    if value == "belief" or value == "pattern":
        return "belief"
    if value == "knowledge":
        return "knowledge"
    return None


def _knowledge_order(entity: CognitionEntity) -> int:
    return {"source": 0, "knowledge": 1, "belief": 2}.get(_knowledge_kind(entity) or "knowledge", 1)


__all__ = ["knowledge_beliefs", "relationship_world", "world_understanding"]
