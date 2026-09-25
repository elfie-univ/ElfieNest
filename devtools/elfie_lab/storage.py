"""测试精灵和调试会话的独立本地存储。"""

import hashlib
import json
import math
import os
import random
import secrets
import shutil
import sqlite3
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional
from uuid import uuid4

from devtools.elfie_lab.schemas import ElfieSpec, derive_life_stage
from elfie.brain.selfhood import (
    derive_personality,
)
from elfie.genesis import (
    BIG_FIVE_TRAITS,
    CandidateSignature,
    GenesisAppearanceIntent,
    GenesisCandidate,
    GenesisCompileInput,
    GenesisCompiler,
    GenesisPersonality,
    stage_for_age,
)
from elfie.genesis.appearance import generate_appearance, signature, visible_key
from elfie.genesis.personality import profile as genesis_personality_profile
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
        self.genesis_reviews_dir = self.root / "genesis_reviews"
        self.elfies_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.genesis_reviews_dir.mkdir(parents=True, exist_ok=True)
        self._catalog = load_and_configure_species_catalog()
        self._source_package = load_genesis_source_package()
        self._genesis = GenesisCompiler(
            self._source_package,
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
        age_years: Optional[float] = None,
        description: str = "用于本地调试的单精灵",
        *,
        appearance_description: str = "默认测试外貌",
        personality_description: str = "",
        elfie_id: Optional[str] = None,
        big_five_overrides: Optional[Dict[str, float]] = None,
        gender: Optional[str] = None,
    ) -> ElfieSpec:
        if species_id not in {"dog", "fox"}:
            raise ValueError("精灵物种只能是 dog 或 fox")
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("精灵名称不能为空")
        if age_years is None:
            generation = self._catalog.definition(
                species_id, adoptable_only=True
            ).genesis
            if generation is None:
                raise ValueError("物种缺少 Genesis 年龄配置")
            maximum = max(upper for _, upper in generation.stage_ranges.values())
            age_years = secrets.choice(tuple(range(2, maximum + 1)))
        if (
            isinstance(age_years, bool)
            or not isinstance(age_years, (int, float))
            or not math.isfinite(float(age_years))
            or not float(age_years).is_integer()
            or age_years < 2
            or age_years > 100
        ):
            raise ValueError("精灵年龄必须是 2 到 100 岁之间的整数")
        if gender is None:
            gender = secrets.choice(("male", "female"))
        if gender not in {"male", "female"}:
            raise ValueError("精灵性别必须是 male 或 female")
        if big_five_overrides is not None and (
            set(big_five_overrides) != set(BIG_FIVE_TRAITS)
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 1
                for value in big_five_overrides.values()
            )
        ):
            raise ValueError("大五人格必须提供五个 0 到 1 之间的数值")
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
        selected_big_five = (
            big_five_overrides
            if big_five_overrides is not None
            else {
                trait: round(secrets.SystemRandom().uniform(0.2, 0.8), 4)
                for trait in BIG_FIVE_TRAITS
            }
        )
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
        self._save_character_profile(spec, selected_big_five, gender=gender)
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

    def genesis_review_path(self, elfie_id: str) -> Path:
        self._validate_id(elfie_id)
        return self.genesis_reviews_dir / f"{elfie_id}.json"

    def get_genesis_review(self, elfie_id: str) -> Dict[str, Any]:
        if not self.profile_path(elfie_id).is_file():
            raise KeyError(f"测试精灵不存在: {elfie_id}")
        path = self.genesis_review_path(elfie_id)
        if not path.is_file():
            raise FileNotFoundError(f"该精灵没有同次 Genesis 审查记录: {elfie_id}")
        return self._read_json(path)

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
        *,
        gender: Optional[str] = None,
    ) -> None:
        if spec.age_years is None or not float(spec.age_years).is_integer():
            raise ValueError("测试精灵年龄必须是整数年")
        age_years = int(spec.age_years)
        life_stage = stage_for_age(spec.species_id, age_years, self._catalog)
        appearance_seed = int.from_bytes(
            hashlib.sha256(f"{spec.elfie_id}:appearance".encode()).digest()[:8],
            "big",
        )
        selected_gender = gender or secrets.choice(("male", "female"))
        selected_big_five = (
            big_five_overrides
            if big_five_overrides is not None
            else {
                trait: round(secrets.SystemRandom().uniform(0.2, 0.8), 4)
                for trait in BIG_FIVE_TRAITS
            }
        )
        latent = tuple(4 * selected_big_five[trait] - 2 for trait in BIG_FIVE_TRAITS)
        personality = genesis_personality_profile(latent)
        appearance = generate_appearance(
            seed=appearance_seed,
            species_id=spec.species_id,
            intent=GenesisAppearanceIntent(
                "standard", "standard", "balanced", "any", "face"
            ),
            role="primary_match",
            rng=random.Random(appearance_seed),
            life_stage=life_stage,
            age_years=age_years,
            gender=selected_gender,
            variant_index=0,
            catalog=self._catalog,
        )
        candidate = GenesisCandidate(
            candidate_id=f"lab:{spec.elfie_id}",
            role="primary_match",
            seed=appearance_seed,
            species_id=spec.species_id,
            life_stage=life_stage,
            age_years=age_years,
            gender=selected_gender,
            appearance=appearance,
            personality=GenesisPersonality(personality, personality),
            signature=CandidateSignature(
                personality=tuple(value / 2 for value in latent),
                appearance=signature(appearance),
                visual_key=visible_key(appearance),
            ),
        )
        compilation = self._genesis.compile(
            GenesisCompileInput(
                elfie_id=spec.elfie_id,
                owner_reference="developer-tool",
                display_name=spec.name,
                species_id=spec.species_id,
                gender=selected_gender,
                life_stage=life_stage,
                age_years_at_adoption=age_years,
                appearance_seed=appearance_seed,
                candidate=candidate,
                height="standard",
                build="standard",
                face="balanced",
                signature="any",
                personality_description=spec.personality_description,
                big_five_overrides=selected_big_five,
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
        self._write_json(
            self.genesis_review_path(spec.elfie_id),
            self._genesis_review_payload(compilation),
        )

    def _genesis_review_payload(self, compilation: Any) -> Dict[str, Any]:
        """Keep the same-run creation decisions in Lab-only review storage."""
        plan = compilation.plan
        bundle = plan.bundle
        traces = {item.knowledge_id: item for item in plan.decision_trace}
        selected = {item.knowledge_id: item for item in plan.knowledge_entries}
        knowledge: list[dict[str, object]] = []
        for fact in self._source_package.knowledge:
            entry = selected.get(fact.fact_id)
            trace = traces.get(fact.fact_id)
            decision = trace.decision if trace is not None else "not_selected"
            reason = (
                trace.reason if trace is not None else "编译器未提供该单元的选择理由"
            )
            if (
                entry is not None
                and trace is not None
                and trace.decision
                in {
                    "not_eligible",
                    "not_yet_eligible",
                    "not_mastered",
                }
            ):
                decision = "selected_by_prerequisite_closure"
                reason = "由已选知识的前置知识闭包补入，最终纳入个人知识"
            knowledge.append(
                {
                    "knowledge_id": fact.fact_id,
                    "source_text": fact.statement,
                    "topic": fact.topic,
                    "scope": fact.scope,
                    "level": fact.level,
                    "certainty": fact.certainty,
                    "status": fact.status,
                    "mastery_difficulty": fact.mastery_difficulty,
                    "eligibility": list(fact.eligibility),
                    "acquisition_channels": list(fact.acquisition_channels),
                    "conditions": [
                        {
                            "kind": condition.kind,
                            "attributes": dict(condition.attributes),
                        }
                        for condition in fact.conditions
                    ],
                    "prerequisite_ids": list(fact.prerequisite_ids),
                    "selected": entry is not None,
                    "decision": decision,
                    "reason": reason,
                    "access": trace.access if trace is not None else "unknown",
                    "exposure": trace.exposure if trace is not None else "unknown",
                    "selected_text": entry.source_statement
                    if entry is not None
                    else None,
                    "mastery_level": entry.mastery_level if entry is not None else None,
                    "acquired_age_years": (
                        entry.acquired_age_years if entry is not None else None
                    ),
                    "acquired_via": entry.acquired_via if entry is not None else None,
                }
            )
        mobility = plan.life_context.mobility
        return {
            "schema_version": 1,
            "source": {
                "package_id": self._source_package.manifest.package_id,
                "package_version": self._source_package.manifest.package_version,
                "content_sha256": self._source_package.manifest.content_sha256,
                "policy_version": self._source_package.generation_policy.policy_version,
                "compiler_version": self._genesis.compiler_version,
            },
            "summary": {
                "knowledge_unit_count": len(knowledge),
                "selected_knowledge_count": len(selected),
                "not_selected_knowledge_count": len(knowledge) - len(selected),
                "conditional_knowledge_count": sum(
                    bool(item["conditions"]) for item in knowledge
                ),
                "episode_count": len(bundle.episode_seeds),
                "relationship_count": len(bundle.relationship_seeds),
                "place_count": len(bundle.place_seeds),
                "place_relation_count": len(bundle.place_relation_seeds),
                "travel_path_count": len(mobility.travel_paths),
            },
            "knowledge": knowledge,
            "life": {
                "identity": {
                    "species_id": plan.life_context.identity.species_id,
                    "gender": plan.life_context.identity.gender,
                    "life_stage": plan.life_context.identity.life_stage,
                    "age_years_at_adoption": plan.life_context.identity.age_years_at_adoption,
                    "adoption_anchor_at": plan.life_context.identity.adoption_anchor_at,
                },
                "origin": _jsonable(plan.life_context.origin),
                "household": _jsonable(plan.life_context.household),
                "learning": _jsonable(plan.life_context.learning),
                "vocation": _jsonable(plan.life_context.vocation),
                "mobility": _jsonable(mobility),
                "travel_paths": _jsonable(mobility.travel_paths),
                "earth_transition": _jsonable(plan.life_context.earth_transition),
            },
            "episodes": _jsonable(bundle.episode_seeds),
            "relationships": _jsonable(bundle.relationship_seeds),
            "places": _jsonable(bundle.place_seeds),
            "place_relations": _jsonable(bundle.place_relation_seeds),
            "outputs": {
                "profile": {
                    "age_years": plan.profile.identity.origin.age_years,
                    "gender": plan.profile.identity.gender,
                    "origin_place_id": plan.profile.identity.origin.origin_place_id,
                    "origin_place_label": plan.profile.identity.origin.origin_place_label,
                },
                "selfhood": _jsonable(bundle.selfhood_state),
                "knowledge": _jsonable(bundle.knowledge_seeds),
                "output_ids": list(bundle.manifest.output_ids),
                "content_hash": bundle.manifest.content_hash,
            },
        }

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


def _jsonable(value: Any) -> Any:
    """Convert typed creation evidence into JSON without stringifying objects."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value") and isinstance(value.value, (str, int, float)):
        return value.value
    raise TypeError(f"无法安全序列化 Genesis 审查值: {type(value).__name__}")
