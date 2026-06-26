from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

from elfienest.manage.adoption import ElfieGenerator
from elfienest.manage.adoption_config import (
    get_allowed_anatomy_types,
    get_allowed_personality_styles,
    get_max_elfies_per_user,
)
from elfienest.manage.store import count_elfies_by_owner, get_db
from elfienest.room import RoomFullError
from runtime.storage.data_home import get_elfie_config_dir

logger = logging.getLogger("elfienest.adoption.service")

VALID_HEIGHTS = ("short", "standard", "tall")
VALID_BUILDS = ("slim", "standard", "plump")


class AdoptionValidationError(Exception):
    pass


@dataclass(frozen=True)
class AdoptionRequest:
    name: str
    anatomy_type: str
    personality_style: str
    height: str
    build: str


@dataclass(frozen=True)
class AdoptionResult:
    elfie_id: str
    name: str
    config_dir: str


def adoption_options(db_path: str) -> dict[str, list[str]]:
    return {
        "personality_styles": list(get_allowed_personality_styles(db_path)),
        "anatomy_types": list(get_allowed_anatomy_types(db_path)),
        "heights": list(VALID_HEIGHTS),
        "builds": list(VALID_BUILDS),
    }


def adopt_elfie_for_user(
    db_path: str,
    *,
    user_id: int,
    request: AdoptionRequest,
    engine: Any = None,
) -> AdoptionResult:
    _validate_adoption_request(db_path, user_id=user_id, request=request)

    elfie_id = f"elfie_{int(time.time())}_{secrets.token_hex(2)}"
    config_dir = str(get_elfie_config_dir(elfie_id))

    try:
        ElfieGenerator().generate(
            name=request.name,
            anatomy_type=request.anatomy_type,
            personality_style=request.personality_style,
            height=request.height,
            build=request.build,
            config_dir=config_dir,
            elfie_id=elfie_id,
        )
    except ValueError as exc:
        raise AdoptionValidationError(str(exc)) from None

    with get_db(db_path) as conn:
        conn.execute(
            """INSERT INTO elfie_registry
               (elfie_id, name, owner_user_id, anatomy_type, config_dir,
                personality_style, height, build)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                elfie_id,
                request.name,
                user_id,
                request.anatomy_type,
                config_dir,
                request.personality_style,
                request.height,
                request.build,
            ),
        )
        conn.commit()

    if engine is not None:
        _register_with_engine(engine, elfie_id, request)

    return AdoptionResult(
        elfie_id=elfie_id,
        name=request.name,
        config_dir=config_dir,
    )


def _validate_adoption_request(
    db_path: str,
    *,
    user_id: int,
    request: AdoptionRequest,
) -> None:
    if not request.name or len(request.name) > 20:
        raise AdoptionValidationError("名字长度必须在 1-20 字之间")

    allowed_anatomy = get_allowed_anatomy_types(db_path)
    if request.anatomy_type not in allowed_anatomy:
        raise AdoptionValidationError(f"anatomy_type 必须是 {allowed_anatomy}")

    allowed_styles = get_allowed_personality_styles(db_path)
    if request.personality_style not in allowed_styles:
        raise AdoptionValidationError(f"personality_style 必须是 {list(allowed_styles)}")

    if request.height not in VALID_HEIGHTS:
        raise AdoptionValidationError(f"height 必须是 {VALID_HEIGHTS}")

    if request.build not in VALID_BUILDS:
        raise AdoptionValidationError(f"build 必须是 {VALID_BUILDS}")

    max_per_user = get_max_elfies_per_user(db_path)
    current_count = count_elfies_by_owner(user_id, db_path)
    if current_count >= max_per_user:
        raise RoomFullError(f"每用户最多领养 {max_per_user} 只精灵")


def _register_with_engine(
    engine: Any,
    elfie_id: str,
    request: AdoptionRequest,
) -> None:
    try:
        from elfie.elfie_individual import ElfieIndividual  # noqa: PLC0415

        elfie = ElfieIndividual(
            config_dir=str(get_elfie_config_dir(elfie_id)),
            anatomy_type=request.anatomy_type,
        )
        engine.coordinator.register_elfie(elfie_id, elfie)
        logger.info(
            "Elfie %s (%s) registered to room via engine",
            elfie_id,
            request.name,
        )
    except RoomFullError:
        raise
    except Exception as exc:  # noqa: BLE001 - adapter boundary keeps adoption persisted.
        logger.warning("Failed to register elfie %s to engine: %s", elfie_id, exc)
