from __future__ import annotations

import logging
import os
import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai_runtime.storage.data_home import data_home_from_db_path
from ai_runtime.storage.data_layout import final_root_layout
from app.features.adoption.config import (
    get_allowed_personality_styles,
    get_allowed_species_ids,
    get_max_elfies_per_user,
)
from app.features.adoption.generator import ElfieGenerator
from app.infrastructure.persistence.account_repository import AccountRepository
from app.infrastructure.persistence.elfie_repository import (
    ElfieCapacityExceeded,
    ElfieOwnerNotFound,
    ElfieRepository,
)
from app.infrastructure.persistence.store import get_db

logger = logging.getLogger("app.features.adoption.service")

VALID_HEIGHTS = ("short", "standard", "tall")
VALID_BUILDS = ("slim", "standard", "plump")


class AdoptionValidationError(Exception):
    pass


class AdoptionRuntimeRegistrationError(RuntimeError):
    """The generated Elfie could not be admitted to the live runtime."""

    def __init__(self, elfie_id: str) -> None:
        self.elfie_id = elfie_id
        super().__init__(f"精灵 {elfie_id} 未能加入运行时")


@dataclass(frozen=True)
class AdoptionCapacityError(Exception):
    __slots__ = ("detail",)

    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True)
class AdoptionRequest:
    name: str
    species_id: str
    personality_style: str
    height: str
    build: str
    appearance_overrides: dict[str, Any] = field(default_factory=dict)
    appearance_seed: int | None = None
    gender: str | None = None
    birth_date: str | None = None


@dataclass(frozen=True)
class AdoptionResult:
    __slots__ = ("elfie_id", "name", "species_id", "config_dir")

    elfie_id: str
    name: str
    species_id: str
    config_dir: str


def adoption_options(db_path: str) -> dict[str, list[str]]:
    return {
        "personality_styles": list(get_allowed_personality_styles(db_path)),
        "species_ids": list(get_allowed_species_ids(db_path)),
        "heights": list(VALID_HEIGHTS),
        "builds": list(VALID_BUILDS),
        "life_stages": ["youth", "young_adult", "mature", "elder", "any"],
    }


def _effective_user_limit(db_path: str, user_id: int) -> int:
    system_limit = get_max_elfies_per_user(db_path)
    with get_db(db_path) as connection:
        limit = AccountRepository(connection).elfie_limit(user_id, system_limit)
    return system_limit if limit is None else limit


def adoption_options_for_user(db_path: str, *, user_id: int) -> dict[str, Any]:
    max_per_user = _effective_user_limit(db_path, user_id)
    used = ElfieRepository(db_path).count_for_owner(user_id)
    remaining = max(0, max_per_user - used)
    options: dict[str, Any] = dict(adoption_options(db_path))
    options["quota"] = {
        "used": used,
        "max": max_per_user,
        "remaining": remaining,
        "can_adopt": remaining > 0,
    }
    return options


def adopt_elfie_for_user(
    db_path: str,
    *,
    user_id: int,
    request: AdoptionRequest,
    engine: Any = None,
) -> AdoptionResult:
    _validate_adoption_request(db_path, request=request)

    elfie_id = f"{secrets.randbelow(100_000_000):08d}"
    config_path = _get_elfie_config_dir(db_path, elfie_id)
    config_dir = str(config_path)
    _reserve_adoption_slot(
        db_path,
        user_id=user_id,
        request=request,
        elfie_id=elfie_id,
    )

    generated = False
    try:
        config_path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(config_path, 0o700)
        ElfieGenerator().generate_for_species(
            name=request.name,
            species_id=request.species_id,
            personality_style=request.personality_style,
            height=request.height,
            build=request.build,
            config_dir=config_dir,
            elfie_id=elfie_id,
            appearance_seed=request.appearance_seed,
            appearance_overrides=request.appearance_overrides,
        )
        ElfieRepository(db_path).update_profile(
            elfie_id,
            gender=request.gender,
            birth_date=request.birth_date,
            summary=request.personality_style,
        )
        generated = True
    except ValueError as exc:
        raise AdoptionValidationError(str(exc)) from None
    finally:
        if not generated:
            _release_adoption_slot(db_path, elfie_id=elfie_id, config_dir=config_dir)

    if engine is not None:
        try:
            _register_with_engine(engine, elfie_id, request, config_dir, db_path)
        except AdoptionRuntimeRegistrationError:
            _release_adoption_slot(db_path, elfie_id=elfie_id, config_dir=config_dir)
            raise

    return AdoptionResult(
        elfie_id=elfie_id,
        name=request.name,
        species_id=request.species_id,
        config_dir=config_dir,
    )


def _validate_adoption_request(
    db_path: str,
    *,
    request: AdoptionRequest,
) -> None:
    if not request.name or len(request.name) > 20:
        raise AdoptionValidationError("名字长度必须在 1-20 字之间")

    allowed_species = get_allowed_species_ids(db_path)
    if request.species_id not in allowed_species:
        raise AdoptionValidationError(f"species_id 必须是 {allowed_species}")

    allowed_styles = get_allowed_personality_styles(db_path)
    if request.personality_style not in allowed_styles:
        raise AdoptionValidationError(
            f"personality_style 必须是 {list(allowed_styles)}"
        )

    if request.height not in VALID_HEIGHTS:
        raise AdoptionValidationError(f"height 必须是 {VALID_HEIGHTS}")

    if request.build not in VALID_BUILDS:
        raise AdoptionValidationError(f"build 必须是 {VALID_BUILDS}")
    if request.gender is not None and request.gender not in ("male", "female"):
        raise AdoptionValidationError("gender 必须是 male 或 female")


def _reserve_adoption_slot(
    db_path: str,
    *,
    user_id: int,
    request: AdoptionRequest,
    elfie_id: str,
) -> None:
    system_limit = get_max_elfies_per_user(db_path)
    try:
        ElfieRepository(db_path).reserve_adoption(
            elfie_id=elfie_id,
            owner_user_id=user_id,
            name=request.name,
            species=request.species_id,
            summary=request.personality_style,
            max_elfies=system_limit,
        )
    except ElfieOwnerNotFound:
        raise AdoptionValidationError("用户不存在") from None
    except ElfieCapacityExceeded as error:
        raise AdoptionCapacityError(f"每用户最多领养 {error.limit} 只精灵") from None


def _release_adoption_slot(db_path: str, *, elfie_id: str, config_dir: str) -> None:
    ElfieRepository(db_path).delete(elfie_id)
    shutil.rmtree(config_dir, ignore_errors=True)


def _register_with_engine(
    engine: Any,
    elfie_id: str,
    request: AdoptionRequest,
    config_dir: str,
    db_path: str,
) -> None:
    try:
        from elfie import ElfieFactory  # noqa: PLC0415

        elfie = ElfieFactory().restore(
            config_dir,
            elfie_id=elfie_id,
            godot_api=getattr(engine, "api_server", None),
        )
        engine.session.register_elfie(elfie_id, elfie)
        logger.info(
            "Elfie %s (%s) registered to room via engine",
            elfie_id,
            request.name,
        )
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        logger.warning("Failed to register elfie %s to engine: %s", elfie_id, exc)
        raise AdoptionRuntimeRegistrationError(elfie_id) from exc


def _get_elfie_config_dir(db_path: str, elfie_id: str) -> Path:
    return final_root_layout(data_home_from_db_path(db_path)).elfie(elfie_id).workspace
