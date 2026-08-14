from __future__ import annotations

import pytest

from app.features.accounts import AccountPrincipal, AccountRole
from app.features.nest_management import (
    AssignNestHomeCommand,
    NestBedRecord,
    NestConfigurationInvalid,
    NestManagementForbidden,
    NestManagementService,
    NestSnapshotRecord,
    UpdateNestBedCountCommand,
)


class FakeNestManagementPort:
    def __init__(self) -> None:
        self.snapshot = NestSnapshotRecord(
            desired_bed_count=4,
            applied_world_revision=3,
            beds=(
                NestBedRecord(
                    anchor_id="dorm-01/bed-01",
                    label="Bed 01",
                    order=0,
                    occupant_id="00000001",
                    occupant_name="小狐",
                    occupant_owner_user_id=1,
                    occupant_species_id="fox",
                    occupant_owner_account_id="owner",
                    occupant_owner_display_name="Owner",
                ),
            ),
        )
        self.assigned: tuple[str, str | None] | None = None

    def load_snapshot(self) -> NestSnapshotRecord:
        return self.snapshot

    def update_bed_count(self, bed_count: int) -> NestSnapshotRecord:
        self.snapshot = NestSnapshotRecord(
            desired_bed_count=bed_count,
            applied_world_revision=self.snapshot.applied_world_revision,
            beds=self.snapshot.beds,
        )
        return self.snapshot

    def assign_home(self, elfie_id: str, home_anchor_id: str | None) -> None:
        self.assigned = (elfie_id, home_anchor_id)


def _principal(role: AccountRole = "owner") -> AccountPrincipal:
    return AccountPrincipal(
        user_id=1,
        account_id="owner",
        role=role,
        default_landing_page="/manage",
    )


def test_manager_reads_strict_semantic_nest_projection() -> None:
    service = NestManagementService(FakeNestManagementPort())

    rooms = service.get_rooms(_principal())

    assert len(rooms) == 1
    assert rooms[0].nest_id == "local-nest"
    assert rooms[0].beds[0].anchor_id == "dorm-01/bed-01"
    assert rooms[0].beds[0].occupant_id == "00000001"


def test_member_cannot_manage_nest() -> None:
    service = NestManagementService(FakeNestManagementPort())

    with pytest.raises(NestManagementForbidden):
        service.get_rooms(_principal("user"))


def test_bed_count_uses_public_nest_range() -> None:
    service = NestManagementService(FakeNestManagementPort())

    with pytest.raises(NestConfigurationInvalid):
        service.update_bed_count(
            _principal(),
            UpdateNestBedCountCommand(bed_count=3),
        )


def test_assign_home_returns_semantic_anchor() -> None:
    persistence = FakeNestManagementPort()
    service = NestManagementService(persistence)

    result = service.assign_home(
        _principal(),
        AssignNestHomeCommand(
            elfie_id="00000001",
            home_anchor_id="dorm-01/bed-02",
        ),
    )

    assert persistence.assigned == ("00000001", "dorm-01/bed-02")
    assert result.home_anchor_id == "dorm-01/bed-02"
