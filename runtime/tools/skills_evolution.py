import logging
import os
from typing import Any, Dict

from runtime.tools.code import CodeSandboxPlugin
from runtime.tools.file import FileSandbox

logger = logging.getLogger("runtime.plugins.skills_evolution")


class SkillsSelfEvolutionPlugin:
    """模型技能自进化与沉淀复用插件 (Tool Synthesis)"""

    def __init__(self, permission_manager):
        self.permission_manager = permission_manager
        self.file_sandbox = FileSandbox()
        self.sandbox_plugin = CodeSandboxPlugin(timeout_seconds=5.0)

    def write_skill(self, filename: str, code: str, admin_token: str = None) -> str:
        """
        拦截 [WRITE_SKILL] 语法并写入新技能
        进行严格的分级安全审计
        """
        # 1. 净化文件名，保证是标准的 .py 后缀
        if not filename.endswith(".py"):
            filename = f"{filename}.py"

        # 2. 判断是否是“覆盖已有的成熟技能”还是“新建”
        safe_path = self.file_sandbox._safe_path(filename)
        is_overwrite = os.path.exists(safe_path)

        if is_overwrite:
            # 覆盖修改视同高危的代谢修改操作，需特权 token
            self.permission_manager.verify_action(
                "DELETE_SKILL", file_path=filename, token=admin_token
            )
        else:
            # 新增技能直接放行
            self.permission_manager.verify_action("CREATE_SKILL", file_path=filename)

        # 3. 写入文件
        saved_name = self.file_sandbox.write_file(filename, code)

        feedback = (
            f"🎉 技能沉淀成功！新技能脚本已安全写入为 '{saved_name}'。\n"
            f"此后，无论在何种复杂问题下，您都可以直接通过发出：\n"
            f"`[RUN_SKILL]{saved_name}|具体参数[/RUN_SKILL]` 标签在沙箱里完美复用该技能，无需再次生成此段代码。"
        )
        return feedback

    def run_skill(self, filename: str, args: str = "") -> Dict[str, Any]:
        """
        拦截 [RUN_SKILL] 语法并运行已保存的技能
        """
        if not filename.endswith(".py"):
            filename = f"{filename}.py"

        # 1. 安全审计 (运行技能自动放行)
        self.permission_manager.verify_action("RUN_SKILL", file_path=filename)

        # 2. 读取技能源码
        try:
            skill_code = self.file_sandbox.read_file(filename)
        except FileNotFoundError:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"FileNotFoundError: Skills database has no evolutionary skill named '{filename}'",
                "exit_code": -404,
            }

        # 3. 参数动态变量注入，使技能脚本能安全接受并处理上游参数
        # 我们在代码头部注入 args 变量
        injected_code = (
            f"# -*- coding: utf-8 -*-\n"
            f"# Injected dynamic arguments from upstream Brain:\n"
            f"args = {repr(args)}\n\n"
            f"{skill_code}"
        )

        # 4. 驱动隔离代码沙箱运行
        logger.info(f"⚙️ 正在沙箱中驱动沉淀技能 '{filename}'，注入参数: '{args}'...")
        exec_res = self.sandbox_plugin.execute(injected_code)
        return exec_res

    def list_skills(self) -> str:
        """
        拦截 [LIST_SKILLS] 语法，列出所有已学会的技能
        """
        self.permission_manager.verify_action("READ", file_path="skills_list")
        files = self.file_sandbox.list_files()

        if not files:
            return "📁 当前精灵自定义技能库为空，您尚未沉淀任何专属技能脚本。"

        formatted = ["📁 当前已学会并沉淀的专属技能库清单如下："]
        for idx, name in enumerate(files, 1):
            formatted.append(f"  [{idx}] {name}")
        return "\n".join(formatted)

    def delete_skill_by_admin(self, filename: str, admin_token: str) -> str:
        """
        特权时段 (N3代谢) 进行技能删除
        """
        if not filename.endswith(".py"):
            filename = f"{filename}.py"

        # 强特权审计
        self.permission_manager.verify_action(
            "DELETE_SKILL", file_path=filename, token=admin_token
        )

        if self.file_sandbox.delete_file(filename):
            return f"🗑️ 特权代谢成功：已彻底清理历史冗余技能脚本 '{filename}'。"
        return f"💡 技能库中未找到需要清理的目标技能文件 '{filename}'。"
