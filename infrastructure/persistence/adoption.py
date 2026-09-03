"""SQLite Adapters for Adoption policy and Resident Admission state.

The database row in ``resident_admissions`` is a transaction coordinator, not
an Elfie owner. It holds only the bounded information required to reserve
capacity, resume a staged publication, and make a request idempotent. The
final identity and cognitive owners still live in the Elfie workspace.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, cast

from app.features.adoption import (
    AdoptionNestCapacityRecord,
    AdoptionPortCapacityReached,
    AdoptionPortError,
    AdoptionPortNestCapacityReached,
    AdoptionPortOwnerNotFound,
    AdoptionQuotaRecord,
)
from app.orchestration.resident_admission import (
    ADMISSION_TRANSITIONS,
    AdmissionPublication,
    AdmissionRecord,
    AdmissionReservation,
    AdmissionState,
)
from infrastructure.persistence.nest_db.sqlite_connection import app_sqlite_connection
from nest.public import NestConfig


class SQLiteAdoptionAdapter:
    """Own Adoption quota reads and the single durable Admission state path."""

    def __init__(self, db_path: str, *, nest_config: NestConfig | None = None) -> None:
        self._db_path = db_path
        self._nest_config = nest_config or NestConfig()

    def get_quota(
        self,
        owner_user_id: int,
        default_limit: int,
    ) -> AdoptionQuotaRecord | None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                owner = connection.execute(
                    "SELECT elfie_limit FROM users WHERE id=?",
                    (owner_user_id,),
                ).fetchone()
                if owner is None:
                    return None
                used = _count_elfies(connection, owner_user_id=owner_user_id)
        except sqlite3.Error as error:
            raise AdoptionPortError("unable to read Adoption quota") from error
        effective_limit = default_limit if owner[0] is None else int(owner[0])
        return AdoptionQuotaRecord(used=used, effective_limit=effective_limit)

    def get_nest_capacity(self) -> AdoptionNestCapacityRecord:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                row = connection.execute(
                    "SELECT bed_count FROM nest_settings WHERE nest_id='local-nest'"
                ).fetchone()
                used = _count_elfies(connection)
        except sqlite3.Error as error:
            raise AdoptionPortError("unable to read Nest capacity") from error
        maximum = self._nest_config.bed_count if row is None else int(row[0])
        return AdoptionNestCapacityRecord(used=used, maximum=maximum)

    # ResidentAdmissionStorePort -----------------------------------------

    def reserve(
        self,
        reservation: AdmissionReservation,
        default_limit: int,
    ) -> AdmissionRecord:
        """Reserve quota and create one durable ``reserved`` record atomically."""

        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = _find_existing(connection, reservation)
                if existing is not None:
                    _verify_same_reservation(existing, reservation)
                    connection.commit()
                    return _record(existing)

                owner = connection.execute(
                    "SELECT elfie_limit FROM users WHERE id=?",
                    (reservation.owner_user_id,),
                ).fetchone()
                if owner is None:
                    raise AdoptionPortOwnerNotFound

                nest = connection.execute(
                    "SELECT bed_count FROM nest_settings WHERE nest_id='local-nest'"
                ).fetchone()
                nest_limit = (
                    self._nest_config.bed_count if nest is None else int(nest[0])
                )
                if _count_elfies(connection) >= nest_limit:
                    raise AdoptionPortNestCapacityReached(nest_limit)

                effective_limit = default_limit if owner[0] is None else int(owner[0])
                if (
                    _count_elfies(
                        connection,
                        owner_user_id=reservation.owner_user_id,
                    )
                    >= effective_limit
                ):
                    raise AdoptionPortCapacityReached(effective_limit)

                now = _utc_now()
                connection.execute(
                    """INSERT INTO resident_admissions(
                           admission_id, idempotency_key_digest, elfie_id,
                           owner_user_id, state, candidate_set_id, candidate_id,
                           display_name, species_id, gender, age_years,
                           adoption_anchor_at, runtime_status, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, 'reserved', ?, ?, ?, ?, ?, ?, ?,
                                 'pending', ?, ?)""",
                    (
                        reservation.admission_id,
                        reservation.idempotency_key_digest,
                        reservation.elfie_id,
                        reservation.owner_user_id,
                        reservation.candidate_set_id,
                        reservation.candidate_id,
                        reservation.display_name,
                        reservation.species_id,
                        reservation.gender,
                        reservation.age_years,
                        reservation.adoption_anchor_at,
                        now,
                        now,
                    ),
                )
                connection.commit()
                row = connection.execute(
                    "SELECT * FROM resident_admissions WHERE admission_id=?",
                    (reservation.admission_id,),
                ).fetchone()
                if row is None:  # pragma: no cover - defensive SQLite invariant
                    raise AdoptionPortError("Admission reservation disappeared")
                return _record(row)
        except (
            AdoptionPortCapacityReached,
            AdoptionPortNestCapacityReached,
            AdoptionPortOwnerNotFound,
            AdoptionPortError,
        ):
            raise
        except sqlite3.IntegrityError as error:
            raise AdoptionPortError(
                "Admission reservation conflicts with existing data"
            ) from error
        except sqlite3.Error as error:
            raise AdoptionPortError("unable to reserve Admission capacity") from error

    def get(self, admission_id: str) -> AdmissionRecord | None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                row = connection.execute(
                    "SELECT * FROM resident_admissions WHERE admission_id=?",
                    (admission_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise AdoptionPortError("unable to read Admission state") from error
        return None if row is None else _record(row)

    def list_incomplete(self) -> tuple[AdmissionRecord, ...]:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                rows = connection.execute(
                    """SELECT * FROM resident_admissions
                       WHERE state NOT IN ('committed','aborted')
                       ORDER BY created_at, admission_id"""
                ).fetchall()
        except sqlite3.Error as error:
            raise AdoptionPortError("unable to list incomplete Admissions") from error
        return tuple(_record(row) for row in rows)

    def transition(
        self,
        admission_id: str,
        expected_state: AdmissionState,
        next_state: AdmissionState,
        *,
        manifest_id: str | None = None,
        content_hash: str | None = None,
        output_ids_hash: str | None = None,
        compiler_version: str | None = None,
        schema_version: int | None = None,
    ) -> AdmissionRecord:
        if next_state not in ADMISSION_TRANSITIONS[expected_state]:
            raise AdoptionPortError(
                f"invalid Admission transition {expected_state}->{next_state}"
            )
        assignments = ["state=?", "updated_at=?"]
        values: list[Any] = [next_state, _utc_now()]
        for column, value in (
            ("manifest_id", manifest_id),
            ("content_hash", content_hash),
            ("output_ids_hash", output_ids_hash),
            ("compiler_version", compiler_version),
            ("schema_version", schema_version),
        ):
            if value is not None:
                assignments.append(f"{column}=?")
                values.append(value)
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM resident_admissions WHERE admission_id=?",
                    (admission_id,),
                ).fetchone()
                if row is None:
                    raise AdoptionPortError("Admission record not found")
                current = cast(AdmissionState, str(row["state"]))
                if current == next_state:
                    connection.commit()
                    return _record(row)
                if current != expected_state:
                    raise AdoptionPortError(
                        f"Admission state changed unexpectedly: {current}"
                    )
                connection.execute(
                    f"UPDATE resident_admissions SET {', '.join(assignments)} "
                    "WHERE admission_id=? AND state=?",
                    (*values, admission_id, expected_state),
                )
                connection.commit()
                updated = connection.execute(
                    "SELECT * FROM resident_admissions WHERE admission_id=?",
                    (admission_id,),
                ).fetchone()
                if updated is None:  # pragma: no cover
                    raise AdoptionPortError("Admission record disappeared")
                return _record(updated)
        except AdoptionPortError:
            raise
        except sqlite3.Error as error:
            raise AdoptionPortError("unable to transition Admission state") from error

    def commit(
        self,
        admission_id: str,
        publication: AdmissionPublication,
    ) -> AdmissionRecord:
        """Publish ownership and mark the Admission committed.

        The final workspace has already been atomically renamed by the caller.
        If a process stops between that rename and this method, the same call
        completes the relation without compiling or replacing files.
        """

        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM resident_admissions WHERE admission_id=?",
                    (admission_id,),
                ).fetchone()
                if row is None:
                    raise AdoptionPortError("Admission record not found")
                current = cast(AdmissionState, str(row["state"]))
                if current == "committed":
                    _verify_publication(row, publication)
                    connection.commit()
                    return _record(row)
                if current != "publishing":
                    raise AdoptionPortError(
                        f"Admission cannot commit from state {current}"
                    )
                _validate_publication(publication)
                _verify_row_publication(row, publication)
                existing_elfie = connection.execute(
                    "SELECT owner_user_id FROM elfies WHERE elfie_id=?",
                    (row["elfie_id"],),
                ).fetchone()
                if existing_elfie is None:
                    connection.execute(
                        """INSERT INTO elfies(
                               elfie_id, owner_user_id, adopted_at, status
                           ) VALUES (?, ?, ?, 'offline')""",
                        (
                            row["elfie_id"],
                            row["owner_user_id"],
                            publication.adopted_at,
                        ),
                    )
                elif int(existing_elfie["owner_user_id"]) != int(row["owner_user_id"]):
                    raise AdoptionPortError("Elfie ownership conflicts with Admission")

                committed_at = _utc_now()
                connection.execute(
                    """UPDATE resident_admissions
                       SET state='committed', manifest_id=?, content_hash=?,
                           output_ids_hash=?, compiler_version=?, schema_version=?,
                           runtime_status='offline', error_code=NULL,
                           candidate_set_id=NULL, candidate_id=NULL, display_name=NULL,
                           species_id=NULL, gender=NULL, age_years=NULL,
                           adoption_anchor_at=NULL, committed_at=?, updated_at=?
                       WHERE admission_id=? AND state='publishing'""",
                    (
                        publication.manifest_id,
                        publication.content_hash,
                        publication.output_ids_hash,
                        publication.compiler_version,
                        publication.schema_version,
                        committed_at,
                        committed_at,
                        admission_id,
                    ),
                )
                connection.commit()
                updated = connection.execute(
                    "SELECT * FROM resident_admissions WHERE admission_id=?",
                    (admission_id,),
                ).fetchone()
                if updated is None:  # pragma: no cover
                    raise AdoptionPortError("Admission record disappeared")
                return _record(updated)
        except AdoptionPortError:
            raise
        except sqlite3.IntegrityError as error:
            raise AdoptionPortError("unable to publish Elfie ownership") from error
        except sqlite3.Error as error:
            raise AdoptionPortError("unable to commit Admission") from error

    def abort(self, admission_id: str, *, error_code: str) -> AdmissionRecord:
        """Close a pre-commit record and release its reserved capacity."""

        if not error_code.strip() or len(error_code) > 64:
            raise AdoptionPortError("Admission abort error code is invalid")
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM resident_admissions WHERE admission_id=?",
                    (admission_id,),
                ).fetchone()
                if row is None:
                    raise AdoptionPortError("Admission record not found")
                current = cast(AdmissionState, str(row["state"]))
                if current == "aborted":
                    connection.commit()
                    return _record(row)
                if current == "committed":
                    raise AdoptionPortError("committed Admission cannot be aborted")
                now = _utc_now()
                connection.execute(
                    """UPDATE resident_admissions
                       SET state='aborted', error_code=?, runtime_status='offline',
                           candidate_set_id=NULL, candidate_id=NULL, display_name=NULL,
                           species_id=NULL, gender=NULL, age_years=NULL,
                           adoption_anchor_at=NULL, updated_at=?
                       WHERE admission_id=?""",
                    (error_code.strip(), now, admission_id),
                )
                connection.commit()
                updated = connection.execute(
                    "SELECT * FROM resident_admissions WHERE admission_id=?",
                    (admission_id,),
                ).fetchone()
                if updated is None:  # pragma: no cover
                    raise AdoptionPortError("Admission record disappeared")
                return _record(updated)
        except AdoptionPortError:
            raise
        except sqlite3.Error as error:
            raise AdoptionPortError("unable to abort Admission") from error

    def mark_runtime_registered(self, admission_id: str) -> AdmissionRecord:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM resident_admissions WHERE admission_id=?",
                    (admission_id,),
                ).fetchone()
                if row is None:
                    raise AdoptionPortError("Admission record not found")
                if str(row["state"]) != "committed":
                    raise AdoptionPortError(
                        "Runtime can be registered only after Admission commit"
                    )
                if row["runtime_status"] != "registered":
                    connection.execute(
                        "UPDATE resident_admissions SET runtime_status='registered', updated_at=? "
                        "WHERE admission_id=? AND state='committed'",
                        (_utc_now(), admission_id),
                    )
                connection.commit()
                updated = connection.execute(
                    "SELECT * FROM resident_admissions WHERE admission_id=?",
                    (admission_id,),
                ).fetchone()
                if updated is None:  # pragma: no cover
                    raise AdoptionPortError("Admission record disappeared")
                return _record(updated)
        except AdoptionPortError:
            raise
        except sqlite3.Error as error:
            raise AdoptionPortError("unable to record Runtime registration") from error


def _count_elfies(
    connection: sqlite3.Connection,
    *,
    owner_user_id: int | None = None,
) -> int:
    """Count visible residents plus active reservations without double-counting."""

    if owner_user_id is None:
        query = """SELECT COUNT(*) FROM (
                     SELECT elfie_id FROM elfies
                     UNION
                     SELECT elfie_id FROM resident_admissions
                     WHERE state IN ('reserved','compiling','staged','publishing')
                       AND NOT EXISTS(
                           SELECT 1 FROM elfies e WHERE e.elfie_id=resident_admissions.elfie_id
                       )
                   )"""
        return int(connection.execute(query).fetchone()[0])
    query = """SELECT COUNT(*) FROM (
                 SELECT elfie_id FROM elfies WHERE owner_user_id=?
                 UNION
                 SELECT a.elfie_id FROM resident_admissions a
                 WHERE a.owner_user_id=?
                   AND a.state IN ('reserved','compiling','staged','publishing')
                   AND NOT EXISTS(
                       SELECT 1 FROM elfies e WHERE e.elfie_id=a.elfie_id
                   )
               )"""
    return int(connection.execute(query, (owner_user_id, owner_user_id)).fetchone()[0])


def _find_existing(
    connection: sqlite3.Connection,
    reservation: AdmissionReservation,
) -> sqlite3.Row | None:
    return connection.execute(
        """SELECT * FROM resident_admissions
           WHERE admission_id=? OR idempotency_key_digest=? OR elfie_id=?
           LIMIT 1""",
        (
            reservation.admission_id,
            reservation.idempotency_key_digest,
            reservation.elfie_id,
        ),
    ).fetchone()


def _verify_same_reservation(
    row: sqlite3.Row,
    reservation: AdmissionReservation,
) -> None:
    pairs = (
        ("admission_id", reservation.admission_id),
        ("idempotency_key_digest", reservation.idempotency_key_digest),
        ("elfie_id", reservation.elfie_id),
        ("owner_user_id", reservation.owner_user_id),
        ("candidate_set_id", reservation.candidate_set_id),
        ("candidate_id", reservation.candidate_id),
        ("species_id", reservation.species_id),
        ("gender", reservation.gender),
        ("age_years", reservation.age_years),
    )
    for column, expected in pairs:
        if str(row[column]) != str(expected):
            raise AdoptionPortError("同一幂等键对应了不同的领养决定")


def _validate_publication(publication: AdmissionPublication) -> None:
    for value in (
        publication.manifest_id,
        publication.content_hash,
        publication.output_ids_hash,
        publication.compiler_version,
        publication.adopted_at,
    ):
        if not str(value).strip():
            raise AdoptionPortError("Admission publication metadata is incomplete")
    for digest in (publication.content_hash, publication.output_ids_hash):
        if len(digest) != 64 or any(
            char not in "0123456789abcdefABCDEF" for char in digest
        ):
            raise AdoptionPortError("Admission publication digest is invalid")
    if isinstance(publication.schema_version, bool) or publication.schema_version < 1:
        raise AdoptionPortError("Admission publication schema version is invalid")


def _verify_row_publication(
    row: sqlite3.Row,
    publication: AdmissionPublication,
) -> None:
    for column, expected in (
        ("manifest_id", publication.manifest_id),
        ("content_hash", publication.content_hash),
        ("output_ids_hash", publication.output_ids_hash),
        ("compiler_version", publication.compiler_version),
        ("schema_version", publication.schema_version),
    ):
        if row[column] is not None and str(row[column]) != str(expected):
            raise AdoptionPortError("Admission publication metadata changed")


def _verify_publication(row: sqlite3.Row, publication: AdmissionPublication) -> None:
    _validate_publication(publication)
    _verify_row_publication(row, publication)


def _record(row: sqlite3.Row) -> AdmissionRecord:
    state = cast(AdmissionState, str(row["state"]))
    return AdmissionRecord(
        admission_id=str(row["admission_id"]),
        idempotency_key_digest=str(row["idempotency_key_digest"]),
        elfie_id=str(row["elfie_id"]),
        owner_user_id=int(row["owner_user_id"]),
        state=state,
        display_name=_optional_text(row["display_name"]),
        species_id=_optional_text(row["species_id"]),
        gender=_optional_text(row["gender"]),
        age_years=None if row["age_years"] is None else int(row["age_years"]),
        candidate_set_id=_optional_text(row["candidate_set_id"]),
        candidate_id=_optional_text(row["candidate_id"]),
        adoption_anchor_at=_optional_text(row["adoption_anchor_at"]),
        manifest_id=_optional_text(row["manifest_id"]),
        content_hash=_optional_text(row["content_hash"]),
        output_ids_hash=_optional_text(row["output_ids_hash"]),
        compiler_version=_optional_text(row["compiler_version"]),
        schema_version=(
            None if row["schema_version"] is None else int(row["schema_version"])
        ),
        runtime_status=cast(Any, str(row["runtime_status"])),
        error_code=_optional_text(row["error_code"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        committed_at=_optional_text(row["committed_at"]),
    )


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ("SQLiteAdoptionAdapter",)
