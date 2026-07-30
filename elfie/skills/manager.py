"""精灵技能白名单管理和 Runtime 适配。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from elfie.skills.builtin import BUILTIN_SKILLS
from elfie.skills.policy import SkillPolicy
from elfie.skills.registry import SkillDefinition, SkillRegistry


class RuntimeSkillAdapter:
    """透明代理 Runtime，只过滤已有调用中的 allowed_skills 参数。"""

    _FILTERED_METHODS = frozenset({"ask", "ask_with_food", "run_with_food"})

    def __init__(self, runtime_agent: Any, manager: SkillManager) -> None:
        self.runtime_agent = runtime_agent
        self.manager = manager

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self.runtime_agent, name)
        if name not in self._FILTERED_METHODS or not callable(attribute):
            return attribute

        def invoke(*args: Any, **kwargs: Any) -> Any:
            if "allowed_skills" in kwargs:
                kwargs = dict(kwargs)
                kwargs["allowed_skills"] = list(
                    self.manager.filter_runtime_tools(kwargs["allowed_skills"])
                )
            elif name == "ask" and callable(
                getattr(self.runtime_agent, "run_with_food", None)
            ):
                kwargs = dict(kwargs)
                kwargs["allowed_skills"] = list(self.manager.allowed_runtime_tools())
            return attribute(*args, **kwargs)

        return invoke


class SkillManager:
    """声明精灵能使用什么；实际执行仍完全交给 Runtime。"""

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

    def filter_runtime_tools(
        self, requested_tools: Optional[Iterable[str]]
    ) -> Tuple[str, ...]:
        if requested_tools is None:
            return ()
        allowed_tools = set(self.allowed_runtime_tools())
        candidates = [str(tool) for tool in requested_tools]
        result: List[str] = []
        for tool in candidates:
            if tool in allowed_tools and tool not in result:
                result.append(tool)
        return tuple(result)

    def allowed_runtime_tools(self) -> Tuple[str, ...]:
        """返回当前策略允许的全部 Runtime 工具，保持注册顺序。"""
        allowed_tools = {
            skill.runtime_tool
            for skill in self.registry.list_skills()
            if self.policy.allows(skill)
        }
        result: List[str] = []
        for skill in self.registry.list_skills():
            tool = skill.runtime_tool
            if tool in allowed_tools and tool not in result:
                result.append(tool)
        return tuple(result)

    def wrap_runtime(self, runtime_agent: Any) -> RuntimeSkillAdapter:
        if (
            isinstance(runtime_agent, RuntimeSkillAdapter)
            and runtime_agent.manager is self
        ):
            return runtime_agent
        return RuntimeSkillAdapter(runtime_agent, self)

    def snapshot(self) -> Dict[str, Any]:
        allowed = set(self.allowed_runtime_tools())
        return {
            "skills": [
                {
                    **skill.to_dict(),
                    "allowed": skill.runtime_tool in allowed,
                }
                for skill in self.registry.list_skills()
            ],
            "allowed_runtime_tools": sorted(allowed),
        }
