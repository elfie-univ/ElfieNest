"""Semantic Skill declarations and the in-memory catalog owned by Brain."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import RLock
from typing import Dict, List, Optional, Tuple, Union

SkillValue = Union[str, Tuple[str, ...]]


@dataclass(frozen=True)
class SkillDefinition:
    """Immutable declaration of one Brain capability and its Tool bindings."""

    skill_id: str
    tool_keys: Tuple[str, ...]
    display_name: str
    description: str

    def to_dict(self) -> Dict[str, SkillValue]:
        return asdict(self)


class SkillRegistrationError(ValueError):
    """Raised when a Skill declaration is invalid or conflicts."""


class SkillRegistry:
    """Thread-safe in-memory catalog for bundled or explicitly assembled Skills."""

    def __init__(self) -> None:
        self._skills: Dict[str, SkillDefinition] = {}
        self._lock = RLock()

    def register(
        self, skill: SkillDefinition, *, replace: bool = False
    ) -> SkillDefinition:
        if not skill.skill_id.strip():
            raise SkillRegistrationError("skill_id must not be blank")
        if not skill.tool_keys:
            raise SkillRegistrationError("tool_keys must not be empty")
        if any(not tool_key.strip() for tool_key in skill.tool_keys):
            raise SkillRegistrationError("tool_keys must not contain blanks")
        if len(set(skill.tool_keys)) != len(skill.tool_keys):
            raise SkillRegistrationError("tool_keys must be unique")
        with self._lock:
            existing = self._skills.get(skill.skill_id)
            if existing is not None and existing != skill and not replace:
                raise SkillRegistrationError(
                    f"Skill already registered: {skill.skill_id}"
                )
            self._skills[skill.skill_id] = skill
        return skill

    def unregister(self, skill_id: str) -> SkillDefinition:
        with self._lock:
            try:
                return self._skills.pop(skill_id)
            except KeyError as exc:
                raise KeyError(f"Skill not registered: {skill_id}") from exc

    def get(self, skill_id: str) -> Optional[SkillDefinition]:
        with self._lock:
            return self._skills.get(skill_id)

    def list_skills(self) -> List[SkillDefinition]:
        with self._lock:
            return list(self._skills.values())
