import logging
from typing import Dict, Any

logger = logging.getLogger("elfie.brain.energy")

class HypothalamusEnergy:
    """中层：下丘脑 (生理能量与生物钟作息控制)"""

    def __init__(self, limits_config: Dict[str, Any] = None):
        # 默认阈值与参数设定 (防配置文件加载失败 fallback)
        config = limits_config.get("limits", {}) if limits_config else {}
        self.energy_config = config.get("energy", {})
        self.fatigue_config = config.get("fatigue", {})
        
        self.max_energy = self.energy_config.get("max_value", 100.0)
        self.energy = self.energy_config.get("initial_value", 100.0)
        self.depletion_rate = self.energy_config.get("depletion_rate_per_sec", 0.005)
        
        self.max_fatigue = self.fatigue_config.get("max_value", 100.0)
        self.fatigue = self.fatigue_config.get("initial_value", 0.0)
        self.accumulation_rate = self.fatigue_config.get("accumulation_rate_per_sec", 0.003)
        
        self.hibernation_threshold = self.fatigue_config.get("hibernation_threshold", 95.0)
        self.wakeup_threshold = self.fatigue_config.get("wakeup_threshold", 15.0)
        
        self.is_sleeping = False

    def update_clock(self, dt: float):
        """
        生理时钟 Tick 更新
        :param dt: 步长秒数 (由 elfienest 引擎传入)
        """
        if self.is_sleeping:
            # 睡觉状态下恢复体能、消退疲劳 (清空腺苷)
            rec_rate = self.energy_config.get("recovery_rate_sleep_per_sec", 0.05)
            dec_rate = self.fatigue_config.get("decay_rate_sleep_per_sec", 0.04)
            
            self.energy = min(self.energy + rec_rate * dt, self.max_energy)
            self.fatigue = max(self.fatigue - dec_rate * dt, 0.0)
            
            # 疲劳消退至足够低，恢复清醒
            if self.fatigue <= self.wakeup_threshold:
                self.is_sleeping = False
                logger.info(f"☀️ [生理钟唤醒] 疲劳已消退至 {self.fatigue:.1f}%，精灵自然醒来！")
        else:
            # 清醒状态下缓慢自然消耗体能、累积疲劳
            self.energy = max(self.energy - self.depletion_rate * dt, 0.0)
            self.fatigue = min(self.fatigue + self.accumulation_rate * dt, self.max_fatigue)
            
            # 疲劳度过高，触发休眠熔断
            if self.fatigue >= self.hibernation_threshold:
                self.is_sleeping = True
                logger.warning(f"💤 [生理钟休眠熔断] 疲劳度达到临界值 {self.fatigue:.1f}%，精灵强制闭眼休眠！")

    def consume_energy_by_action(self, is_remote: bool):
        """执行大脑思考动作会额外扣减精力"""
        cost = self.energy_config.get("depletion_per_remote_chat", 2.5) if is_remote else \
               self.energy_config.get("depletion_per_local_chat", 0.5)
        self.energy = max(self.energy - cost, 0.0)
        logger.info(f"⚡ [动作耗能] 消耗 {cost} 能量，当前精力剩余: {self.energy:.1f}%")

    def get_energy(self) -> float:
        return self.energy

    def get_fatigue(self) -> float:
        return self.fatigue
