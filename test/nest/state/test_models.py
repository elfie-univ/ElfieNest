import pytest
from pydantic import ValidationError

from nest.state.models import (
    AnchorKind,
    HomeAssignment,
    InteractionAnchor,
    PersistentResidentState,
    ResidentPresence,
    RuntimeResidentMirror,
    WorldCatalog,
    ZoneDescriptor,
)


def test_world_catalog_round_trips_when_semantic_ids_are_valid() -> None:
    # Given
    catalog = WorldCatalog(
        nest_id="local-nest",
        revision=3,
        zones=(
            ZoneDescriptor(
                zone_id="dorm-01",
                label="Dormitory 1",
                order=1,
                anchors=(
                    InteractionAnchor(
                        anchor_id="dorm-01/bed-01",
                        kind=AnchorKind.BED,
                        label="Bed 1",
                        order=1,
                    ),
                ),
            ),
        ),
    )

    # When
    restored = WorldCatalog.model_validate_json(catalog.model_dump_json())

    # Then
    assert restored == catalog
    assert "dorm-01/bed-01" in restored.anchor_ids


def test_world_catalog_rejects_duplicate_anchors_and_extra_fields() -> None:
    # Given
    duplicate_anchor_payload = {
        "nest_id": "local-nest",
        "revision": 1,
        "zones": [
            {
                "zone_id": "dorm-01",
                "label": "Dormitory 1",
                "order": 1,
                "anchors": [
                    {
                        "anchor_id": "dorm-01/bed-01",
                        "kind": "bed",
                        "label": "Bed 1",
                        "order": 1,
                    },
                    {
                        "anchor_id": "dorm-01/bed-01",
                        "kind": "chair",
                        "label": "Chair 1",
                        "order": 2,
                    },
                ],
            },
        ],
    }
    extra_field_payload = {
        "anchor_id": "dorm-01/bed-02",
        "kind": "bed",
        "label": "Bed 2",
        "order": 2,
        "position": [1.0, 2.0, 3.0],
    }

    # When / Then
    with pytest.raises(ValidationError, match="duplicate anchor_id"):
        WorldCatalog.model_validate(duplicate_anchor_payload)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InteractionAnchor.model_validate(extra_field_payload)


def test_home_assignment_rejects_non_bed_anchor_kind() -> None:
    # Given
    chair_home_payload = {
        "elfie_id": "fox-1",
        "home_zone_id": "dorm-01",
        "home_anchor_id": "dorm-01/chair-01",
        "anchor_kind": "chair",
    }

    # When / Then
    with pytest.raises(ValidationError, match="home assignment requires bed anchor"):
        HomeAssignment.model_validate(chair_home_payload)


def test_resident_semantic_state_separates_persistent_and_runtime_fields() -> None:
    # Given
    persistent = PersistentResidentState(
        elfie_id="fox-1",
        presence=ResidentPresence.ACTIVE,
        home_zone_id="dorm-01",
        home_anchor_id="dorm-01/bed-01",
    )
    runtime = RuntimeResidentMirror(
        elfie_id="fox-1",
        current_zone_id="activity-main",
        posture="standing",
        active_command_id="command-1",
    )

    # When
    persistent_json = persistent.model_dump_json()
    runtime_json = runtime.model_dump_json()

    # Then
    assert "home_anchor_id" in persistent_json
    assert "current_zone_id" not in persistent_json
    assert "active_command_id" in runtime_json
    assert "grid" not in persistent_json
    assert "Vector3" not in persistent_json
