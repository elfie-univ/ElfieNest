"""Setup-owned Nest Port Adapter over the Nest Management fact source."""

from app.features.nest_management import NestPortError
from app.orchestration.setup_installation import SetupInstallationPortError

from .nest_management import SQLiteNestManagementAdapter


class SetupNestAdapter:
    def __init__(self, nest: SQLiteNestManagementAdapter) -> None:
        self._nest = nest

    def set_bed_count(self, bed_count: int) -> None:
        try:
            self._nest.initialize_bed_count(bed_count)
        except NestPortError as error:
            raise SetupInstallationPortError(
                "unable to apply Nest bed count"
            ) from error


__all__ = ("SetupNestAdapter",)
