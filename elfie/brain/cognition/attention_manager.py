import logging
from typing import Dict, Any

logger = logging.getLogger("elfie.cognition.attention_manager")

class AttentionManager:
    """注意力调度网络 (DMN / CEN / SN 脑网络管理)"""

    def __init__(self):
        # 默认模式为 DMN (发呆/离线思考/自言自语)
        self.current_network = "DMN"
        self._interrupted = False

    def evaluate_state(self, has_new_user_message: bool, salience_score: float) -> str:
        """
        根据外界输入的突显度评分和是否有新消息，动态切换脑网络
        :param has_new_user_message: 主人是否发了新消息 (触发 CEN 任务)
        :param salience_score: 传感器捕获的外界物理突发强度 (0-100，如环境大噪音，温度剧烈变动等)
        :return: 当前激活的脑网络类型
        """
        old_network = self.current_network
        
        # 1. 突发威胁/重大环境变动 (突显网络 SN 优先强行拦截打断)
        if salience_score >= 70.0:
            self.current_network = "SN"
            if old_network != "SN":
                logger.warning(f"🚨 [脑网络触发 SN 突显拦截] 检测到高突显度信号 ({salience_score})！强行打断当前发呆！")
                self._interrupted = True
                
        # 2. 主人直接任务下达 (中央执行网络 CEN 专注干活)
        elif has_new_user_message:
            self.current_network = "CEN"
            if old_network != "CEN":
                logger.info("🎯 [脑网络切换 CEN] 主人下达任务，大脑进入深度专注执行状态。")
                
        # 3. 闲置状态下回退至默认网络 (DMN 发呆/消耗多余电能整理三观)
        else:
            self.current_network = "DMN"
            if old_network != "DMN":
                logger.info("💭 [脑网络切换 DMN] 大脑进入静默发呆、自言自语及整理历史记忆的离线模式。")
                
        return self.current_network

    def is_interrupted(self) -> bool:
        """是否刚刚发生了 SN 打断，读取后会自动复位"""
        val = self._interrupted
        self._interrupted = False
        return val
