"""调试平台的持久化数据契约。"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def derive_life_stage(species_id: str, age_years: float) -> str:
    """按物种和实际年龄派生可解释的生命阶段。"""
    ranges = _configured_stage_ranges(species_id)
    if age_years < ranges["childhood"][1]:
        return "幼年期"
    if age_years < ranges["adolescent"][1]:
        return "青春期"
    if age_years < ranges["mature"][1]:
        return "成熟期"
    return "老年期"


@lru_cache(maxsize=3)
def _configured_stage_ranges(species_id: str) -> Dict[str, tuple[int, int]]:
    """Read the canonical species ranges instead of duplicating age cutoffs."""
    from infrastructure.persistence.configuration.species import (
        load_and_configure_species_catalog,
    )

    definition = load_and_configure_species_catalog().definition(
        species_id, adoptable_only=True
    )
    if definition.genesis is None:
        raise ValueError(f"物种 {species_id!r} 缺少 Genesis 年龄配置")
    return dict(definition.genesis.stage_ranges)


@dataclass
class ElfieSpec:
    elfie_id: str
    name: str
    species_id: str = "saevi"
    age_years: Optional[float] = None
    life_stage: str = "年龄未设置"
    description: str = "用于本地调试的单精灵"
    appearance_description: str = ""
    personality_description: str = ""
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ElfieSpec":
        species_id = str(data.get("species_id", ""))
        if species_id not in {"tovren", "saevi"}:
            # 旧或未知 Lab 记录使用赛维母版兜底，不把身体实现类型暴露为个体类别。
            species_id = "saevi"
        raw_age = data.get("age_years")
        age_years = float(raw_age) if isinstance(raw_age, (int, float)) else None
        return cls(
            elfie_id=str(data["elfie_id"]),
            name=str(data["name"]),
            species_id=species_id,
            age_years=age_years,
            life_stage=(
                derive_life_stage(species_id, age_years)
                if age_years is not None
                else "年龄未设置"
            ),
            description=str(data.get("description", "")),
            appearance_description=str(data.get("appearance_description", "")),
            personality_description=str(data.get("personality_description", "")),
            created_at=str(data.get("created_at", utc_now())),
            updated_at=str(data.get("updated_at", utc_now())),
        )


@dataclass
class StimulusBundle:
    source_domain: Literal["communication", "embodied"] = "communication"
    message: str = ""
    vision_media: Optional[Dict[str, Any]] = None
    message_attachments: List[Dict[str, Any]] = field(default_factory=list)
    temperature: float = 24.0
    is_network_online: bool = True
    salience_score: float = 20.0
    impact_force: float = 0.0
    impact_direction: str = "none"
    gentle_stroke: float = 0.0
    state_injection: Dict[str, Any] = field(default_factory=dict)

    def to_sensor_data(self, message_id: str) -> Dict[str, Any]:
        return {
            "message_id": message_id,
            "has_new_message": bool(self.message.strip()),
            "user_message": self.message.strip(),
            "temperature": self.temperature,
            "is_network_online": self.is_network_online,
            "salience_score": self.salience_score,
            "impact_force": self.impact_force,
            "impact_direction": self.impact_direction,
            "gentle_stroke": self.gentle_stroke,
        }


@dataclass
class TurnRecord:
    turn_id: str
    session_id: str
    elfie_id: str
    timestamp: str
    food_key: str
    stimulus_bundle: Dict[str, Any]
    state_before: Dict[str, Any]
    trace: Dict[str, Any]
    model_call: Dict[str, Any]
    result: Dict[str, Any]
    decision: Dict[str, Any]
    state_after: Dict[str, Any]
    state_diff: Dict[str, Any]
    duration_ms: float
    used_state_injection: bool = False
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calculate_state_diff(
    before: Dict[str, Any], after: Dict[str, Any]
) -> Dict[str, Any]:
    """计算快照的可读差异，仅返回真正变化的字段。"""
    diff: Dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        old = before.get(key)
        new = after.get(key)
        if isinstance(old, dict) and isinstance(new, dict):
            nested = calculate_state_diff(old, new)
            if nested:
                diff[key] = nested
        elif old != new:
            diff[key] = {"before": old, "after": new}
    return diff
