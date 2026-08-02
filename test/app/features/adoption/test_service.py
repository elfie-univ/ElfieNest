from __future__ import annotations

import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from app.features.adoption.service import (
    AdoptionCapacityError,
    AdoptionRequest,
    AdoptionValidationError,
    adopt_elfie_for_user,
)
from app.infrastructure.persistence.store import get_db, init_db


def _request(name: str) -> AdoptionRequest:
    return AdoptionRequest(
        name=name,
        species_id="fox",
        personality_style="好奇探索",
        height="standard",
        build="standard",
    )


def test_concurrent_adoptions_cannot_exceed_user_quota(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        user_id = int(
            connection.execute(
                """INSERT INTO users
                   (account_id, password_hash, role, elfie_limit)
                   VALUES ('alice', 'unused', 'user', 1)"""
            ).lastrowid
        )
        connection.commit()

    generation_started = threading.Event()
    allow_generation = threading.Event()

    def generate(**_kwargs: object) -> None:
        generation_started.set()
        assert allow_generation.wait(timeout=5)

    with patch(
        "app.features.adoption.service.ElfieGenerator.generate_for_species",
        side_effect=generate,
    ):
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(
                adopt_elfie_for_user,
                db_path,
                user_id=user_id,
                request=_request("小一"),
            )
            assert generation_started.wait(timeout=5)
            second = executor.submit(
                adopt_elfie_for_user,
                db_path,
                user_id=user_id,
                request=_request("小二"),
            )
            with pytest.raises(AdoptionCapacityError):
                second.result(timeout=5)
            allow_generation.set()
            first.result(timeout=5)

    with get_db(db_path) as connection:
        persisted_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM elfies WHERE owner_user_id = ?",
                (user_id,),
            ).fetchone()[0]
        )
    assert persisted_count == 1


def test_failed_generation_releases_reserved_slot(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        user_id = int(
            connection.execute(
                """INSERT INTO users
                   (account_id, password_hash, role, elfie_limit)
                   VALUES ('alice', 'unused', 'user', 1)"""
            ).lastrowid
        )
        connection.commit()

    with patch(
        "app.features.adoption.service.ElfieGenerator.generate_for_species",
        side_effect=ValueError("生成失败"),
    ):
        with pytest.raises(AdoptionValidationError, match="生成失败"):
            adopt_elfie_for_user(
                db_path,
                user_id=user_id,
                request=_request("小一"),
            )

    with get_db(db_path) as connection:
        persisted_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM elfies WHERE owner_user_id = ?",
                (user_id,),
            ).fetchone()[0]
        )
    assert persisted_count == 0


def test_adoption_creates_owner_only_elfie_workspace(tmp_path: Path) -> None:
    # Given: an initialized final Nest database with one owner.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        user_id = int(
            connection.execute(
                """INSERT INTO users
                   (account_id, password_hash, role, elfie_limit)
                   VALUES ('owner', 'unused', 'owner', 1)"""
            ).lastrowid
        )
        connection.commit()

    # When: the owner adopts an Elfie through the product service.
    result = adopt_elfie_for_user(
        db_path,
        user_id=user_id,
        request=_request("小栗"),
    )

    # Then: the stable Elfie workspace is accessible only to the current owner.
    workspace = Path(result.config_dir)
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
