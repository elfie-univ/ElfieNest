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
    SkillDefinition(
        skill_id="code_sandbox",
        runtime_tool="code_sandbox",
        display_name="代码沙箱",
        description="通过 Runtime 权限管理器在受限沙箱中运行代码。",
    ),
    SkillDefinition(
        skill_id="skills_evolution",
        runtime_tool="skills_evolution",
        display_name="技能演化",
        description="通过 Runtime 的技能生命周期插件创建和运行自定义技能。",
    ),
)

__all__ = ["BUILTIN_SKILLS"]
