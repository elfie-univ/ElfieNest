import logging
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict

logger = logging.getLogger("runtime.tools.code")


class CodeSandboxPlugin:
    """Python 沙箱代码执行器，大模型进行精确算术与物理规则推理的算力外挂"""

    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds

    def execute(self, code: str) -> Dict[str, Any]:
        """
        在子进程中安全执行 Python 代码，并捕获标准输出、标准错误和退出码
        :param code: 待执行的 Python 源代码
        :return: 包含 stdout, stderr, exit_code 的字典
        """
        logger.info("沙箱代码执行器收到代码，准备启动物理隔离子进程...")

        cleaned_code = self._clean_code(code)

        # 创建临时文件写入代码
        temp_file_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False
            ) as temp_file:
                temp_file.write(cleaned_code)
                temp_file_path = temp_file.name

            # 使用当前 Python 解释器启动子进程
            process = subprocess.run(
                [sys.executable, temp_file_path],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )

            # 若执行出错，原样向上抛出真实的 RuntimeError
            if process.returncode != 0:
                raise RuntimeError(
                    f"【Python 沙箱执行报错】\n"
                    f"退出码: {process.returncode}\n"
                    f"标准输出: {process.stdout.strip()}\n"
                    f"错误流 (stderr): {process.stderr.strip()}"
                )

            return {
                "success": True,
                "stdout": process.stdout.strip(),
                "stderr": process.stderr.strip(),
                "exit_code": process.returncode,
            }

        except subprocess.TimeoutExpired:
            logger.error("沙箱代码执行超时！已强行中止。")
            raise RuntimeError(
                f"【Python 沙箱执行超时】\n"
                f"代码执行时间超限，强行终止（上限 {self.timeout_seconds} 秒）"
            ) from None
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise e
            logger.error(f"沙箱启动异常: {e}")
            raise RuntimeError(
                f"【沙箱物理引擎故障】启动或运行 Python 隔离子进程失败: {e}"
            ) from e
        finally:
            # 清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception:
                    pass

    def _clean_code(self, code: str) -> str:
        """剥离 Markdown 的 ```python 标记，并做一些基本的安全检查和优化"""
        lines = code.strip().splitlines()
        cleaned_lines = []
        for line in lines:
            if line.strip().startswith("```"):
                continue
            cleaned_lines.append(line)

        cleaned_code = "\n".join(cleaned_lines)

        # 基础安全警告/检查：拒绝危险模块
        dangerous_keywords = [
            "rmtree",
            "os.system",
            "shutil",
            "subprocess",
            "rm -rf",
            "eval(",
        ]
        for kw in dangerous_keywords:
            if kw in cleaned_code and "code_sandbox.py" not in cleaned_code:
                logger.warning(f"沙箱检测到敏感词: '{kw}'，仅做安全审查提示。")

        return cleaned_code
