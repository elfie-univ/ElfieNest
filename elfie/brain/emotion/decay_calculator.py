import logging

from elfie.brain.emotion.accumulator.decay import decay
from elfie.brain.emotion.emotion_types import EMOTION_CONFIGS, resolve_emotion_name
from elfie.brain.emotion.emotional_state import AmygdalaEmotionalState

logger = logging.getLogger("elfie.brain.emotion.decay_calculator")


class EmotionDecayCalculator:
    """中层：杏仁核情绪化学衰减计算器 (基于化学半衰期分阶段衰减算法)"""

    def __init__(self, half_life_seconds: float = 300.0):
        # 默认情绪的化学扩散半衰期为 300 秒 (5分钟)
        self.half_life = half_life_seconds
        # 阈值：用于分阶段衰减判断
        self.threshold = 50.0

    def decay_emotions(self, emotion_state: AmygdalaEmotionalState, dt: float):
        """
        根据时间步长 dt 进行情绪分阶段衰减，向各情绪的基准平静状态回落
        使用EMOTION_CONFIGS中定义的baseline和half_life

        :param emotion_state: 待更新的情绪状态机实例
        :param dt: 过去的时间（秒）
        """
        # 遍历emotion_state中的所有情绪
        for emo_name, old_value in list(emotion_state.emotions.items()):
            # 解析情绪名称（向后兼容：将旧名称映射到新名称）
            resolved_name = resolve_emotion_name(emo_name)

            # 获取配置（使用新名称）
            if resolved_name in EMOTION_CONFIGS:
                config = EMOTION_CONFIGS[resolved_name]
                baseline = config["baseline"]
                half_life = config["half_life"]
            else:
                # 如果没有配置，使用默认值
                baseline = 10.0
                half_life = self.half_life

            # 使用新的分阶段衰减函数
            new_value = decay(
                current_value=old_value,
                dt=dt,
                baseline=baseline,
                half_life=half_life,
                threshold=self.threshold,
            )

            # 确保情绪值在有效范围内
            emotion_state.emotions[emo_name] = max(min(new_value, 100.0), 0.0)
