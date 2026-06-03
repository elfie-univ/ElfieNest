from typing import Any, Dict


class ModelRegistry:
    """大模型算力池注册中心，维护模型类型、多模态能力与计费等级元数据"""

    def __init__(self, config):
        self.config = config

    def _is_provider_active(self, provider: str) -> bool:
        """检查特定提供商的 API 密钥是否已录入或是否为本地 Ollama"""
        if provider == "ollama":
            return True
        provider_info = self.config.providers.get(provider, {})
        return bool(provider_info.get("api_key"))

    def get_catalog(self) -> Dict[str, Dict[str, Any]]:
        """
        获取动态算力注册池清单
        依据当前的 config 动态展示模型的激活状态
        """
        cheap_active = self._is_provider_active(self.config.cheap_provider)
        deep_active = self._is_provider_active(self.config.deep_provider)
        multimodal_active = self._is_provider_active(self.config.multimodal_provider)

        # 探测是否支持原生音频：目前仅 OpenAI 和 Gemini 平台对某些模型开启原生音频多模态
        cheap_audio = self.config.cheap_provider in ["openai", "gemini"]
        deep_audio = self.config.deep_provider in ["openai", "gemini"]
        multimodal_audio = self.config.multimodal_provider in ["openai", "gemini"]

        # 探测是否支持视觉 (云端主流提供商默认开放视觉多模态，以提供最大兼容包容性)
        cheap_vision = (
            self.config.cheap_provider in ["openai", "gemini", "qwen"]
            or "vl" in self.config.cheap_model.lower()
        )
        deep_vision = (
            self.config.deep_provider in ["openai", "gemini", "qwen"]
            or "vl" in self.config.deep_model.lower()
        )
        multimodal_vision = (
            self.config.multimodal_provider in ["openai", "gemini", "qwen"]
            or "vl" in self.config.multimodal_model.lower()
        )

        return {
            "local_fast": {
                "name": self.config.ollama_model_fast,
                "provider": "ollama",
                "is_vision": False,
                "is_audio": False,
                "cost_tier": 0,  # 免费
                "active": True,
            },
            "local_vision": {
                "name": self.config.ollama_model_vision,
                "provider": "ollama",
                "is_vision": True,
                "is_audio": False,
                "cost_tier": 0,
                "active": True,
            },
            "remote_cheap": {
                "name": self.config.cheap_model,
                "provider": self.config.cheap_provider,
                "is_vision": cheap_vision,
                "is_audio": cheap_audio,
                "cost_tier": 1,  # 极低
                "active": cheap_active,
            },
            "remote_deep": {
                "name": self.config.deep_model,
                "provider": self.config.deep_provider,
                "is_vision": deep_vision,
                "is_audio": deep_audio,
                "cost_tier": 3,  # 高难推理
                "active": deep_active,
            },
            "remote_multimodal": {
                "name": self.config.multimodal_model,
                "provider": self.config.multimodal_provider,
                "is_vision": multimodal_vision,
                "is_audio": multimodal_audio,
                "cost_tier": 2,  # 多模态
                "active": multimodal_active,
            },
        }

    def list_available_models(self) -> Dict[str, Dict[str, Any]]:
        """
        列出当前所有激活并可供上游大脑调配的模型
        """
        catalog = self.get_catalog()
        return {key: val for key, val in catalog.items() if val["active"]}

    def get_model_info(self, model_key: str) -> Dict[str, Any]:
        """
        获取指定模型 key 的能力元数据
        """
        catalog = self.get_catalog()
        if model_key not in catalog:
            raise KeyError(f"模型注册中心未找到指定算力 Key: '{model_key}'")
        return catalog[model_key]
