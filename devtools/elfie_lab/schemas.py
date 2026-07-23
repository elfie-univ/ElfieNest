"""调试平台的持久化数据契约。"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def derive_life_stage(species_id: str, age_years: float) -> str:
    """按物种和实际年龄派生可解释的生命阶段。"""
    youth_limit = 3.0 if species_id == "dog" else 2.0
    senior_limit = 8.0 if species_id == "dog" else 7.0
    if age_years < 1.0:
        return "幼年"
    if age_years < youth_limit:
        return "青年"
    if age_years < senior_limit:
        return "成年"
    return "老年"


@dataclass
class ElfieSpec:
    elfie_id: str
    name: str
    species_id: str = "fox"
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
        if species_id not in {"dog", "fox"}:
            # 旧 Lab 只保存身体形态，没有物种。迁移时用狐狸母版兜底，
            # 不再把 biped/quadruped 暴露为个体类别。
            species_id = "fox"
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
    message: str = ""
    vision_media: Optional[Dict[str, Any]] = None
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
