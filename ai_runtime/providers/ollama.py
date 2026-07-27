import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from typing import List, Mapping, Optional

logger = logging.getLogger("ai_runtime.providers.ollama")


class OllamaNotReadyError(Exception):
    """Ollama 算力底座无法就绪或自启动失败的特有异常"""

    pass


class OllamaManager:
    """运行时轻量级 Ollama 进程自愈与状态管理器"""

    def __init__(self, config):
        self.config = config

    def check_health(self) -> bool:
        """极速心跳探测 (100ms 级别)"""
        url = f"{self.config.ollama_host}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            # 缩短超时时间以实现毫秒级快速无感检测
            with urllib.request.urlopen(req, timeout=1.0) as response:
                return response.status == 200
        except Exception:
            return False

    def list_installed_models(self) -> tuple[str, ...]:
        url = f"{self.config.ollama_host}/api/tags"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2.0) as response:
            data = json.loads(response.read().decode("utf-8"))
        return tuple(
            model.get("name", "")
            for model in data.get("models", [])
            if model.get("name")
        )

    def has_model(self, model_name: str) -> bool:
        installed = self.list_installed_models()
        return any(
            name == model_name or name.split(":", 1)[0] == model_name
            for name in installed
        )

    def ensure_service_started(self) -> bool:
        """
        保证 Ollama 算力服务处于运行状态
        心跳探测通过直接返回；若未通畅，执行秒级后台静默拉起
        """
        if self.check_health():
            return True

        if os.environ.get("ELFIENEST_SUPERVISED") == "1":
            raise OllamaNotReadyError(
                "❌ Ollama 未就绪；当前由 Electron supervisor 托管，Core 不会自行启动 Ollama。"
            )

        launch_command = self._recorded_launch_command()
        if launch_command is None:
            raise OllamaNotReadyError(
                "❌ 当前 Ollama 没有可启动的固定绑定。\n"
                "💡 请通过初始化向导绑定已安装的公共 Ollama，或进入修复流程。"
            )
        logger.warning("🔌 已绑定的公共 Ollama 未响应，尝试启动该固定安装。")

        try:
            # 静默拉起后台守护进程
            # preexec_fn 用于在 Unix 下使子进程脱离终端控制，防止 main 退出时被误杀
            subprocess.Popen(
                launch_command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setpgrp if sys.platform != "win32" else None,
            )

            # 快速自旋等待 (每次等 200ms，共 25 次，上限 5 秒)
            for _ in range(25):
                time.sleep(0.2)
                if self.check_health():
                    logger.info("✅ Ollama 算力自愈成功，服务已在后台运行！")
                    return True

            # 若超时仍未连通，说明服务因某些原因拉起失败 (如端口被占用)
            raise OllamaNotReadyError(
                "❌ 已绑定的 Ollama 启动超时 (5s)！请在初始化向导中检查该绑定。"
            )

        except Exception as e:
            if isinstance(e, OllamaNotReadyError):
                raise e
            raise OllamaNotReadyError(f"❌ 自愈拉起 Ollama 子进程异常: {e}") from e

    def _recorded_launch_command(self) -> Optional[List[str]]:
        providers = getattr(self.config, "providers", {})
        if not isinstance(providers, Mapping):
            return None
        provider = providers.get("ollama")
        if not isinstance(provider, Mapping):
            return None
        installation = provider.get("installation")
        if not isinstance(installation, Mapping):
            return None
        platform = installation.get("platform")
        install_kind = installation.get("install_kind")
        launch_target = installation.get("launch_target")
        if not all(
            isinstance(value, str) and value
            for value in (platform, install_kind, launch_target)
        ):
            return None
        platform_name = str(platform)
        installation_kind = str(install_kind)
        target = str(launch_target)
        if platform_name == "darwin":
            return ["/usr/bin/open", "-a", target]
        if platform_name == "win32":
            return [target]
        if platform_name == "linux" and installation_kind == "systemd-user":
            return ["systemctl", "--user", "start", target]
        if platform_name == "linux":
            return [target, "serve"]
        return None
