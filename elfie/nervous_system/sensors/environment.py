import logging
from typing import Any, Dict

logger = logging.getLogger("elfie.nervous_system.sensors.environment")


class EnvironmentSensor:
    """神经交互总线：物理环境与具身触觉传感器 (Environment & Tactile Channels)"""

    def __init__(self):
        self.ambient_temperature = 22.0
        self.gravity = 9.8
        self.weather = "sunny"
        self.tactile_buffer = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 0.0,  # 抚摸频率 Hz
        }

    def update_from_godot_world(
        self, godot_world_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        从 Godot 虚拟世界同步环境温湿度、天气、重力等宏观物理指标
        :param godot_world_state: 仿真器发送的物理世界字典
        """
        self.ambient_temperature = godot_world_state.get("temperature", 22.0)
        self.gravity = godot_world_state.get("gravity", 9.8)
        self.weather = godot_world_state.get("weather", "sunny")

        logger.info(
            f"🌍 [神经环境传感器] 同步 Godot 物理参数 -> 天气: {self.weather}, 温度: {self.ambient_temperature}°C"
        )
        return self.get_environment_report()

    def receive_tactile_pulse(
        self, impact_force: float, direction: str = "none", stroke_freq: float = 0.0
    ):
        """
        接收自 Godot 碰撞引擎产生的具身触觉神经冲动
        :param impact_force: 瞬间碰撞力度 (> 15.0 触发激烈反应)
        :param direction: 碰撞来源方向 ("front", "back", "left", "right", "none")
        :param stroke_freq: 温柔抚摸频率 (0.5 - 2.5 Hz 表示舒适抚摸)
        """
        self.tactile_buffer = {
            "impact_force": impact_force,
            "impact_direction": direction,
            "gentle_stroke": stroke_freq,
        }
        if impact_force > 0.0 or stroke_freq > 0.0:
            logger.info(
                f"✋ [神经触觉总线] 捕获触觉脉冲 -> 碰撞力: {impact_force}, "
                f"方向: {direction}, 抚摸频段: {stroke_freq}Hz"
            )

    def clear_tactile_buffer(self):
        """消费完触觉神经信号后重置清零，避免高频自激"""
        self.tactile_buffer = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 0.0,
        }

    def get_tactile_data(self) -> Dict[str, Any]:
        return self.tactile_buffer

    def get_environment_report(self) -> Dict[str, Any]:
        return {
            "temperature": self.ambient_temperature,
            "gravity": self.gravity,
            "weather": self.weather,
            "is_network_online": True,  # 虚拟世界恒定在线
            "signal_strength": 100,
        }
