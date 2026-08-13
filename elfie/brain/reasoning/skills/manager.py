"""Brain-owned Skill authorization without a Runtime proxy or executor."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from elfie.brain.reasoning.skills.builtin import BUILTIN_SKILLS
from elfie.brain.reasoning.skills.policy import SkillPolicy
from elfie.brain.reasoning.skills.registry import SkillDefinition, SkillRegistry


class SkillManager:
    """Declare and authorize semantic tool capabilities for one Elfie."""

    def __init__(
        self,
        *,
        registry: Optional[SkillRegistry] = None,
        policy: Optional[SkillPolicy] = None,
        include_builtins: bool = True,
    ) -> None:
        self.registry = registry if registry is not None else SkillRegistry()
        self.policy = policy if policy is not None else SkillPolicy()
        if include_builtins:
            for skill in BUILTIN_SKILLS:
                self.registry.register(skill)

    def register(self, skill: SkillDefinition) -> SkillDefinition:
        return self.registry.register(skill)

    def authorize(
        self, requested_tool_keys: Optional[Iterable[str]]
    ) -> Tuple[str, ...]:
        """Intersect Brain's request with this Elfie's registered policy."""
        if requested_tool_keys is None:
            return ()
        allowed = set(self.allowed_tool_keys())
        result: List[str] = []
        for tool_key in requested_tool_keys:
            normalized = str(tool_key)
            if normalized in allowed and normalized not in result:
                result.append(normalized)
        return tuple(result)

    def allowed_tool_keys(self) -> Tuple[str, ...]:
        """Return allowed semantic tool keys in declaration order."""
        allowed = {
            skill.tool_key
            for skill in self.registry.list_skills()
            if self.policy.allows(skill)
        }
        result: List[str] = []
        for skill in self.registry.list_skills():
            if skill.tool_key in allowed and skill.tool_key not in result:
                result.append(skill.tool_key)
        return tuple(result)

    def snapshot(self) -> Dict[str, Any]:
        allowed = set(self.allowed_tool_keys())
        return {
            "skills": [
                {
                    **skill.to_dict(),
                    "allowed": skill.tool_key in allowed,
                }
                for skill in self.registry.list_skills()
            ],
            "allowed_tool_keys": sorted(allowed),
        }
