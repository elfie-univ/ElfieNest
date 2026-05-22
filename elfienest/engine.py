import time
import logging
from typing import Dict, Any

from elfienest.world import ElfieNestWorld
from elfienest.coordinator import ElfieNestCoordinator

logger = logging.getLogger("elfienest.engine")

class ElfieNestEngine:
    """精灵盒子主运行引擎 (生态容器 Tick 生命周期调度器)"""

    def __init__(self):
        self.world = ElfieNestWorld()
        self.coordinator = ElfieNestCoordinator()
        self.running = False

    def start_loop(self, runtime_agent: Any, ticks_to_run: int = 3, interval_sec: float = 1.0):
        """
        开启盒子环境仿真循环
        :param runtime_agent: 大模型底座运行时 RuntimeAgent 实例
        :param ticks_to_run: 本次测试运行多少个 Tick 周期 (避免死循环阻塞)
        :param interval_sec: 每个 Tick 之间的真实世界睡眠秒数
        """
        logger.info("🎬 [精灵盒子引擎] 物理世界启动，生态容器进入 Tick 循环...")
        self.running = True
        
        # 设定虚拟世界时间尺度，假设每个 Tick 过去 30 秒以加速小精灵情绪和生理代谢
        virtual_dt = 30.0 
        
        for step in range(ticks_to_run):
            if not self.running:
                break
                
            logger.info(f"\n================ 🌀 世界 Tick #{step + 1} 周期 ================")
            
            # 1. 物理环境 Tick 更新
            world_state = self.world.update_world_physics(virtual_dt)
            logger.info(f"🌍 [世界物理参数] 当前天气: {world_state['weather']}, 温度: {world_state['temperature']}°C")
            
            # 2. 驱动每只注册精灵进行体内新陈代谢 (能量消耗、情绪半衰期指数衰退)
            for name, elfie in self.coordinator.registered_elfies.items():
                # 生理 Tick
                elfie.tick(virtual_dt)
                logger.info(
                    f"🧬 [{name} 生理指标] 精力: {elfie.hypothalamus.get_energy():.1f}%, "
                    f"疲劳度: {elfie.hypothalamus.get_fatigue():.1f}%, "
                    f"情绪概要: {elfie.amygdala.get_current_emotion_summary()}"
                )
                
                # 3. 模拟环境感官输入采样 (传感器捕获 -> 输入皮层决策)
                sensor_data = {
                    "temperature": world_state["temperature"],
                    "is_network_online": True,
                    "salience_score": 10.0, # 正常白噪音
                    "has_new_message": False,
                    "user_message": ""
                }
                
                # 随机触发：第二周期主人发了条日常微信
                if step == 1:
                    sensor_data["has_new_message"] = True
                    sensor_data["user_message"] = "艾菲你好呀！帮我算一下 1250 元打九折再加 50 元邮费是多少钱哒？"
                    
                # 驱动小精灵感官反射大脑回路 (percive_and_respond)
                response = elfie.perceive_and_respond(sensor_data, runtime_agent)
                
                if response.get("filtered"):
                    logger.info(f"Dam Filter: {name} 大脑感知过滤了多余的无趣白噪音信号。")
                elif response.get("success"):
                    if response.get("speech"):
                        logger.info(f"💬 [{name} 回应主人]: \"{response['speech']}\"")
                    if response.get("action"):
                        logger.info(f"🐾 [{name} 躯体反应]: 电机运行 -> {response['action']}")
                    if response.get("mutter"):
                        logger.info(f"💭 [{name} 自言碎语]: {response['mutter']}")
            
            time.sleep(interval_sec)
            
        self.running = False
        logger.info("🎬 [精灵盒子引擎] 物理世界挂起，Tick 循环圆满结束。")
