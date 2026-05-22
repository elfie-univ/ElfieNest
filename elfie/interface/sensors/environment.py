import logging
import random
from typing import Dict, Any

logger = logging.getLogger("elfie.interface.sensors.environment")

class EnvironmentSensor:
    """底层：感官输入 - 皮肤与系统 (物理环境状态传感器)"""

    def __init__(self):
        self.temperature = 24.5 # 初始温度
        self.wifi_online = True

    def poll_environment(self) -> Dict[str, Any]:
        """
        采样当前的物理系统指标 (每隔一段时间由主 Tick 驱动)
        :return: 包含温度、网络连接、系统负荷的采样元组
        """
        # 模拟物理指标轻微浮动
        self.temperature += random.uniform(-0.1, 0.1)
        
        # 99% 概率网络在线，模拟 1% 的断网偶发，供 expectation 进行预测误差测试
        self.wifi_online = random.random() < 0.99
        
        stats = {
            "temperature": round(self.temperature, 2),
            "is_network_online": self.wifi_online,
            "signal_strength": 90 if self.wifi_online else 0,
            "battery_level": 98.5
        }
        
        return stats
