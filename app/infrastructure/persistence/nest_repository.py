"""SQLite adapter for final semantic Nest settings and bed assignments."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Final, TypedDict

DEFAULT_NEST_ID: Final = "local"
DEFAULT_DESIRED_BED_COUNT: Final = 4
DEFAULT_TICK_INTERVAL_SECONDS: Final = 1.0
MIN_DESIRED_BED_COUNT: Final = 4
MAX_DESIRED_BED_COUNT: Final = 32
_BED_SUFFIX: Final = re.compile(r"(?:^|/)bed-(\d+)$")


class NestRepositoryConflictError(RuntimeError):
    """The requested semantic Nest mutation conflicts with current state."""


class NestRepositoryNotFoundError(RuntimeError):
    """The requested semantic Nest record does not exist."""


class BedPayload(TypedDict):
    id: int
    anchor_id: str
    kind: str
    label: str
    order: int
    active: bool
    occupant_id: str | None
    occupant_name: str | None
    occupant_owner_user_id: int | None
    occupant_species_id: str | None
    occupant_owner_account_id: str | None
    occupant_owner_display_name: str | None


class ZonePayload(TypedDict):
    zone_id: str
    label: str
    order: int
    anchors: tuple[BedPayload, ...]


class RoomPayload(TypedDict):
    id: str
    name: str
    desired_bed_count: int
    applied_world_revision: int | None
    beds: list[BedPayload]
    zones: list[ZonePayload]


@dataclass(frozen=True)
class SemanticNestView:
    """Final Nest projection; bed numbers are semantic, never coordinates."""

    nest_id: str
    desired_bed_count: int
    applied_world_revision: int | None
    beds: tuple[BedPayload, ...]

    def as_rooms_payload(self, *, user_id: int | None = None) -> list[RoomPayload]:
        """Project final bed occupancy while hiding other Owners' identities."""
        visible_beds = [self._bed_for_user(bed, user_id=user_id) for bed in self.beds]
        zone = ZonePayload(
            zone_id="beds",
            label="Beds",
            order=0,
            anchors=tuple(visible_beds),
        )
        return [
            RoomPayload(
                id=self.nest_id,
                name="Local Nest",
                desired_bed_count=self.desired_bed_count,
                applied_world_revision=self.applied_world_revision,
                beds=visible_beds,
                zones=[zone],
            )
        ]

    @staticmethod
    def _bed_for_user(bed: BedPayload, *, user_id: int | None) -> BedPayload:
        if user_id is None or bed["occupant_owner_user_id"] == user_id:
            return bed.copy()
        visible = bed.copy()
        visible["occupant_id"] = None
        visible["occupant_name"] = None
        visible["occupant_owner_user_id"] = None
        visible["occupant_species_id"] = None
        visible["occupant_owner_account_id"] = None
        visible["occupant_owner_display_name"] = None
        return visible


