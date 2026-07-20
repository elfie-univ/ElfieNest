"""精灵可使用技能的声明和注册表。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import RLock
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SkillDefinition:
    skill_id: str
    runtime_tool: str
    display_name: str
    description: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


class SkillRegistrationError(ValueError):
    """技能声明无效或标识发生冲突。"""


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: Dict[str, SkillDefinition] = {}
        self._lock = RLock()

    def register(
        self, skill: SkillDefinition, *, replace: bool = False
    ) -> SkillDefinition:
        if not skill.skill_id.strip():
            raise SkillRegistrationError("skill_id 不能为空")
        if not skill.runtime_tool.strip():
            raise SkillRegistrationError("runtime_tool 不能为空")
        with self._lock:
            existing = self._skills.get(skill.skill_id)
            if existing is not None and existing != skill and not replace:
                raise SkillRegistrationError(f"技能已经注册: {skill.skill_id}")
            self._skills[skill.skill_id] = skill
        return skill

    def unregister(self, skill_id: str) -> SkillDefinition:
        with self._lock:
            try:
                return self._skills.pop(skill_id)
            except KeyError as exc:
                raise KeyError(f"技能未注册: {skill_id}") from exc

    def get(self, skill_id: str) -> Optional[SkillDefinition]:
        with self._lock:
            return self._skills.get(skill_id)

    def list_skills(self) -> List[SkillDefinition]:
        with self._lock:
            return list(self._skills.values())
