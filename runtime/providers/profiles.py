"""LLM 服务商声明式注册配置。

每个 ProviderProfile 定义一个 LLM 服务商的完整配置：
- 连接参数 (api_base, auth_type, api_mode)
- 环境变量映射 (base_url_env_var, api_key_env_var)
- 推荐模型清单 (default_models)

参考：
- Hermes Agent 的 HermesOverlay dataclass 模式
- OpenClaw 的 ModelProviderConfig (types.models.ts)
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ProviderProfile:
    """LLM 服务商配置档案。

    Attributes:
        name: 显示名称，如 "OpenAI"
        api_base: 默认 API 基础 URL
        auth_type: 认证类型 ("bearer" | "x-api-key" | "none")
        api_mode: API 调用模式 ("ollama" | "chat_completions" | "anthropic_messages")
        base_url_env_var: 覆盖 api_base 的环境变量名
        api_key_env_var: 存储 API Key 的环境变量名
        default_models: 推荐模型清单，按用途分类
    """

    name: str
    api_base: str
    auth_type: str  # "bearer" | "x-api-key" | "none"
    api_mode: str  # "ollama" | "chat_completions" | "anthropic_messages"
    base_url_env_var: str  # 环境变量名，用于覆盖 api_base
    api_key_env_var: str  # 环境变量名，用于读取 API Key
    default_models: Dict[str, List[str]]  # {"cheap": [...], "deep": [...], "multimodal": [...]}


# ---------------------------------------------------------------------------
# 内置服务商档案（9 个主流 LLM 提供商）
# ---------------------------------------------------------------------------

BUILTIN_PROFILES: Dict[str, ProviderProfile] = {
    "ollama": ProviderProfile(
        name="Ollama",
        api_base="http://localhost:11434",
        auth_type="none",
        api_mode="ollama",
        base_url_env_var="OLLAMA_HOST",
        api_key_env_var="",
        default_models={
            "cheap": ["qwen3.5:0.8b", "qwen2.5:0.5b", "llama3.2:1b"],
            "deep": ["qwen3.5:4b", "qwen2.5:7b", "llama3:8b"],
            "multimodal": ["moondream", "llava"],
        },
    ),
    "openai": ProviderProfile(
        name="OpenAI",
        api_base="https://api.openai.com/v1",
        auth_type="bearer",
        api_mode="chat_completions",
        base_url_env_var="OPENAI_API_BASE",
        api_key_env_var="OPENAI_API_KEY",
        default_models={
            "cheap": ["gpt-4o-mini", "gpt-3.5-turbo"],
            "deep": ["gpt-4o", "o1-mini", "o3-mini"],
            "multimodal": ["gpt-4o"],
        },
    ),
    "anthropic": ProviderProfile(
        name="Anthropic",
        api_base="https://api.anthropic.com/v1",
        auth_type="x-api-key",
        api_mode="anthropic_messages",
        base_url_env_var="ANTHROPIC_API_BASE",
        api_key_env_var="ANTHROPIC_API_KEY",
        default_models={
            "cheap": ["claude-3-haiku-20240307"],
            "deep": ["claude-3-opus-20240229", "claude-3-sonnet-20240229"],
            "multimodal": ["claude-3-sonnet-20240229", "claude-3-opus-20240229"],
        },
    ),
    "deepseek": ProviderProfile(
        name="DeepSeek",
        api_base="https://api.deepseek.com/v1",
        auth_type="bearer",
        api_mode="chat_completions",
        base_url_env_var="DEEPSEEK_API_BASE",
        api_key_env_var="DEEPSEEK_API_KEY",
        default_models={
            "cheap": ["deepseek-chat"],
            "deep": ["deepseek-reasoner", "deepseek-chat"],
            "multimodal": ["deepseek-chat"],  # 暂无原生多模态，用 chat 替代
        },
    ),
    "gemini": ProviderProfile(
        name="Google Gemini",
        api_base="https://generativelanguage.googleapis.com/v1beta/openai",
        auth_type="bearer",
        api_mode="chat_completions",
        base_url_env_var="GEMINI_API_BASE",
        api_key_env_var="GEMINI_API_KEY",
        default_models={
            "cheap": ["gemini-1.5-flash", "gemini-2.0-flash"],
            "deep": ["gemini-1.5-pro", "gemini-2.0-pro-exp"],
            "multimodal": ["gemini-1.5-flash", "gemini-1.5-pro"],
        },
    ),
    "qwen": ProviderProfile(
        name="Ali Qwen (DashScope)",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        auth_type="bearer",
        api_mode="chat_completions",
        base_url_env_var="QWEN_API_BASE",
        api_key_env_var="QWEN_API_KEY",
        default_models={
            "cheap": ["qwen-coder-turbo", "qwen-turbo", "qwen-plus"],
            "deep": ["qwen-coder-plus", "qwen-max"],
            "multimodal": ["qwen-vl-plus", "qwen-vl-max"],
        },
    ),
    "xai": ProviderProfile(
        name="xAI (Grok)",
        api_base="https://api.x.ai/v1",
        auth_type="bearer",
        api_mode="chat_completions",
        base_url_env_var="XAI_API_BASE",
        api_key_env_var="XAI_API_KEY",
        default_models={
            "cheap": ["grok-beta"],
            "deep": ["grok-2-1212", "grok-2-vision-1212"],
            "multimodal": ["grok-2-vision-1212"],
        },
    ),
    "mistral": ProviderProfile(
        name="Mistral AI",
        api_base="https://api.mistral.ai/v1",
        auth_type="bearer",
        api_mode="chat_completions",
        base_url_env_var="MISTRAL_API_BASE",
        api_key_env_var="MISTRAL_API_KEY",
        default_models={
            "cheap": ["mistral-small-latest", "codestral-latest"],
            "deep": ["mistral-large-latest"],
            "multimodal": ["pixtral-12b-2409"],
        },
    ),
    "groq": ProviderProfile(
        name="Groq",
        api_base="https://api.groq.com/openai/v1",
        auth_type="bearer",
        api_mode="chat_completions",
        base_url_env_var="GROQ_API_BASE",
        api_key_env_var="GROQ_API_KEY",
        default_models={
            "cheap": ["llama-3.1-8b-instant", "llama-3.2-1b-preview"],
            "deep": ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile"],
            "multimodal": ["llava-v1.5-7b-4096-preview"],
        },
    ),
}


def get_profile(provider_name: str) -> ProviderProfile | None:
    """获取指定服务商的配置档案。

    Args:
        provider_name: 服务商标识符（如 "openai", "anthropic"）

    Returns:
        ProviderProfile 实例，不存在时返回 None
    """
    return BUILTIN_PROFILES.get(provider_name)


def get_default_api_mode(provider_name: str) -> str:
    """获取指定服务商的默认 API 模式。

    Args:
        provider_name: 服务商标识符

    Returns:
        API 模式字符串，未知服务商返回 "chat_completions"
    """
    profile = BUILTIN_PROFILES.get(provider_name)
    return profile.api_mode if profile else "chat_completions"
