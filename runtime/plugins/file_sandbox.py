import logging
import os

logger = logging.getLogger("runtime.plugins.file_sandbox")


class FileSandbox:
    """技能文件专用安全沙箱，物理隔离防路径穿梭"""

    def __init__(self):
        # 技能库根目录设定在 runtime/custom_skills
        self.runtime_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.skills_root = os.path.join(self.runtime_dir, "custom_skills")
        self._ensure_skills_root()

    def _ensure_skills_root(self):
        if not os.path.exists(self.skills_root):
            os.makedirs(self.skills_root)
            # 自动生成一个简单的 __init__.py 方便做包导入 (如果需要)
            with open(os.path.join(self.skills_root, "__init__.py"), "w") as f:
                f.write(
                    "# -*- coding: utf-8 -*-\n# Elfie custom evolved skills package\n"
                )

    def _safe_path(self, filename: str) -> str:
        """安全路径校验，杜绝任何 ../ 注入"""
        # 移除可能导致路径穿越的敏感成分
        clean_name = os.path.basename(filename)
        target_path = os.path.join(self.skills_root, clean_name)
        return target_path

    def write_file(self, filename: str, content: str) -> str:
        """安全地在技能库中写入新脚本"""
        target_path = self._safe_path(filename)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"💾 自定义技能文件已物理保存: {target_path}")
        return os.path.basename(filename)

    def read_file(self, filename: str) -> str:
        """安全地从技能库读取已有脚本"""
        target_path = self._safe_path(filename)
        if not os.path.exists(target_path):
            raise FileNotFoundError(f"❌ 技能库未找到文件: '{filename}'")
        with open(target_path, encoding="utf-8") as f:
            return f.read()

    def list_files(self) -> list[str]:
        """列出当前已习得的所有技能文件"""
        self._ensure_skills_root()
        files = []
        for name in os.listdir(self.skills_root):
            # 过滤掉系统隐藏文件和初始化脚本
            if name.startswith(".") or name.startswith("__"):
                continue
            if os.path.isfile(os.path.join(self.skills_root, name)):
                files.append(name)
        return sorted(files)

    def delete_file(self, filename: str) -> bool:
        """在技能库中删除指定脚本"""
        target_path = self._safe_path(filename)
        if os.path.exists(target_path):
            os.remove(target_path)
            logger.info(f"🗑️ 已从物理磁盘中彻底擦除技能脚本: {target_path}")
            return True
        return False
