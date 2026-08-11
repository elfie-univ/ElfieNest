"""Per-Elfie Skill authorization policy owned by Brain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from elfie.brain.skills.registry import SkillDefinition


@dataclass(frozen=True)
class SkillPolicy:
    """Allow registered Skills, then apply explicit denials."""

    allowed_skill_ids: FrozenSet[str] = frozenset()
    denied_skill_ids: FrozenSet[str] = frozenset()

    def allows(self, skill: SkillDefinition) -> bool:
        if skill.skill_id in self.denied_skill_ids:
            return False
        return not self.allowed_skill_ids or skill.skill_id in self.allowed_skill_ids
