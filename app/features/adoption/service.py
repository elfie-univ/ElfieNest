from __future__ import annotations

import logging
import secrets
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.features.adoption.config import (
    get_allowed_personality_styles,
    get_allowed_species_ids,
    get_max_elfies_per_user,
)
from app.features.adoption.generator import ElfieGenerator
from app.infrastructure.persistence.store import count_elfies_by_owner, get_db
from nest import NestFullError

logger = logging.getLogger("app.features.adoption.service")

VALID_HEIGHTS = ("short", "standard", "tall")
VALID_BUILDS = ("slim", "standard", "plump")


class AdoptionValidationError(Exception):
    pass


@dataclass(frozen=True)
class AdoptionCapacityError(Exception):
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


@dataclass(frozen=True)
class AdoptionResult:
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
    }


def _effective_user_limit(db_path: str, user_id: int) -> int:
    system_limit = get_max_elfies_per_user(db_path)
    with get_db(db_path) as connection:
        row = connection.execute(
            "SELECT elfie_quota_override FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None or row["elfie_quota_override"] is None:
        return system_limit
    return int(row["elfie_quota_override"])


def adoption_options_for_user(db_path: str, *, user_id: int) -> dict[str, Any]:
    max_per_user = _effective_user_limit(db_path, user_id)
    used = count_elfies_by_owner(user_id, db_path)
    remaining = max(0, max_per_user - used)
    options = adoption_options(db_path)
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

    elfie_id = f"elfie_{int(time.time())}_{secrets.token_hex(2)}"
    config_dir = str(_get_elfie_config_dir(db_path, elfie_id))
    _reserve_adoption_slot(
        db_path,
        user_id=user_id,
        request=request,
        elfie_id=elfie_id,
        config_dir=config_dir,
    )

    try:
        ElfieGenerator().generate_for_species(
            name=request.name,
            species_id=request.species_id,
            personality_style=request.personality_style,
            height=request.height,
            build=request.build,
            config_dir=config_dir,
            elfie_id=elfie_id,
            appearance_overrides=request.appearance_overrides,
        )
    except ValueError as exc:
        _release_adoption_slot(db_path, elfie_id=elfie_id, config_dir=config_dir)
        raise AdoptionValidationError(str(exc)) from None
    except Exception:
        _release_adoption_slot(db_path, elfie_id=elfie_id, config_dir=config_dir)
        raise

    if engine is not None:
        _register_with_engine(engine, elfie_id, request, config_dir, db_path)

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


def _reserve_adoption_slot(
    db_path: str,
    *,
    user_id: int,
    request: AdoptionRequest,
    elfie_id: str,
    config_dir: str,
) -> None:
    system_limit = get_max_elfies_per_user(db_path)
    with get_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        user = connection.execute(
            "SELECT elfie_quota_override FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            connection.rollback()
            raise AdoptionValidationError("用户不存在")
        quota = (
            system_limit
            if user["elfie_quota_override"] is None
            else int(user["elfie_quota_override"])
        )
        current_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM elfie_registry WHERE owner_user_id = ?",
                (user_id,),
            ).fetchone()[0]
        )
        if current_count >= quota:
            connection.rollback()
            raise AdoptionCapacityError(f"每用户最多领养 {quota} 只精灵")
        connection.execute(
            """INSERT INTO elfie_registry
               (elfie_id, name, owner_user_id, species_id,
                profile_schema_version, config_dir, personality_style, height, build)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                elfie_id,
                request.name,
                user_id,
                request.species_id,
                1,
                config_dir,
                request.personality_style,
                request.height,
                request.build,
            ),
        )
        connection.commit()


def _release_adoption_slot(db_path: str, *, elfie_id: str, config_dir: str) -> None:
    with get_db(db_path) as connection:
        connection.execute("DELETE FROM elfie_registry WHERE elfie_id = ?", (elfie_id,))
        connection.commit()
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
    except NestFullError:
        raise
    except Exception as exc:  # noqa: BLE001 - adapter boundary keeps adoption persisted.
        logger.warning("Failed to register elfie %s to engine: %s", elfie_id, exc)


def _get_elfie_config_dir(db_path: str, elfie_id: str) -> Path:
    return Path(db_path).expanduser().parent / "elfies" / elfie_id
