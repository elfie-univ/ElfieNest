import logging

logger = logging.getLogger("elfie.brain.emotion.emotional_state")


class AmygdalaEmotionalState:
    """中层：杏仁核 (实时情绪状态机)"""

    def __init__(self):
        # 初始情绪状态指数 (范围 0.0 - 100.0)
        self.emotions = {
            "happiness": 50.0,  # 快乐
            "anxiety": 10.0,  # 焦虑
            "jealousy": 0.0,  # 吃醋/嫉妒
            "boredom": 20.0,  # 无聊/孤独
        }

    def update_emotion(self, name: str, change_value: float):
        """
        修改指定情绪的数值，并进行边界裁切 (0 - 100)
        :param name: 情绪键名
        :param change_value: 增减变化量 (可正可负)
        """
        if name in self.emotions:
            old_val = self.emotions[name]
            self.emotions[name] = max(
                min(self.emotions[name] + change_value, 100.0), 0.0
            )
            logger.info(
                f"🎭 [情绪微调] {name}: {old_val:.1f} -> {self.emotions[name]:.1f}"
            )
        else:
            logger.warning(f"未知情绪类型: '{name}'")

    def get_dominant_mood(self) -> str:
        """评估主导情绪"""
        # 如果焦虑和吃醋极高，优先体现情绪不佳
        if self.emotions["jealousy"] > 50.0:
            return "jealous"
        if self.emotions["anxiety"] > 60.0:
            return "anxious"
        if self.emotions["boredom"] > 60.0:
            return "bored"
        if self.emotions["happiness"] > 60.0:
            return "happy"
        return "calm"

    def get_current_emotion_summary(self) -> str:
        """格式化输出当前情绪特征"""
        summary = (
            f"快乐值:{self.emotions['happiness']:.1f}/100, "
            f"焦虑值:{self.emotions['anxiety']:.1f}/100, "
            f"吃醋度:{self.emotions['jealousy']:.1f}/100, "
            f"无聊度:{self.emotions['boredom']:.1f}/100"
        )
        return summary
