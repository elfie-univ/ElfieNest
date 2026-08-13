"""Bundled semantic Skill declarations."""

from elfie.brain.reasoning.skills.registry import SkillDefinition

BUILTIN_SKILLS = (
    SkillDefinition(
        skill_id="web_search",
        tool_key="web_search",
        display_name="Web search",
        description="Request bounded public-web search through the injected ToolPort.",
    ),
    SkillDefinition(
        skill_id="local_file",
        tool_key="local_file",
        display_name="Local file",
        description="Request bounded reads from the authorized workspace through ToolPort.",
    ),
)

__all__ = ["BUILTIN_SKILLS"]
