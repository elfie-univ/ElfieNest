import json
import os
from dataclasses import dataclass, field
from typing import Any

# 🌟 大模型跨服务商算力预设与精选推荐清单
PROVIDER_RECOMMENDS: dict[str, dict[str, Any]] = {
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


@dataclass
class LLMRuntimeConfig:
    """大模型运行时跨服务商混合算力网格配置"""

    # 1. 多订阅源字典：存储各个 Provider 的 API Key 与 Base 节点 (支持从环境变量加载默认值)
    providers: dict[str, dict[str, str]] = field(
        default_factory=lambda: {
            "deepseek": {
                "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
                "api_base": os.getenv(
                    "DEEPSEEK_API_BASE", PROVIDER_RECOMMENDS["deepseek"]["api_base"]
                ),
            },
            "openai": {
                "api_key": os.getenv("OPENAI_API_KEY", ""),
                "api_base": os.getenv(
                    "OPENAI_API_BASE", PROVIDER_RECOMMENDS["openai"]["api_base"]
                ),
            },
            "gemini": {
                "api_key": os.getenv("GEMINI_API_KEY", ""),
                "api_base": os.getenv(
                    "GEMINI_API_BASE", PROVIDER_RECOMMENDS["gemini"]["api_base"]
                ),
            },
            "qwen": {
                "api_key": os.getenv("QWEN_API_KEY", ""),
                "api_base": os.getenv(
                    "QWEN_API_BASE", PROVIDER_RECOMMENDS["qwen"]["api_base"]
                ),
            },
            "ollama": {
                "api_key": "",
                "api_base": os.getenv(
                    "OLLAMA_HOST", PROVIDER_RECOMMENDS["ollama"]["api_base"]
                ),
            },
        }
    )

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

    def __post_init__(self):
        # 尝试自检测并热加载持久化的本地 JSON 算力配置文件
        json_path = os.path.join(os.path.dirname(__file__), "runtime_config.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, encoding="utf-8") as f:
                    saved_cfg = json.load(f)

                # 递归更新 providers 字典以防止局部 key 缺失
                if "providers" in saved_cfg and isinstance(
                    saved_cfg["providers"], dict
                ):
                    for provider, info in saved_cfg["providers"].items():
                        if provider in self.providers:
                            if "api_key" in info:
                                self.providers[provider]["api_key"] = info["api_key"]
                            if "api_base" in info:
                                self.providers[provider]["api_base"] = info["api_base"]

                # 更新其他字段属性
                for k, v in saved_cfg.items():
                    if k != "providers" and hasattr(self, k) and v is not None:
                        setattr(self, k, v)
            except Exception:
                pass

        # 同步本地 ollama_host 的最新变更到 providers 字典中
        if self.ollama_host:
            self.providers["ollama"]["api_base"] = self.ollama_host

    def to_dict(self) -> dict[str, Any]:
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
        }
