import logging
from typing import Dict, Any

logger = logging.getLogger("elfie.interface.actuators.motion")

class MotionActuator:
    """底层：行动输出 - 肢体 (电机舵机与形象动图控制器)"""

    def __init__(self):
        self.last_action = ""

    def execute_action(self, action_name: str) -> bool:
        """
        控制精灵物理身体摇尾巴、动耳朵或眨眼睛
        :param action_name: 动作标识符 (如 "wag_tail")
        :return: 是否执行成功
        """
        if not action_name:
            return False
            
        logger.info(f"🐾 [肢体动作驱动] 启动电机/执行动画: '{action_name}'")
        self.last_action = action_name
        # 真实硬件上，这里会发送 PWM 占空比给舵机控制板，驱动毛绒小尾巴摆动
        return True
