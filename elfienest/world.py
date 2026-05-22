import logging
import random
from typing import Dict, Any

logger = logging.getLogger("elfienest.world")

class ElfieNestWorld:
    """精灵盒子生态世界环境 (World Physical States)"""

    def __init__(self):
        self.gravity = 9.8            # 基础物理重力加速度
        self.time_dilation = 1.0       # 虚拟与现实的时间流速倍率 (1.0表示同步，10.0表示盒子内世界时间飞逝)
        self.weather = "sunny"         # 盒子内虚拟天气: sunny, rainy, snowy, windy
        self.ambient_temperature = 22.0 # 盒子环境初始温度 (摄氏度)
        self.public_energy_station = {
            "x": 100.0, "y": 0.0, "z": 50.0,
            "charge_rate_per_sec": 10.0 # 能量充电站坐标与速率
        }

    def update_world_physics(self, dt: float) -> Dict[str, Any]:
        """
        更新环境状态机
        :param dt: 本次 Tick 的真实物理间隔秒数
        """
        # 温度受天气影响发生细微物理起伏
        temp_drift = random.uniform(-0.05, 0.05)
        if self.weather == "sunny":
            self.ambient_temperature = min(self.ambient_temperature + temp_drift + 0.01, 35.0)
        elif self.weather == "rainy":
            self.ambient_temperature = max(self.ambient_temperature + temp_drift - 0.02, 10.0)

        # 0.5% 概率世界天气骤变
        if random.random() < 0.005:
            weathers = ["sunny", "rainy", "windy", "snowy"]
            old_w = self.weather
            self.weather = random.choice(weathers)
            logger.info(f"⛅ [世界物理引擎] 天气变幻！由 '{old_w}' 变为 '{self.weather}'。")

        return self.get_world_state()

    def get_world_state(self) -> Dict[str, Any]:
        return {
            "weather": self.weather,
            "temperature": round(self.ambient_temperature, 2),
            "gravity": self.gravity,
            "energy_station_location": self.public_energy_station
        }
