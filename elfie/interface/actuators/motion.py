# -*- coding: utf-8 -*-
import logging
from typing import Dict, Any
from elfie.body.anatomy.base import SomaticAnatomy
from elfie.body.actuators.gait import GaitEngine

logger = logging.getLogger("elfie.interface.actuators.motion")

class MotionActuator:
    """神经交互总线：行动输出 - 肢体肢体与关节运动控制器"""

    def __init__(self):
        self.gait_engine = GaitEngine()
        self.last_action_intent = "idle"

    def translate_and_drive(self, 
                            anatomy: SomaticAnatomy, 
                            action_intent: str, 
                            speed: float = 1.0, 
                            elapsed_time: float = 0.0) -> Dict[str, float]:
        """
        核心物理驱动：将大脑做出的宏观动作决策 (高阶意图) 翻译为具体多关节角度，并安全驱动 Body 关节点
        :param anatomy: 精灵的具身数字孪生躯壳描述 (SomaticAnatomy)
        :param action_intent: 高阶姿态意图 ("walk", "run", "idle", "wave_hands", "wag_tail", "nod_head")
        :param speed: 速度频段因子
        :param elapsed_time: 自仿真以来时间步累计
        :return: 经过小脑限位后的各关节实际输出角度值字典
        """
        self.last_action_intent = action_intent
        
        # 1. 针对简单无周期控制做特殊处理
        if action_intent == "nod_head":
            # 简单点头：脖子瞬间下压 0.4 弧度
            target_angles = {"neck_pitch": 0.4, "head_yaw": 0.0}
        elif action_intent == "blink_eyes" or not action_intent:
            # 眨眼/静默姿态：全身关节置零
            target_angles = {name: 0.0 for name in anatomy.joints.keys()}
        else:
            # 2. 调用小脑步态协同发生器产生连续波形
            target_angles = self.gait_engine.generate_step_angles(
                anatomy=anatomy,
                gait_type=action_intent,
                speed=speed,
                elapsed_time=elapsed_time
            )
            
        # 3. 灌入数字孪生 Body 关节，执行解剖学物理旋转截断限位
        actual_driven_angles = anatomy.apply_joint_angles(target_angles)
        
        # 4. 模拟打包关节状态发送给 Godot 端
        logger.info(
            f"🐾 [神经关节总线] 高阶动作 '{action_intent}' -> "
            f"计算产生 {len(actual_driven_angles)} 个关节驱动信号发往 Godot. "
            f"当前驱动角示例: { {k: round(v, 2) for k, v in list(actual_driven_angles.items())[:3]} }"
        )
        
        return actual_driven_angles
