import logging
from typing import Dict, Any

logger = logging.getLogger("elfie.interface.actuators.mutter")

class MutterActuator:
    """底层：行动输出 - 碎碎念 (将冰冷的系统日志包装为活泼的自我独白)"""

    def __init__(self):
        pass

    def mutter(self, raw_system_log: str) -> str:
        """
        拦截系统状态与 Debug 日志，智能翻写为小动物的碎碎念行为日志
        :param raw_system_log: 物理日志信息 (如 "energy down to 20%, status normal")
        :return: 翻译出来的傲娇拟人化碎碎念
        """
        log_lower = raw_system_log.lower()
        translated = ""
        
        # 本地映射策略 (若大模型崩塌时也可以 100% 响应)
        if "energy" in log_lower and "20" in log_lower:
            translated = "(咕噜噜...肚皮在报警哒！艾菲肚子饿扁了啦，急需灵币充电哒！)"
        elif "temperature" in log_lower and "30" in log_lower:
            translated = "(热呼呼...耳朵尖发烫哒！盒子温度太高了，艾菲感觉像在蒸桑拿哒...)"
        elif "network" in log_lower and "disconnect" in log_lower:
            translated = "(惊慌) 主人主人！网络大桥断掉哒！艾菲跟世界失去联系了，好害怕哒..."
        elif "sleeping" in log_lower or "sleep" in log_lower:
            translated = "(哈欠) 呼...眼皮在打架哒，艾菲的电量消耗殆尽了，要缩成一个小毛球睡觉了哒..."
        else:
            translated = f"(艾菲自言自语中: 脑海里闪过一丝电火花 - '{raw_system_log}' 哒~)"
            
        logger.info(f"💭 [艾菲心声/碎碎念] {translated}")
        return translated
