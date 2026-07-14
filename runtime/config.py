import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml

from .providers.profiles import get_default_api_mode
from .storage.data_home import get_config_path, get_env_path


def _load_env_file_values(env_path: Path | None = None) -> Dict[str, str]:
    env_path = env_path or get_env_path()
    env_values: Dict[str, str] = {}
    if not os.path.exists(env_path):
        return env_values
    try:
        with open(env_path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env_values[key.strip()] = value.strip()
    except OSError:
        return env_values
    return env_values


def _env_value(
    env_values: Dict[str, str],
    key: str,
    default: str = "",
    *,
    include_process_env: bool = True,
) -> str:
    if include_process_env:
        return os.getenv(key, env_values.get(key, default))
    return env_values.get(key, default)


def _default_providers(
    env_path: Path | None = None,
    *,
    include_process_env: bool = True,
) -> Dict[str, Dict[str, str]]:
    env_values = _load_env_file_values(env_path)
    return {
        "deepseek": {
            "api_key": _env_value(
                env_values,
                "DEEPSEEK_API_KEY",
                include_process_env=include_process_env,
            ),
            "api_base": _env_value(
                env_values,
                "DEEPSEEK_API_BASE",
                PROVIDER_RECOMMENDS["deepseek"]["api_base"],
                include_process_env=include_process_env,
            ),
            "api_mode": "chat_completions",
        },
        "openai": {
            "api_key": _env_value(
                env_values,
                "OPENAI_API_KEY",
                include_process_env=include_process_env,
            ),
            "api_base": _env_value(
                env_values,
                "OPENAI_API_BASE",
                PROVIDER_RECOMMENDS["openai"]["api_base"],
                include_process_env=include_process_env,
            ),
            "api_mode": "chat_completions",
        },
        "custom_openai": {
            "api_key": _env_value(
                env_values,
                "CUSTOM_OPENAI_API_KEY",
                include_process_env=include_process_env,
            ),
            "api_base": _env_value(
                env_values,
                "CUSTOM_OPENAI_API_BASE",
                "http://localhost:8000/v1",
                include_process_env=include_process_env,
            ),
            "api_mode": "chat_completions",
            "test_model": "custom-model",
        },
        "gemini": {
            "api_key": _env_value(
                env_values,
                "GEMINI_API_KEY",
                include_process_env=include_process_env,
            ),
            "api_base": _env_value(
                env_values,
                "GEMINI_API_BASE",
                PROVIDER_RECOMMENDS["gemini"]["api_base"],
                include_process_env=include_process_env,
            ),
            "api_mode": "chat_completions",
        },
        "qwen": {
            "api_key": _env_value(
                env_values,
                "QWEN_API_KEY",
                include_process_env=include_process_env,
            ),
            "api_base": _env_value(
                env_values,
                "QWEN_API_BASE",
                PROVIDER_RECOMMENDS["qwen"]["api_base"],
                include_process_env=include_process_env,
            ),
            "api_mode": "chat_completions",
        },
        "ollama": {
            "api_key": "",
            "api_base": _env_value(
                env_values,
                "OLLAMA_HOST",
                PROVIDER_RECOMMENDS["ollama"]["api_base"],
                include_process_env=include_process_env,
            ),
            "api_mode": "ollama",
        },
    }


# 🌟 大模型跨服务商算力预设与精选推荐清单
PROVIDER_RECOMMENDS: Dict[str, Dict[str, Any]] = {
    "deepseek": {
        "name": "DeepSeek",
        "api_base": "https://api.deepseek.com/v1",
        "cheap_models": ["deepseek-chat"],
        "deep_models": ["deepseek-reasoner", "deepseek-chat"],
        "multimodal_models": ["deepseek-chat"],  # 暂无原生多模态，用 chat 替代
    },
    "openai": {
        "name": "OpenAI",
        "api_base": "https://api.openai.com/v1",
        "cheap_models": ["gpt-4o-mini", "gpt-3.5-turbo"],
        "deep_models": ["gpt-4o", "o1-mini", "o3-mini"],
        "multimodal_models": ["gpt-4o"],
    },
    "gemini": {
        "name": "Gemini",
        "api_base": "https://generativelanguage.googleapis.com/v1beta",
        "cheap_models": ["gemini-1.5-flash", "gemini-2.0-flash"],
        "deep_models": ["gemini-1.5-pro", "gemini-2.0-pro-exp"],
        "multimodal_models": ["gemini-1.5-flash", "gemini-1.5-pro"],
    },
    "qwen": {
        "name": "Ali Qwen (DashScope)",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "cheap_models": ["qwen-coder-turbo", "qwen-turbo", "qwen-plus"],
        "deep_models": ["qwen-coder-plus", "qwen-max"],
        "multimodal_models": ["qwen-vl-plus", "qwen-vl-max"],
    },
    "ollama": {
        "name": "本地 Ollama",
        "api_base": "http://localhost:11434",
        "cheap_models": ["qwen3.5:0.8b", "qwen2.5:0.5b", "llama3.2:1b"],
        "deep_models": ["qwen3.5:4b", "qwen2.5:7b", "llama3:8b"],
        "multimodal_models": ["moondream", "llava"],
    },
}


# ---------------------------------------------------------------------------
# 系统设置默认值 & 深层合并工具
# ---------------------------------------------------------------------------


def deep_update(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并 ``updates`` 到 ``base``（就地修改）。

    对于嵌套字典键，递归合并；否则直接覆盖。
    """
    for k, v in updates.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            deep_update(base[k], v)
        else:
            base[k] = v
    return base


DEFAULT_SYSTEM_SETTINGS: Dict[str, Dict[str, Any]] = {
    "llm": {
        "default_cheap_model": "qwen3.5:0.8b",
        "default_cheap_provider": "ollama",
        "default_deep_model": "qwen3.5:0.8b",
        "default_deep_provider": "ollama",
        "default_multimodal_model": "moondream",
        "default_multimodal_provider": "ollama",
        "temperature": 0.7,
        "max_tokens": 1500,
        "energy_threshold_fast": 30,
        "complexity_threshold_deep": 4,
    },
    "adoption": {
        "max_elfies_per_user": 3,
        "allowed_anatomy_types": ["biped", "quadruped"],
        "personality_presets_enabled": {
            "活泼好动": True,
            "安静温顺": True,
            "好奇探索": True,
            "胆小害羞": True,
            "傲娇独立": True,
            "完全随机": True,
        },
    },
    "engine": {
        "tick_interval_sec": 1.5,
        "tts_enabled": True,
        "max_elfies_per_room": None,
        "default_tts_voice": "zh-CN-XiaoxiaoNeural",
    },
    "security": {
        "session_ttl_days": 7,
        "rate_limit": {"max_attempts": 5, "window_seconds": 300},
    },
}


@dataclass
class LLMRuntimeConfig:
    """大模型运行时跨服务商混合算力网格配置"""

    # 1. 多订阅源字典：存储各个 Provider 的 API Key、Base 节点、API 模式与状态
    providers: Dict[str, Dict[str, str]] = field(default_factory=dict)

    # 独立工具可指定自己的配置目录，避免读取正式运行配置和密钥。
    config_home: str | None = field(default=None, repr=False, compare=False)

    # 2. 算力分档路由映射 (模型名称 + 归属 Provider 绑定)
    cheap_model: str = "qwen3.5:0.8b"
    cheap_provider: str = "ollama"

    deep_model: str = "qwen3.5:0.8b"
    deep_provider: str = "ollama"

    multimodal_model: str = "moondream"
    multimodal_provider: str = "ollama"

    # 3. 本地 Ollama 参数 (向下兼容与心跳拉起)
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model_fast: str = os.getenv("OLLAMA_MODEL_FAST", "qwen3.5:0.8b")
    ollama_model_vision: str = os.getenv("OLLAMA_MODEL_VISION", "moondream")

    # 4. 路由与能耗控制阈值
    energy_threshold_fast: float = (
        30.0  # 物理精力低于 30% 强制降级使用 cheap 模型以省钱/省电
    )
    complexity_threshold_deep: int = 3  # 复杂度大于等于 3 使用 deep 深度模型

    # 5. 超参数
    temperature: float = 0.7
    max_tokens: int = 1500

    # 6. 系统设置（深层合并持久化文件中保存的部分）
    system: Dict[str, Dict[str, Any]] = field(
        default_factory=lambda: copy.deepcopy(DEFAULT_SYSTEM_SETTINGS)
    )
    runtime_policy: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        scoped_home = Path(self.config_home).expanduser() if self.config_home else None
        defaults = _default_providers(
            scoped_home / ".env" if scoped_home else None,
            include_process_env=scoped_home is None,
        )
        if self.providers:
            deep_update(defaults, self.providers)
        self.providers = defaults

        # 尝试自检测并热加载持久化的本地 YAML 配置文件
        saved_cfg = None
        yaml_path = scoped_home / "config.yaml" if scoped_home else get_config_path()
        if os.path.exists(yaml_path):
            try:
                with open(yaml_path, encoding="utf-8") as f:
                    saved_cfg = yaml.safe_load(f)
            except Exception:
                pass

        # 向后兼容：如果 YAML 不存在，尝试加载旧版 JSON 配置
        if saved_cfg is None and scoped_home is None:
            json_path = os.path.join(os.path.dirname(__file__), "runtime_config.json")
            if os.path.exists(json_path):
                try:
                    with open(json_path, encoding="utf-8") as f:
                        saved_cfg = json.load(f)
                except Exception:
                    pass

        # 合并配置到当前实例
        if saved_cfg is not None:
            try:
                # 递归更新 providers 字典以防止局部 key 缺失
                if "providers" in saved_cfg and isinstance(
                    saved_cfg["providers"], dict
                ):
                    for provider, info in saved_cfg["providers"].items():
                        if provider not in self.providers:
                            self.providers[provider] = {}
                        if "api_key" in info:
                            self.providers[provider]["api_key"] = info["api_key"]
                        if "api_base" in info:
                            self.providers[provider]["api_base"] = info["api_base"]
                        if "api_mode" in info:
                            self.providers[provider]["api_mode"] = info["api_mode"]
                        if "status" in info and info["status"] in (
                            "active",
                            "inactive",
                        ):
                            self.providers[provider]["status"] = info["status"]
                        if "test_model" in info:
                            self.providers[provider]["test_model"] = info["test_model"]
                        if "display_name" in info:
                            self.providers[provider]["display_name"] = info[
                                "display_name"
                            ]

                # 更新其他字段属性（system 键深层合并，其余直接覆盖）
                for k, v in saved_cfg.items():
                    if k != "providers" and hasattr(self, k) and v is not None:
                        if k == "system" and isinstance(v, dict):
                            deep_update(self.system, v)
                        else:
                            setattr(self, k, v)
            except Exception:
                pass

        # 确保 providers 字典中所有条目都有 api_mode 和 status
        for provider in self.providers:
            # api_mode: 从 BUILTIN_PROFILES 获取，未知服务商默认 chat_completions
            if "api_mode" not in self.providers[provider]:
                self.providers[provider]["api_mode"] = get_default_api_mode(provider)
            # status: 如果 saved_cfg 中显式设置了 status，则使用它；否则根据 api_key 计算
            saved_status = None
            if saved_cfg and "providers" in saved_cfg:
                saved_info = saved_cfg["providers"].get(provider, {})
                if "status" in saved_info and saved_info["status"] in (
                    "active",
                    "inactive",
                ):
                    saved_status = saved_info["status"]
            if saved_status:
                self.providers[provider]["status"] = saved_status
            else:
                api_key = self.providers[provider].get("api_key", "")
                self.providers[provider]["status"] = (
                    "active" if api_key or provider == "ollama" else "inactive"
                )

        if scoped_home is not None and saved_cfg is None:
            self.ollama_host = self.providers["ollama"]["api_base"]

        # 同步本地 ollama_host 的最新变更到 providers 字典中
        if self.ollama_host:
            self.providers["ollama"]["api_base"] = self.ollama_host

    @classmethod
    def load(cls, config_home: str | None = None) -> "LLMRuntimeConfig":
        """加载当前运行时配置（每次调用重新读取）。"""
        return cls(config_home=config_home)

    def to_dict(self) -> Dict[str, Any]:
        """将当前混配配置全量转化为字典格式以供持久化保存"""
        return {
            "providers": self.providers,
            "cheap_model": self.cheap_model,
            "cheap_provider": self.cheap_provider,
            "deep_model": self.deep_model,
            "deep_provider": self.deep_provider,
            "multimodal_model": self.multimodal_model,
            "multimodal_provider": self.multimodal_provider,
            "ollama_host": self.ollama_host,
            "ollama_model_fast": self.ollama_model_fast,
            "ollama_model_vision": self.ollama_model_vision,
            "energy_threshold_fast": self.energy_threshold_fast,
            "complexity_threshold_deep": self.complexity_threshold_deep,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "system": self.system,
            "runtime_policy": self.runtime_policy,
        }
