# -*- coding: utf-8 -*-

import os
import sys
import time
import urllib.request
import shutil
import subprocess
import logging

logger = logging.getLogger("runtime.ollama_manager")

class OllamaNotReadyError(Exception):
    """Ollama 算力底座无法就绪或自启动失败的特有异常"""
    pass

class OllamaManager:
    """运行时轻量级 Ollama 进程自愈与状态管理器"""
    
    def __init__(self, config):
        self.config = config
        self.runtime_dir = os.path.dirname(os.path.abspath(__file__))
        self.ollama_path = os.path.join(self.runtime_dir, "bin", "ollama")

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

    def ensure_service_started(self) -> bool:
        """
        保证 Ollama 算力服务处于运行状态
        心跳探测通过直接返回；若未通畅，执行秒级后台静默拉起
        """
        if self.check_health():
            return True
            
        logger.warning("🔌 本地 Ollama 算力端口未响应！尝试进行自愈式拉起...")
        
        # 寻找可执行文件 (优先项目 bin 下的，其次是系统 PATH)
        ollama_exec = None
        if os.path.exists(self.ollama_path):
            ollama_exec = self.ollama_path
        else:
            ollama_exec = shutil.which("ollama")
            
        if not ollama_exec:
            raise OllamaNotReadyError(
                "❌ 本地未检测到已部署的 Ollama 算力底座可执行程序！\n"
                "💡 请在终端中运行静态引导脚本进行安装拉取：\n"
                "   python runtime/setup_runtime.py"
            )
            
        try:
            # 静默拉起后台守护进程
            # preexec_fn 用于在 Unix 下使子进程脱离终端控制，防止 main 退出时被误杀
            process = subprocess.Popen(
                [ollama_exec, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setpgrp if sys.platform != "win32" else None
            )
            
            # 快速自旋等待 (每次等 200ms，共 25 次，上限 5 秒)
            for attempt in range(25):
                time.sleep(0.2)
                if self.check_health():
                    logger.info("✅ Ollama 算力自愈成功，服务已在后台运行！")
                    return True
            
            # 若超时仍未连通，说明服务因某些原因拉起失败 (如端口被占用)
            raise OllamaNotReadyError(
                f"❌ Ollama 服务拉起超时 (5s)！请手动执行 '{ollama_exec} serve' 检查服务日志。"
            )
            
        except Exception as e:
            if isinstance(e, OllamaNotReadyError):
                raise e
            raise OllamaNotReadyError(f"❌ 自愈拉起 Ollama 子进程异常: {e}")
