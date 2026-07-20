"""每只精灵对 Runtime 技能的使用策略。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from elfie.skills.registry import SkillDefinition


@dataclass(frozen=True)
class SkillPolicy:
    """空 allowed_skill_ids 表示允许所有已注册技能，再应用 denied_skill_ids。"""

    allowed_skill_ids: FrozenSet[str] = frozenset()
    denied_skill_ids: FrozenSet[str] = frozenset()

    def allows(self, skill: SkillDefinition) -> bool:
        if skill.skill_id in self.denied_skill_ids:
            return False
        return not self.allowed_skill_ids or skill.skill_id in self.allowed_skill_ids
