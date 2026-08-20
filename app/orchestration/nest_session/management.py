"""Product command adapter over the one live Nest Session."""

from __future__ import annotations

from app.features.nest_management import (
    NestPortBedNotFound,
    NestPortConflict,
    NestPortError,
    NestPortResidentNotFound,
)
from nest.public import (
    BedCapacityError,
    BedConflictError,
    NestConfigError,
    UnknownAnchorError,
    UnknownResidentError,
)

from .ports import NestStateStoreError
from .session import NestSession


class LiveNestManagementCommands:
    """Translate live Nest domain/state-store failures for the Feature boundary."""

    def __init__(self, session: NestSession) -> None:
        self._session = session

    def initialize_bed_count(self, bed_count: int) -> None:
        try:
            self._session.initialize_bed_count(bed_count)
        except BedCapacityError as error:
            raise NestPortConflict(str(error)) from error
        except NestConfigError as error:
            raise NestPortConflict(str(error)) from error
        except NestStateStoreError as error:
            raise NestPortError("unable to initialize Nest configuration") from error

    def update_bed_count(self, bed_count: int) -> None:
        try:
            self._session.update_bed_count(bed_count)
        except BedCapacityError as error:
            raise NestPortConflict(str(error)) from error
        except NestConfigError as error:
            raise NestPortConflict(str(error)) from error
        except NestStateStoreError as error:
            raise NestPortError("unable to persist Nest configuration") from error

    def assign_home(self, elfie_id: str, home_anchor_id: str | None) -> None:
        try:
            self._session.assign_home(elfie_id, home_anchor_id)
        except UnknownResidentError as error:
            raise NestPortResidentNotFound(str(error)) from error
        except UnknownAnchorError as error:
            raise NestPortBedNotFound(str(error)) from error
        except BedConflictError as error:
            raise NestPortConflict(str(error)) from error
        except NestStateStoreError as error:
            raise NestPortError("unable to persist Nest home") from error


class UnavailableNestManagementCommands:
    """Fail closed when an API container has no live Nest authority."""

    @staticmethod
    def initialize_bed_count(bed_count: int) -> None:
        _ = bed_count
        raise NestPortError("live Nest session unavailable")

    @staticmethod
    def update_bed_count(bed_count: int) -> None:
        _ = bed_count
        raise NestPortError("live Nest session unavailable")

    @staticmethod
    def assign_home(elfie_id: str, home_anchor_id: str | None) -> None:
        _ = (elfie_id, home_anchor_id)
        raise NestPortError("live Nest session unavailable")


__all__ = ("LiveNestManagementCommands", "UnavailableNestManagementCommands")
