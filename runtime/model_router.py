import logging
from typing import Tuple, Dict, Any
from runtime.config import LLMRuntimeConfig

logger = logging.getLogger("runtime.model_router")

class ModelRouter:
    """智能模型动态路由（平时用本地小模型，深度思考与工具调用切云端大模型）"""

    def __init__(self, config: LLMRuntimeConfig):
        self.config = config

    def route_request(self, prompt: str, energy: float, task_complexity: int = 1) -> Tuple[str, Dict[str, Any]]:
        """
        进行智能模型路由选择
        :param prompt: 任务 prompt 文本
        :param energy: 精灵当前精力值（下丘脑提供，范围 0-100）
        :param task_complexity: 预测任务复杂度（范围 1-5，如 1 为闲聊，5 为复杂算术或代码规划）
        :return: (选用的模型模式 - "local" 或 "remote", 路由决策的详细上下文信息)
        """
        logger.info(f"进行大模型路由评定 - 精力: {energy}%, 复杂度: {task_complexity}")
        
        # 1. 强制精力保护：精力不足时只走本地，避免大量能耗和 API 费用
        if energy < self.config.energy_threshold_fast:
            reason = f"精力过低 ({energy}% < {self.config.energy_threshold_fast}%)，触发快速本地大模型保护机制"
            logger.info(reason)
            return "local", {"mode": "local", "reason": reason, "model": self.config.ollama_model_fast}
            
        # 2. 检查是否有强烈的“计算”、“搜索”词汇
        complexity = task_complexity
        intent_keywords_deep = ["计算", "算出", "帮我算", "搜索", "查一下", "最新", "账单", "代码"]
        if any(kw in prompt for kw in intent_keywords_deep):
            complexity = max(complexity, 4)  # 强行拉升复杂度
            
        # 3. 基于任务复杂度进行路由决策
        if complexity >= self.config.complexity_threshold_deep:
            reason = f"任务复杂度较高 ({complexity} >= {self.config.complexity_threshold_deep})，分配云端高级大模型进行深度推理"
            logger.info(reason)
            # 如果远程 API KEY 没配置，会优雅退回到本地并发出警告
            if not self.config.remote_api_key:
                warning_reason = "云端 API Key 未配置，降级使用本地小模型进行深度推理"
                logger.warning(warning_reason)
                return "local", {"mode": "local", "reason": warning_reason, "model": self.config.ollama_model_fast}
            return "remote", {"mode": "remote", "reason": reason, "model": self.config.remote_model_deep}
            
        # 4. 默认走本地快速闲聊
        reason = f"常规日常对话且能量充沛，路由给本地轻量大模型"
        logger.info(reason)
        return "local", {"mode": "local", "reason": reason, "model": self.config.ollama_model_fast}
