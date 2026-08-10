from __future__ import annotations

import pytest

from app.features.accounts import AccountPrincipal, AccountRole
from app.features.nest_management import (
    AssignNestBedCommand,
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
                    bed_number=1,
                    occupant_id="00000001",
                    occupant_name="小狐",
                    occupant_owner_user_id=1,
                    occupant_species_id="fox",
                    occupant_owner_account_id="owner",
                    occupant_owner_display_name="Owner",
                ),
            ),
        )
        self.assigned: tuple[str, int | None] | None = None

    def load_snapshot(self) -> NestSnapshotRecord:
        return self.snapshot

    def update_bed_count(self, bed_count: int) -> NestSnapshotRecord:
        self.snapshot = NestSnapshotRecord(
            desired_bed_count=bed_count,
            applied_world_revision=self.snapshot.applied_world_revision,
            beds=self.snapshot.beds,
        )
        return self.snapshot

    def assign_bed(self, elfie_id: str, bed_number: int | None) -> None:
        self.assigned = (elfie_id, bed_number)


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
    assert rooms[0].beds[0].anchor_id == "bed-01"
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


def test_assign_bed_returns_semantic_anchor() -> None:
    persistence = FakeNestManagementPort()
    service = NestManagementService(persistence)

    result = service.assign_bed(
        _principal(),
        AssignNestBedCommand(elfie_id="00000001", bed_number=2),
    )

    assert persistence.assigned == ("00000001", 2)
    assert result.home_anchor_id == "bed-02"
