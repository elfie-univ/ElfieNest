from __future__ import annotations

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
    adoption_options_for_user,
)
from app.infrastructure.persistence.account_repository import AccountRepository
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
                   (username, password_hash, role, elfie_quota_override)
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
                "SELECT COUNT(*) FROM elfie_registry WHERE owner_user_id = ?",
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
                   (username, password_hash, role, elfie_quota_override)
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
                "SELECT COUNT(*) FROM elfie_registry WHERE owner_user_id = ?",
                (user_id,),
            ).fetchone()[0]
        )
    assert persisted_count == 0


def test_final_null_limit_follows_current_config_and_override_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: config.yaml sets the global limit and the legacy account follows it.
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "system:\n  adoption:\n    max_elfies_per_user: 5\n",
        encoding="utf-8",
    )
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        user_id = int(
            connection.execute(
                """
                INSERT INTO users
                    (username, password_hash, role, elfie_quota_override)
                VALUES ('alice', 'unused', 'user', NULL)
                """
            ).lastrowid
        )
        connection.commit()

    # When/Then: NULL is dynamic config policy, while the final override wins.
    assert adoption_options_for_user(db_path, user_id=user_id)["quota"]["max"] == 5
    with get_db(db_path) as connection:
        AccountRepository(connection).update_quota(user_id, 2)
        connection.commit()
    assert adoption_options_for_user(db_path, user_id=user_id)["quota"]["max"] == 2
