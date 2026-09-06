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
    AssignNestHomeCommand,
    NestBed,
    NestBedAssignment,
    NestConfiguration,
    NestRoom,
    UpdateNestBedCountCommand,
)
from .ports import (
    NestManagementCommandPort,
    NestManagementQueryPort,
    NestPortBedNotFound,
    NestPortConflict,
    NestPortError,
    NestPortResidentNotFound,
    NestSnapshotRecord,
)


class NestManagementService:
    def __init__(
        self,
        query: NestManagementQueryPort,
        commands: NestManagementCommandPort,
    ) -> None:
        self._query = query
        self._commands = commands

    def get_rooms(self, principal: AccountPrincipal) -> tuple[NestRoom, ...]:
        # The monitor is a read-only projection available to every signed-in user.
        if principal.role not in {"owner", "admin", "user"}:
            raise NestManagementForbidden("Nest monitor requires a signed-in user")
        try:
            snapshot = self._query.load_snapshot()
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
            self._commands.update_bed_count(validated.bed_count)
            snapshot = self._query.load_snapshot()
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

    def assign_home(
        self,
        principal: AccountPrincipal,
        command: AssignNestHomeCommand,
    ) -> NestBedAssignment:
        self._require_manager(principal)
        if not command.elfie_id.strip():
            raise NestResidentNotFound("Elfie not found")
        if command.home_anchor_id is not None and not command.home_anchor_id.strip():
            raise NestBedNotFound("home anchor not found")
        try:
            self._commands.assign_home(command.elfie_id, command.home_anchor_id)
        except NestPortResidentNotFound as error:
            raise NestResidentNotFound("Elfie not found") from error
        except NestPortBedNotFound as error:
            raise NestBedNotFound("bed not found") from error
        except NestPortConflict as error:
            raise NestBedConflict("bed already occupied") from error
        except NestPortError as error:
            raise NestManagementUnavailable("Nest management unavailable") from error
        return NestBedAssignment(
            elfie_id=command.elfie_id,
            home_anchor_id=command.home_anchor_id,
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
                    anchor_id=bed.anchor_id,
                    label=bed.label,
                    order=bed.order,
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
