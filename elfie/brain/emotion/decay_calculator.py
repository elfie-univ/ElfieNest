import math
import logging
from elfie.core_systems.emotion.emotional_state import AmygdalaEmotionalState

logger = logging.getLogger("elfie.core_systems.emotion.decay_calculator")

class EmotionDecayCalculator:
    """中层：杏仁核情绪化学衰减计算器 (基于化学半衰期半指数衰减算法)"""

    def __init__(self, half_life_seconds: float = 300.0):
        # 默认情绪的化学扩散半衰期为 300 秒 (5分钟)
        self.half_life = half_life_seconds

    def decay_emotions(self, emotion_state: AmygdalaEmotionalState, dt: float):
        """
        根据时间步长 dt 进行情绪指数级衰减，向基准平静状态回落
        - 快乐的平静基准值为 50.0
        - 焦虑、吃醋、无聊的平静基准值为 10.0
        :param emotion_state: 待更新的情绪状态机实例
        :param dt: 过去的时间（秒）
        """
        # 衰减因子: 2^(-dt / half_life)
        decay_factor = math.pow(0.5, dt / self.half_life)
        
        # 快乐回落至基准 50
        happy_diff = emotion_state.emotions["happiness"] - 50.0
        emotion_state.emotions["happiness"] = 50.0 + happy_diff * decay_factor
        
        # 其它负面/兴奋情绪回落至基准 10.0
        for emo_name in ["anxiety", "jealousy", "boredom"]:
            diff = emotion_state.emotions[emo_name] - 10.0
            emotion_state.emotions[emo_name] = 10.0 + diff * decay_factor
            
            # 确保不出现负数
            if emotion_state.emotions[emo_name] < 0.0:
                emotion_state.emotions[emo_name] = 0.0
                
        # 随时间闲置，如果没有任何外界消息输入，无聊值每秒可缓慢增加 (自然无聊累积)
        # 例如每过一秒自然增加 0.01 的无聊度
        emotion_state.emotions["boredom"] = min(
            emotion_state.emotions["boredom"] + 0.01 * dt, 
            100.0
        )
