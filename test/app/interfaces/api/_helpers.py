"""测试辅助函数 — 直接在数据库中创建测试用户/Owner。

使用方式::

    from _helpers import create_test_owner, create_test_user

    owner_id = create_test_owner(db_path)
    user_id = create_test_user(db_path, "alice", "pass")
"""

from __future__ import annotations

import secrets
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.orchestration.resident_admission import (
    AdmissionReservation,
    idempotency_key_digest,
)
from elfie import ElfieFactory
from elfie.genesis import GenesisCompileInput, GenesisCompiler, stage_for_age
from infrastructure.godot import GodotTransport, NativeBody
from infrastructure.persistence.adoption import SQLiteAdoptionAdapter
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.configuration.world import load_genesis_source_package
from infrastructure.persistence.elfie_workspace.adoption_profiles import (
    FinalElfieWorkspaceAdapter,
)
from infrastructure.persistence.layout.data_home import data_home_from_db_path
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.nest_db.nest_state import SQLiteNestStateAdapter
from infrastructure.persistence.nest_db.store import get_db, hash_password
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter
from infrastructure.persistence.setup import SQLiteSetupAdapter
from infrastructure.platform import ElfieFactoryAdapter
from nest.public import NestSnapshot


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
    elfie_id: str | None = None,
    name: str = "小白",
    species_id: str = "fox",
    personality_style: str = "好奇探索",
    height: str = "standard",
    build: str = "standard",
    engine: Any = None,
) -> str:
    """通过正式 Adoption 服务创建测试精灵，不依赖已退役 HTTP 入口。"""
    elfie_id = elfie_id or f"{secrets.randbelow(100_000_000):08d}"
    catalog = load_and_configure_species_catalog()
    source = load_genesis_source_package()
    age_years = 2
    compilation = GenesisCompiler(source, catalog=catalog).compile(
        GenesisCompileInput(
            elfie_id=elfie_id,
            owner_reference=str(user_id),
            display_name=name,
            species_id=species_id,
            gender="female",
            life_stage=stage_for_age(species_id, age_years, catalog),
            age_years_at_adoption=age_years,
            appearance_seed=secrets.randbits(63),
            height=height,
            build=build,
            face="any",
            signature="any",
            personality_style=personality_style,
            adoption_anchor_at="2001-01-01T00:00:00+00:00",
            reservation_id=f"test:{elfie_id}",
            idempotency_key=f"test-submit:{elfie_id}",
            arrival_base_id="elfie_nest",
        )
    )
    idempotency_key = f"test-submit:{elfie_id}"
    admission_store = SQLiteAdoptionAdapter(db_path)
    admission_id = f"test:{elfie_id}"
    record = admission_store.reserve(
        AdmissionReservation(
            admission_id=admission_id,
            idempotency_key_digest=idempotency_key_digest(idempotency_key),
            elfie_id=elfie_id,
            owner_user_id=user_id,
            candidate_set_id=f"test-set:{elfie_id}",
            candidate_id=f"test-candidate:{elfie_id}",
            display_name=name,
            species_id=species_id,
            gender="female",
            age_years=age_years,
            adoption_anchor_at="2001-01-01T00:00:00+00:00",
        ),
        default_limit=1000,
    )
    record = admission_store.transition(record.admission_id, "reserved", "compiling")
    workspace_adapter = FinalElfieWorkspaceAdapter(data_home_from_db_path(db_path))
    try:
        workspace_adapter.stage(compilation)
        publication = workspace_adapter.publication(elfie_id)
        record = admission_store.transition(
            record.admission_id,
            "compiling",
            "staged",
            manifest_id=publication.manifest_id,
            content_hash=publication.content_hash,
            output_ids_hash=publication.output_ids_hash,
            compiler_version=publication.compiler_version,
            schema_version=publication.schema_version,
        )
        workspace_adapter.reopen(
            elfie_id,
            manifest_id=record.manifest_id,
            content_hash=record.content_hash,
            output_ids_hash=record.output_ids_hash,
        )
        record = admission_store.transition(record.admission_id, "staged", "publishing")
        workspace_adapter.publish(elfie_id)
        admission_store.commit(
            record.admission_id,
            replace(publication, adopted_at=record.created_at),
        )
        workspace_adapter.finalize(elfie_id)
    except Exception:
        workspace_adapter.abort(elfie_id)
        admission_store.abort(record.admission_id, error_code="test_failure")
        raise
    if engine is not None:
        elfie = ElfieFactoryAdapter(
            ElfieFactory(),
            lambda elfie_id, _workspace: (
                None
                if getattr(engine, "world_runtime", None) is None
                else NativeBody(
                    body_id=elfie_id,
                    transport=GodotTransport(
                        engine.world_runtime,
                        actor_id=elfie_id,
                    ),
                )
            ),
            lambda path: YamlProfileStoreAdapter(Path(path) / "profile"),
            lambda path: SQLiteMemoryStoreAdapter(
                Path(path) / "memory" / "knowledge.sqlite"
            ),
        ).restore(elfie_id, workspace_adapter.final_workspace(elfie_id))
        engine.session.register_elfie(elfie_id, elfie)
    return elfie_id


def complete_test_setup(db_path: str, *, bed_count: int = 8) -> None:
    """Complete Setup through the canonical installation phases."""
    repository = SQLiteSetupAdapter(db_path)
    repository.save_remote_draft(configured=False, connection_id=None)
    repository.save_nest_draft(bed_count=bed_count)
    repository.begin_or_resume()
    for phase in range(2, 6):
        repository.complete_phase(phase=phase)
    SQLiteNestStateAdapter(db_path).save_snapshot(
        NestSnapshot(
            desired_bed_count=bed_count,
            elapsed_seconds=0.0,
            catalog=None,
            residents=(),
        )
    )
