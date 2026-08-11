"""测试辅助函数 — 直接在数据库中创建测试用户/Owner。

使用方式::

    from _helpers import create_test_owner, create_test_user

    owner_id = create_test_owner(db_path)
    user_id = create_test_user(db_path, "alice", "pass")
"""

import secrets
from datetime import date
from pathlib import Path
from typing import Any

from app.features.adoption import (
    AcceptedAdoptionReservation,
    AdoptionReservationRecord,
)
from elfie import ElfieFactory
from elfie.body.native import GodotTransport, NativeBody
from infrastructure.persistence.adoption import SQLiteAdoptionAdapter
from infrastructure.persistence.adoption_profiles import FinalElfieWorkspaceAdapter
from infrastructure.persistence.data_home import data_home_from_db_path
from infrastructure.persistence.nest_management import SQLiteNestManagementAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter
from infrastructure.persistence.setup import SQLiteSetupAdapter
from infrastructure.persistence.setup_nest import SetupNestAdapter
from infrastructure.persistence.store import get_db, hash_password
from infrastructure.platform import ElfieFactoryAdapter


def create_test_owner(
    db_path: str, account_id: str = "owner", password: str = "ownerchangeme"
) -> int:
    """直接在数据库中创建测试 Owner，绕过 setup wizard。

    Returns:
        新创建 Owner 的 user_id。
    """
    with get_db(db_path) as conn:
        pw_hash = hash_password(password)
        cursor = conn.execute(
            "INSERT INTO users (account_id, password_hash, role) VALUES (?, ?, 'owner')",
            (account_id, pw_hash),
        )
        user_id = cursor.lastrowid
        conn.commit()
    return user_id


def create_test_user(
    db_path: str, account_id: str, password: str, role: str = "user"
) -> int:
    """直接在数据库中创建测试用户。

    Returns:
        新创建用户的 user_id。
    """
    with get_db(db_path) as conn:
        pw_hash = hash_password(password)
        cursor = conn.execute(
            "INSERT INTO users (account_id, password_hash, role) VALUES (?, ?, ?)",
            (account_id, pw_hash, role),
        )
        user_id = cursor.lastrowid
        conn.commit()
    return user_id


def adopt_test_elfie(
    db_path: str,
    user_id: int,
    *,
    name: str = "小白",
    species_id: str = "fox",
    personality_style: str = "好奇探索",
    height: str = "standard",
    build: str = "standard",
    engine: Any = None,
) -> str:
    """通过正式 Adoption 服务创建测试精灵，不依赖已退役 HTTP 入口。"""
    elfie_id = f"{secrets.randbelow(100_000_000):08d}"
    reservation = AcceptedAdoptionReservation(
        elfie_id=elfie_id,
        owner_user_id=user_id,
        name=name,
        species_id=species_id,
        personality_style=personality_style,
        height=height,
        build=build,
        appearance_seed=secrets.randbits(63),
        face="any",
        signature="any",
        gender="female",
        birth_date=date.today().isoformat(),
    )
    SQLiteAdoptionAdapter(db_path).reserve(
        AdoptionReservationRecord(
            elfie_id=elfie_id,
            owner_user_id=user_id,
            name=name,
            species_id=species_id,
            gender="female",
            birth_date=reservation.birth_date,
            summary=personality_style,
        ),
        default_limit=1000,
    )
    workspace = FinalElfieWorkspaceAdapter(data_home_from_db_path(db_path)).materialize(
        reservation
    )
    if engine is not None:
        elfie = ElfieFactoryAdapter(
            ElfieFactory(),
            lambda elfie_id, _workspace: (
                None
                if getattr(engine, "world_runtime", None) is None
                else NativeBody(
                    body_id=elfie_id,
                    transport=GodotTransport(engine.world_runtime),
                )
            ),
            lambda path: YamlProfileStoreAdapter(Path(path) / "profile"),
        ).restore(elfie_id, workspace)
        engine.session.register_elfie(elfie_id, elfie)
    return elfie_id


def complete_test_setup(db_path: str, *, bed_count: int = 8) -> None:
    """Complete Setup through the canonical installation phases."""
    repository = SQLiteSetupAdapter(db_path)
    repository.save_offline_draft(use_local_ollama=False, model_id=None)
    repository.save_nest_draft(bed_count=bed_count)
    repository.begin_or_resume()
    for phase in range(2, 6):
        repository.complete_phase(phase=phase)
    SetupNestAdapter(SQLiteNestManagementAdapter(db_path)).set_bed_count(bed_count)
