"""现有 Runtime 工具对应的内置技能声明。"""

from elfie.skills.registry import SkillDefinition

BUILTIN_SKILLS = (
    SkillDefinition(
        skill_id="web_search",
        runtime_tool="web_search",
        display_name="网络搜索",
        description="通过 Runtime 搜索插件查询公开网络信息。",
    ),
    SkillDefinition(
        skill_id="local_file",
        runtime_tool="local_file",
        display_name="本地文件",
        description="通过 Runtime 的受控目录读取和列出本地文件。",
    ),
)

__all__ = ["BUILTIN_SKILLS"]
