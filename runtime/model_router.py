"""智能模型动态路由。

支持两种模式：
1. 每精灵路由（elfie_id 提供时）：基于场景分类 + 降级链
2. 全局路由（向后兼容）：基于能量 + 复杂度

路由优先级：
- 精力保护：低能量时强制本地模型
- 场景分类：根据 prompt + 注意力状态选择场景槽
- 降级链：能量不足或服务商不可用时自动降级
"""

import logging
from typing import Any, Dict, Optional, Tuple

from runtime.config import LLMRuntimeConfig
from runtime.model_route import resolve_model
from runtime.scene_classifier import classify_scene

logger = logging.getLogger("runtime.model_router")


class ModelRouter:
    """智能模型动态路由（支持每精灵独立路由策略）。"""

    def __init__(self, config: LLMRuntimeConfig):
        self.config = config

    def route_request(
        self,
        prompt: str,
        energy: float,
        task_complexity: int = 1,
        elfie_id: Optional[str] = None,
        attention_state: Optional[Dict[str, float]] = None,
        has_image: bool = False,
        has_audio: bool = False,
        tool_call_pending: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        进行智能模型路由选择。
        
        当 elfie_id 提供时，使用每精灵路由策略：
        1. 场景分类（基于注意力网络 + 关键词）
        2. 根据场景路由配置选择模型
        3. 考虑能量阈值和降级链
        
        当 elfie_id 未提供时，使用全局路由（向后兼容）：
        1. 能量保护
        2. 复杂度评估
        3. 关键词检测
        
        :param prompt: 任务 prompt 文本
        :param energy: 精灵当前精力值（下丘脑提供，范围 0-100）
        :param task_complexity: 预测任务复杂度（范围 1-5）
        :param elfie_id: 精灵 ID（提供时启用每精灵路由）
        :param attention_state: 注意力网络状态 {"SN": float, "CEN": float, "DMN": float}
        :param has_image: 是否有图片输入
        :param has_audio: 是否有音频输入
        :param tool_call_pending: 是否有待处理的工具调用
        :return: (模型模式 - "local" 或 "remote", 路由决策的详细上下文信息)
        """
        logger.info(f"进行大模型路由评定 - 精力: {energy}%, 复杂度: {task_complexity}")

        # ========================================
        # 每精灵路由模式
        # ========================================
        if elfie_id:
            return self._route_per_elfie(
                prompt=prompt,
                energy=energy,
                elfie_id=elfie_id,
                attention_state=attention_state,
                has_image=has_image,
                has_audio=has_audio,
                tool_call_pending=tool_call_pending,
            )

        # ========================================
        # 全局路由模式（向后兼容）
        # ========================================
        return self._route_global(prompt, energy, task_complexity)

    def _route_per_elfie(
        self,
        prompt: str,
        energy: float,
        elfie_id: str,
        attention_state: Optional[Dict[str, float]] = None,
        has_image: bool = False,
        has_audio: bool = False,
        tool_call_pending: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        """每精灵路由策略"""
        
        # 1. 场景分类
        scene = classify_scene(
            prompt=prompt,
            attention_state=attention_state,
            has_image=has_image,
            has_audio=has_audio,
            tool_call_pending=tool_call_pending,
        )
        
        logger.info(f"精灵 '{elfie_id}' 场景分类结果: {scene}")
        
        # 2. 解析模型
        provider, model_name = resolve_model(
            elfie_id=elfie_id,
            scene=scene,
            energy=energy,
            config=self.config,
        )
        
        # 3. 确定模式
        mode = "local" if provider == "ollama" else "remote"
        
        # 4. 构建决策上下文
        decision = {
            "mode": mode,
            "scene": scene,
            "model": model_name,
            "provider": provider,
            "elfie_id": elfie_id,
            "energy": energy,
        }
        
        reason = f"精灵 '{elfie_id}' 场景 '{scene}' → {provider}/{model_name}"
        logger.info(f"🔮 [每精灵路由] {reason}")
        
        return mode, decision

    def _route_global(
        self,
        prompt: str,
        energy: float,
        task_complexity: int,
    ) -> Tuple[str, Dict[str, Any]]:
        """全局路由策略（向后兼容旧逻辑）"""
        
        # 1. 强制精力保护：精力不足时只走本地，避免大量能耗和 API 费用
        if energy < self.config.energy_threshold_fast:
            reason = f"精力过低 ({energy}% < {self.config.energy_threshold_fast}%)，触发快速本地大模型保护机制"
            logger.info(reason)
            return "local", {
                "mode": "local",
                "reason": reason,
                "model": self.config.ollama_model_fast,
            }

        # 2. 检查是否有强烈的"计算"、"搜索"词汇
        complexity = task_complexity
        intent_keywords_deep = [
            "计算",
            "算出",
            "帮我算",
            "搜索",
            "查一下",
            "最新",
            "账单",
            "代码",
        ]
        if any(kw in prompt for kw in intent_keywords_deep):
            complexity = max(complexity, 4)  # 强行拉升复杂度

        # 3. 基于任务复杂度进行路由决策
        if complexity >= self.config.complexity_threshold_deep:
            reason = f"任务复杂度较高 ({complexity} >= {self.config.complexity_threshold_deep})，分配云端高级大模型进行深度推理"
            logger.info(reason)

            deep_provider = self.config.deep_provider
            provider_api_key = self.config.providers.get(deep_provider, {}).get(
                "api_key", ""
            )

            if deep_provider == "ollama" or not provider_api_key:
                warning_reason = f"深度推理Provider '{deep_provider}' 未配置API Key 或为本地模型，使用本地小模型"
                logger.warning(warning_reason)
                return "local", {
                    "mode": "local",
                    "reason": warning_reason,
                    "model": self.config.ollama_model_fast,
                }

            return "remote", {
                "mode": "remote",
                "reason": reason,
                "model": self.config.deep_model,
                "provider": deep_provider,
            }

        # 4. 默认走本地快速闲聊
        reason = "常规日常对话且能量充沛，路由给本地轻量大模型"
        logger.info(reason)
        return "local", {
            "mode": "local",
            "reason": reason,
            "model": self.config.ollama_model_fast,
        }
