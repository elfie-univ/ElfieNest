"""测试精灵和调试会话的独立本地存储。"""

import hashlib
import json
import math
import os
import secrets
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional
from uuid import uuid4

from devtools.elfie_lab.schemas import ElfieSpec, derive_life_stage
from elfie.brain.selfhood import (
    derive_personality,
)
from elfie.genesis import (
    GenesisCompileInput,
    GenesisCompiler,
    stage_for_age,
)
from infrastructure.persistence.configuration.bundled_defaults import (
    load_selfhood_defaults,
)
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.configuration.world import load_genesis_source_package
from infrastructure.persistence.elfie_workspace.adoption_profiles import (
    FinalElfieWorkspaceAdapter,
)
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.layout.data_home import get_elfie_developer_home
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


class ElfieLabStorage:
    def __init__(self, data_dir: Optional[str] = None):
        configured = data_dir or os.getenv("ELFIE_LAB_DATA_DIR")
        self.root = (
            (
                Path(configured)
                if configured
                else get_elfie_developer_home() / "elfie_lab"
            )
            .expanduser()
            .resolve()
        )
        self.elfies_dir = self.root / "elfies"
        self.sessions_dir = self.root / "sessions"
        self.elfies_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._catalog = load_and_configure_species_catalog()
        self._genesis = GenesisCompiler(
            load_genesis_source_package(),
            catalog=self._catalog,
        )

    def list_elfies(self) -> List[ElfieSpec]:
        specs: List[ElfieSpec] = []
        for path in sorted(self.elfies_dir.glob("*/profile.json")):
            try:
                specs.append(ElfieSpec.from_dict(self._read_json(path)))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(specs, key=lambda item: item.updated_at, reverse=True)

    def create_elfie(
        self,
        name: str,
        species_id: str = "fox",
        age_years: float = 2.0,
        description: str = "用于本地调试的单精灵",
        *,
        appearance_description: str = "默认测试外貌",
        personality_description: str = "",
        elfie_id: Optional[str] = None,
        big_five_overrides: Optional[Dict[str, float]] = None,
    ) -> ElfieSpec:
        if species_id not in {"dog", "fox"}:
            raise ValueError("精灵物种只能是 dog 或 fox")
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("精灵名称不能为空")
        if (
            isinstance(age_years, bool)
            or not isinstance(age_years, (int, float))
            or not math.isfinite(float(age_years))
            or not float(age_years).is_integer()
            or age_years <= 0
            or age_years > 100
        ):
            raise ValueError("精灵年龄必须是 1 到 100 岁之间的整数")
        required_text = {
            "用途描述": description,
            "外貌描述": appearance_description,
        }
        for label, value in required_text.items():
            if not value.strip():
                raise ValueError(f"{label}不能为空")
        selected_elfie_id = elfie_id or _new_final_elfie_id(self.elfies_dir)
        self._validate_id(selected_elfie_id)
        if len(selected_elfie_id) != 8 or not selected_elfie_id.isdigit():
            raise ValueError("测试精灵标识必须是 8 位数字")
        if self.profile_path(selected_elfie_id).exists():
            raise ValueError(f"测试精灵已经存在: {selected_elfie_id}")
        normalized_age = float(age_years)
        random_big_five = big_five_overrides or {
            trait: round(secrets.SystemRandom().uniform(0.2, 0.8), 4)
            for trait in (
                "openness",
                "conscientiousness",
                "extraversion",
                "agreeableness",
                "neuroticism",
            )
        }
        spec = ElfieSpec(
            elfie_id=selected_elfie_id,
            name=clean_name,
            species_id=species_id,
            age_years=normalized_age,
            life_stage=derive_life_stage(species_id, normalized_age),
            description=description.strip(),
            appearance_description=appearance_description.strip(),
            personality_description=personality_description.strip(),
        )
        self._save_character_profile(spec, random_big_five)
        self._write_json(self.profile_path(spec.elfie_id), spec.to_dict())
        return spec

    def update_big_five(
        self,
        elfie_id: str,
        values: Dict[str, float],
    ) -> Callable[[], None]:
        """持久化人工校准的人格五维，并保留派生来源。"""
        spec = self.get_elfie(elfie_id)
        repository = YamlSelfhoodSeedAdapter(self.elfie_dir(elfie_id) / "brain")
        seed = repository.load()
        derivation = derive_personality(
            elfie_id,
            spec.personality_description,
            values,
            default_big_five=self._default_big_five(),
        )
        selfhood_seed = dict(seed)
        adaptive_seed = selfhood_seed.get("adaptive_self")
        if not isinstance(adaptive_seed, Mapping):
            raise ValueError("Selfhood seed 缺少 adaptive_self 对象")
        adaptive = dict(adaptive_seed)
        adaptive["big_five"] = dict(derivation.big_five)
        selfhood_seed["adaptive_self"] = adaptive
        repository.save(selfhood_seed)

        def rollback() -> None:
            repository.save(seed)

        return rollback

    def get_elfie(self, elfie_id: str) -> ElfieSpec:
        path = self.profile_path(elfie_id)
        if not path.exists():
            raise KeyError(f"测试精灵不存在: {elfie_id}")
        spec = ElfieSpec.from_dict(self._read_json(path))
        repository = YamlProfileStoreAdapter(self.elfie_dir(elfie_id) / "profile")
        if repository.exists():
            profile = repository.load()
            if profile.identity.species_id != spec.species_id:
                spec.species_id = profile.identity.species_id
        else:
            self._save_character_profile(spec)
            self._write_json(path, spec.to_dict())
        return spec

    def elfie_dir(self, elfie_id: str) -> Path:
        self._validate_id(elfie_id)
        return self.elfies_dir / elfie_id

    def profile_path(self, elfie_id: str) -> Path:
        return self.elfie_dir(elfie_id) / "profile.json"

    def portrait_path(self, elfie_id: str) -> Path:
        return self.elfie_dir(elfie_id) / "portrait.png"

    def memory_path(self, elfie_id: str) -> Path:
        self._validate_id(elfie_id)
        path = self.elfies_dir / elfie_id / "memory" / "knowledge.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def activity_path(self, elfie_id: str) -> Path:
        """Return the durable Activity store path for one Lab Elfie."""
        self._validate_id(elfie_id)
        path = self.elfies_dir / elfie_id / "activity" / "activity.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def journal_path(self, elfie_id: str) -> Path:
        """Return the durable Brain journal path for one Lab Elfie."""
        self._validate_id(elfie_id)
        path = self.elfies_dir / elfie_id / "brain" / "journal.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def export_elfie_snapshot(self, elfie_id: str, target_root: Path) -> Path:
        """Copy one Lab Elfie's durable state into an isolated evaluation root.

        SQLite databases are copied with the online backup API so an evaluation
        never receives a torn WAL snapshot while the interactive Lab session is
        still open.
        """

        self._validate_id(elfie_id)
        source_workspace = self.elfie_dir(elfie_id)
        if not source_workspace.is_dir():
            raise KeyError(f"测试精灵不存在: {elfie_id}")
        selected_root = target_root.expanduser().resolve(strict=False)
        target_workspace = selected_root / "elfies" / elfie_id
        if target_workspace.exists():
            raise ValueError(f"评测快照已经存在: {target_workspace}")
        target_workspace.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            source_workspace,
            target_workspace,
            ignore=shutil.ignore_patterns("*.sqlite", "*.sqlite-wal", "*.sqlite-shm"),
        )
        for relative in (
            Path("memory/knowledge.sqlite"),
            Path("activity/activity.sqlite"),
            Path("brain/journal.sqlite"),
        ):
            source = source_workspace / relative
            if not source.is_file():
                continue
            destination = target_workspace / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(source)) as source_db:
                with sqlite3.connect(str(destination)) as destination_db:
                    source_db.backup(destination_db)
        return target_workspace

    def save_portrait(self, elfie_id: str, content: bytes) -> Path:
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("头像必须是 PNG 图片")
        if len(content) > 5 * 1024 * 1024:
            raise ValueError("头像文件不能超过 5 MB")
        path = self.portrait_path(elfie_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=".portrait.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return path

    def _save_character_profile(
        self,
        spec: ElfieSpec,
        big_five_overrides: Optional[Dict[str, float]] = None,
    ) -> None:
        if spec.age_years is None or not float(spec.age_years).is_integer():
            raise ValueError("测试精灵年龄必须是整数年")
        age_years = int(spec.age_years)
        life_stage = stage_for_age(spec.species_id, age_years, self._catalog)
        appearance_seed = int.from_bytes(
            hashlib.sha256(f"{spec.elfie_id}:appearance".encode()).digest()[:8],
            "big",
        )
        compilation = self._genesis.compile(
            GenesisCompileInput(
                elfie_id=spec.elfie_id,
                owner_reference="developer-tool",
                display_name=spec.name,
                species_id=spec.species_id,
                gender="female",
                life_stage=life_stage,
                age_years_at_adoption=age_years,
                appearance_seed=appearance_seed,
                height="standard",
                build="standard",
                face="balanced",
                signature="any",
                personality_description=spec.personality_description,
                big_five_overrides=big_five_overrides,
                original_name=spec.name,
                adoption_anchor_at=spec.created_at,
                reservation_id=f"lab-genesis:{spec.elfie_id}",
                idempotency_key=f"lab-genesis-submit:{spec.elfie_id}",
                arrival_base_id="elfie_nest",
            )
        )
        workspace = FinalElfieWorkspaceAdapter(data_home=self.root)
        workspace.stage(compilation)
        workspace.publish(spec.elfie_id)
        workspace.finalize(spec.elfie_id)

    @staticmethod
    def _default_big_five() -> Dict[str, object]:
        values = load_selfhood_defaults().get("big_five")
        if not isinstance(values, dict):
            raise ValueError("bundled Selfhood defaults must contain big_five")
        return dict(values)

    def session_path(self, elfie_id: str, session_id: str) -> Path:
        self._validate_id(elfie_id)
        self._validate_id(session_id)
        path = self.sessions_dir / elfie_id / f"{session_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def load_latest_session(self, elfie_id: str) -> Optional[Dict[str, Any]]:
        self._validate_id(elfie_id)
        directory = self.sessions_dir / elfie_id
        if not directory.exists():
            return None
        candidates = sorted(
            directory.glob("session_*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        return self._read_json(candidates[0]) if candidates else None

    def save_session(self, payload: Dict[str, Any]) -> None:
        self._write_json(
            self.session_path(str(payload["elfie_id"]), str(payload["session_id"])),
            payload,
        )

    @staticmethod
    def _validate_id(value: str) -> None:
        if not value or not all(ch.isalnum() or ch in {"_", "-"} for ch in value):
            raise ValueError("无效的本地数据标识")

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"数据格式错误: {path}")
        return data

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _new_final_elfie_id(elfies_dir: Path) -> str:
    """Generate an ID accepted by the shared final workspace layout."""

    while True:
        candidate = f"{uuid4().int % 100_000_000:08d}"
        if not (elfies_dir / candidate).exists():
            return candidate
