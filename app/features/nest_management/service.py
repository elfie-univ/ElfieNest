"""Authorized product use-cases over the single semantic Nest."""

from __future__ import annotations

from app.features.accounts import AccountPrincipal, is_manager
from nest.public import NestConfig, NestConfigError

from .errors import (
    NestBedConflict,
    NestBedNotFound,
    NestConfigurationConflict,
    NestConfigurationInvalid,
    NestManagementForbidden,
    NestManagementUnavailable,
    NestResidentNotFound,
)
from .models import (
    AssignNestBedCommand,
    NestBed,
    NestBedAssignment,
    NestConfiguration,
    NestRoom,
    UpdateNestBedCountCommand,
)
from .ports import (
    NestManagementPort,
    NestPortBedNotFound,
    NestPortConflict,
    NestPortError,
    NestPortResidentNotFound,
    NestSnapshotRecord,
)


class NestManagementService:
    def __init__(self, persistence: NestManagementPort) -> None:
        self._persistence = persistence

    def get_rooms(self, principal: AccountPrincipal) -> tuple[NestRoom, ...]:
        self._require_manager(principal)
        try:
            snapshot = self._persistence.load_snapshot()
        except NestPortError as error:
            raise NestManagementUnavailable("Nest management unavailable") from error
        return (self._room(snapshot),)

    def update_bed_count(
        self,
        principal: AccountPrincipal,
        command: UpdateNestBedCountCommand,
    ) -> NestConfiguration:
        self._require_manager(principal)
        try:
            validated = NestConfig(bed_count=command.bed_count)
        except NestConfigError as error:
            raise NestConfigurationInvalid(str(error)) from error
        try:
            snapshot = self._persistence.update_bed_count(validated.bed_count)
        except NestPortConflict as error:
            raise NestConfigurationConflict(
                "bed_count is below an occupied bed"
            ) from error
        except NestPortError as error:
            raise NestManagementUnavailable("Nest management unavailable") from error
        return NestConfiguration(
            desired_bed_count=snapshot.desired_bed_count,
            applied_world_revision=snapshot.applied_world_revision,
        )

    def assign_bed(
        self,
        principal: AccountPrincipal,
        command: AssignNestBedCommand,
    ) -> NestBedAssignment:
        self._require_manager(principal)
        if not command.elfie_id.strip():
            raise NestResidentNotFound("Elfie not found")
        if command.bed_number is not None and command.bed_number < 1:
            raise NestBedNotFound("bed not found")
        try:
            self._persistence.assign_bed(command.elfie_id, command.bed_number)
        except NestPortResidentNotFound as error:
            raise NestResidentNotFound("Elfie not found") from error
        except NestPortBedNotFound as error:
            raise NestBedNotFound("bed not found") from error
        except NestPortConflict as error:
            raise NestBedConflict("bed already occupied") from error
        except NestPortError as error:
            raise NestManagementUnavailable("Nest management unavailable") from error
        anchor_id = (
            None if command.bed_number is None else f"bed-{command.bed_number:02d}"
        )
        return NestBedAssignment(
            elfie_id=command.elfie_id,
            home_anchor_id=anchor_id,
        )

    @staticmethod
    def _require_manager(principal: AccountPrincipal) -> None:
        if not is_manager(principal.role):
            raise NestManagementForbidden("Nest management requires a manager")

    @staticmethod
    def _room(snapshot: NestSnapshotRecord) -> NestRoom:
        nest_config = NestConfig(bed_count=snapshot.desired_bed_count)
        return NestRoom(
            nest_id=nest_config.nest_id,
            name="Local Nest",
            desired_bed_count=snapshot.desired_bed_count,
            applied_world_revision=snapshot.applied_world_revision,
            beds=tuple(
                NestBed(
                    bed_number=bed.bed_number,
                    anchor_id=f"bed-{bed.bed_number:02d}",
                    label=f"Bed {bed.bed_number:02d}",
                    occupant_id=bed.occupant_id,
                    occupant_name=bed.occupant_name,
                    occupant_owner_user_id=bed.occupant_owner_user_id,
                    occupant_species_id=bed.occupant_species_id,
                    occupant_owner_account_id=bed.occupant_owner_account_id,
                    occupant_owner_display_name=bed.occupant_owner_display_name,
                )
                for bed in snapshot.beds
            ),
        )


__all__ = ("NestManagementService",)
