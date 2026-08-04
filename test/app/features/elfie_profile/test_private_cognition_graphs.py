from __future__ import annotations

from app.features.elfie_profile.private_cognition_graphs import relationship_world
from app.infrastructure.persistence.elfie_cognition_reader import (
    CognitionEdge,
    CognitionEntity,
)


def _entity(
    entity_id: str,
    name: str,
    *,
    weight: float,
    closeness: float = 0.5,
    entity_type: str = "person",
    is_self: bool = False,
    relationship_label: str = "",
    relation_key: str = "",
) -> CognitionEntity:
    return CognitionEntity(
        id=entity_id,
        entity_type=entity_type,
        name=name,
        summary="",
        metadata={},
        relationship_label=relationship_label,
        relation_key=relation_key,
        weight=weight,
        closeness=closeness,
        is_self=is_self,
    )


def test_relationship_world_returns_self_and_up_to_forty_nine_ranked_nodes() -> None:
    entities = tuple(
        [_entity("self-row", "Happy", weight=1.0, is_self=True)]
        + [
            _entity(f"person-{index:02d}", f"Person {index:02d}", weight=1 - index / 100)
            for index in range(54)
        ]
    )

    result = relationship_world(entities, (), "12345678", "Happy")

    assert len(result["nodes"]) == 50
    assert result["nodes"][0] == {
        "id": "self",
        "label": "Happy",
        "kind": "self",
        "weight": 1.0,
    }
    assert result["nodes"][-1]["id"] == "person-48"


def test_relationship_world_uses_relation_closeness_for_direct_edges() -> None:
    entities = (
        _entity("self-row", "Happy", weight=1.0, is_self=True),
        _entity(
            "owner-row",
            "主人",
            weight=0.98,
            closeness=0.22,
            relationship_label="主人",
            relation_key="owner",
        ),
    )

    result = relationship_world(entities, (), "12345678", "Happy")

    assert result["edges"] == [
        {
            "source": "self",
            "target": "owner-row",
            "relation_key": "owner",
            "display_label": "主人",
            "weight": 0.22,
        }
    ]


def test_relationship_world_stably_prioritizes_self_edges_and_caps_edges() -> None:
    entities = (
        _entity("self-row", "Happy", weight=1.0, is_self=True),
        _entity("person-01", "Person 01", weight=0.9),
        _entity("person-02", "Person 02", weight=0.8),
        _entity("person-03", "Person 03", weight=0.7),
    )
    edges = tuple(
        CognitionEdge(
            id=f"edge-{index:03d}",
            source="self-row" if index < 3 else "person-01",
            target=f"person-{index + 1:02d}" if index < 3 else "person-02",
            relation_type=f"relation-{index:03d}",
            summary=f"Relation {index:03d}",
            weight=0.95 - index / 200,
        )
        for index in range(130)
    )

    first = relationship_world(entities, edges, "12345678", "Happy")
    second = relationship_world(entities, edges, "12345678", "Happy")

    assert first == second
    assert len(first["edges"]) == 120
    assert all(edge["source"] == "self" for edge in first["edges"][:3])
