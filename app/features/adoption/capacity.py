"""Transactional per-account adoption capacity policy."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.adoption.config import get_max_elfies_per_user
from app.infrastructure.persistence.account_repository import AccountRepository
from app.infrastructure.persistence.account_storage_cutover import (
    ensure_account_storage_cutover,
)
from app.infrastructure.persistence.store import get_db


@dataclass(frozen=True)
class AdoptionCapacityError(Exception):
    """The account has no remaining adoption slots."""

    detail: str
    __slots__ = ("detail",)

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True)
class AdoptionAccountMissingError(Exception):
    """The requested adoption account does not exist."""

    user_id: int
    __slots__ = ("user_id",)

    def __str__(self) -> str:
        return f"account {self.user_id} does not exist"


@dataclass(frozen=True)
class AdoptionReservation:
    """Values persisted while reserving one adoption slot."""

    elfie_id: str
    name: str
    species_id: str
    personality_style: str
    height: str
    build: str
    config_dir: str
    __slots__ = (
        "elfie_id",
        "name",
        "species_id",
        "personality_style",
        "height",
        "build",
        "config_dir",
    )


def effective_user_limit(db_path: str, user_id: int) -> int:
    """Resolve NULL final account limits through the current config.yaml policy."""
    ensure_account_storage_cutover(db_path)
    system_limit = get_max_elfies_per_user(db_path)
    with get_db(db_path) as connection:
        account = AccountRepository(connection).find_by_id(user_id)
    if account is None or account.elfie_limit is None:
        return system_limit
    return account.elfie_limit


def reserve_adoption_slot(
    db_path: str,
    user_id: int,
    reservation: AdoptionReservation,
) -> None:
    """Atomically enforce the final account limit and reserve one registry row."""
    ensure_account_storage_cutover(db_path)
    system_limit = get_max_elfies_per_user(db_path)
    with get_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        account = AccountRepository(connection).find_by_id(user_id)
        if account is None:
            connection.rollback()
            raise AdoptionAccountMissingError(user_id)
        quota = system_limit if account.elfie_limit is None else account.elfie_limit
        if account.elfie_count >= quota:
            connection.rollback()
            raise AdoptionCapacityError(f"每用户最多领养 {quota} 只精灵")
        connection.execute(
            """INSERT INTO elfie_registry
               (elfie_id, name, owner_user_id, species_id,
                profile_schema_version, config_dir, personality_style, height, build)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                reservation.elfie_id,
                reservation.name,
                user_id,
                reservation.species_id,
                1,
                reservation.config_dir,
                reservation.personality_style,
                reservation.height,
                reservation.build,
            ),
        )
        connection.commit()