class SQLiteNestRepository:
    """Persist final Nest settings and Elfie semantic placement only."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def ensure_default_config(self) -> None:
        """Create the single local settings row when Setup has not done so."""
        self._connection.execute(
            """INSERT OR IGNORE INTO nest_settings(
                   nest_id, bed_count, tick_interval_sec
               ) VALUES (?, ?, ?)""",
            (
                DEFAULT_NEST_ID,
                DEFAULT_DESIRED_BED_COUNT,
                DEFAULT_TICK_INTERVAL_SECONDS,
            ),
        )

    def set_desired_bed_count(self, bed_count: int) -> dict[str, int | None]:
        """Set the final semantic capacity within the schema range."""
        if not MIN_DESIRED_BED_COUNT <= bed_count <= MAX_DESIRED_BED_COUNT:
            raise ValueError(
                f"bed_count 必须在 {MIN_DESIRED_BED_COUNT} 到 {MAX_DESIRED_BED_COUNT} 之间"
            )
        self.ensure_default_config()
        try:
            self._connection.execute(
                """UPDATE nest_settings
                   SET bed_count=?, updated_at=CURRENT_TIMESTAMP WHERE nest_id=?""",
                (bed_count, DEFAULT_NEST_ID),
            )
        except sqlite3.IntegrityError as error:
            raise NestRepositoryConflictError(
                "bed_count is below an occupied bed"
            ) from error
        return self.config_summary()

    def config_summary(self) -> dict[str, int | None]:
        """Return the route-compatible final settings summary."""
        self.ensure_default_config()
        row = self._connection.execute(
            """SELECT bed_count, applied_world_revision FROM nest_settings
               WHERE nest_id=?""",
            (DEFAULT_NEST_ID,),
        ).fetchone()
        if row is None:
            raise NestRepositoryNotFoundError(DEFAULT_NEST_ID)
        return {
            "desired_bed_count": int(row["bed_count"]),
            "applied_world_revision": (
                None
                if row["applied_world_revision"] is None
                else int(row["applied_world_revision"])
            ),
        }

    def load_view(self) -> SemanticNestView:
        """Build a semantic bed projection without persistent geometry tables."""
        self.ensure_default_config()
        config = self._connection.execute(
            """SELECT bed_count, applied_world_revision FROM nest_settings
               WHERE nest_id=?""",
            (DEFAULT_NEST_ID,),
        ).fetchone()
        if config is None:
            raise NestRepositoryNotFoundError(DEFAULT_NEST_ID)
        occupants = {
            int(row["bed_number"]): row
            for row in self._connection.execute(
                """SELECT e.elfie_id, e.name, e.owner_user_id, e.species,
                          e.bed_number, u.account_id, u.display_name
                   FROM elfies e JOIN users u ON u.id=e.owner_user_id
                   WHERE e.bed_number IS NOT NULL"""
            ).fetchall()
        }
        beds = tuple(
            _bed_payload(number, occupants.get(number))
            for number in range(1, int(config["bed_count"]) + 1)
        )
        revision = config["applied_world_revision"]
        return SemanticNestView(
            nest_id=DEFAULT_NEST_ID,
            desired_bed_count=int(config["bed_count"]),
            applied_world_revision=None if revision is None else int(revision),
            beds=beds,
        )

    def assign_bed(self, *, elfie_id: str, bed_number: int | None) -> None:
        """Assign a nullable final bed number, rejecting missing/out-of-range beds."""
        self.ensure_default_config()
        if bed_number is not None:
            bed_count = int(
                self._connection.execute(
                    "SELECT bed_count FROM nest_settings WHERE nest_id=?",
                    (DEFAULT_NEST_ID,),
                ).fetchone()[0]
            )
            if not 1 <= bed_number <= bed_count:
                raise ValueError(f"bed_number 必须在 1 到 {bed_count} 之间")
        try:
            cursor = self._connection.execute(
                """UPDATE elfies SET bed_number=?, updated_at=CURRENT_TIMESTAMP
                   WHERE elfie_id=?""",
                (bed_number, elfie_id),
            )
        except sqlite3.IntegrityError as error:
            raise NestRepositoryConflictError("bed already occupied") from error
        if cursor.rowcount != 1:
            raise NestRepositoryNotFoundError("elfie not found")

    def assign_home(self, *, elfie_id: str, anchor_id: str | None) -> None:
        """Map the current Runtime bed anchor contract to final ``bed_number``."""
        if anchor_id is None:
            self.assign_bed(elfie_id=elfie_id, bed_number=None)
            return
        matched = _BED_SUFFIX.search(anchor_id)
        if matched is None:
            raise NestRepositoryNotFoundError("bed anchor not found")
        self.assign_bed(elfie_id=elfie_id, bed_number=int(matched.group(1)))

    def assign_home_immediately(
        self,
        *,
        elfie_id: str,
        anchor_id: str | None,
    ) -> None:
        """Acquire the write lock inside persistence before assigning a home."""
        self._connection.execute("BEGIN IMMEDIATE")
        self.assign_home(elfie_id=elfie_id, anchor_id=anchor_id)


def _bed_payload(number: int, occupant: sqlite3.Row | None) -> BedPayload:
    return BedPayload(
        id=number,
        anchor_id=f"bed-{number:02d}",
        kind="bed",
        label=f"Bed {number:02d}",
        order=number - 1,
        active=True,
        occupant_id=None if occupant is None else str(occupant["elfie_id"]),
        occupant_name=None if occupant is None else str(occupant["name"]),
        occupant_owner_user_id=(
            None if occupant is None else int(occupant["owner_user_id"])
        ),
        occupant_species_id=None if occupant is None else str(occupant["species"]),
        occupant_owner_account_id=(
            None if occupant is None else str(occupant["account_id"])
        ),
        occupant_owner_display_name=(
            None
            if occupant is None or occupant["display_name"] is None
            else str(occupant["display_name"])
        ),
    )


__all__ = (
    "NestRepositoryConflictError",
    "NestRepositoryNotFoundError",
    "SQLiteNestRepository",
    "SemanticNestView",
)
