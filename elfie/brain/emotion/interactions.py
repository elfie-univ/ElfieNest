"""
情绪交互系统 (Emotion Interaction System)

实现情绪之间的相互影响：
- Transfer (转移): 当source情绪超过阈值时，部分转移到target
- Inhibition (抑制): source情绪抑制target情绪的增长
- Enhancement (增强): source情绪增强target情绪的增长
"""

from typing import Any

from elfie.brain.emotion.emotion_types import EMOTION_INTERACTIONS


def apply_transfer(
    emotions: dict[str, float], source: str, target: str, config: dict
) -> float:
    """
    应用转移交互。

    当source情绪超过threshold时，超过部分的rate比例转移到target。

    Args:
        emotions: 当前情绪字典
        source: 源情绪名称
        target: 目标情绪名称
        config: 交互配置，包含threshold和rate

    Returns:
        转移的量
    """
    source_val = emotions.get(source, 0)
    threshold = config["threshold"]
    rate = config["rate"]

    if source_val > threshold:
        # 计算转移量
        transfer_amount = (source_val - threshold) * rate
        # 从source减少
        emotions[source] = source_val - transfer_amount
        # 向target增加
        target_val = emotions.get(target, 0)
        emotions[target] = target_val + transfer_amount
        return transfer_amount

    return 0.0


def get_inhibition_modifier(
    emotions: dict[str, float], source: str, rate: float, max_value: float = 100.0
) -> float:
    """
    计算抑制系数。

    source情绪存在时，target情绪的增长降低。

    Args:
        emotions: 当前情绪字典
        source: 源情绪名称（抑制者）
        rate: 抑制率
        max_value: 情绪最大值

    Returns:
        抑制系数 (0.1 ~ 1.0)
    """
    source_val = emotions.get(source, 0)
    modifier = 1.0 - (rate * source_val / max_value)
    # 至少保留10%
    return max(0.1, modifier)


def get_enhancement_modifier(
    emotions: dict[str, float], source: str, rate: float, max_value: float = 100.0
) -> float:
    """
    计算增强系数。

    source情绪存在时，target情绪的增长增强。

    Args:
        emotions: 当前情绪字典
        source: 源情绪名称（增强者）
        rate: 增强率
        max_value: 情绪最大值

    Returns:
        增强系数 (>= 1.0)
    """
    source_val = emotions.get(source, 0)
    modifier = 1.0 + (rate * source_val / max_value)
    return modifier


class EmotionInteractionSystem:
    """
    情绪交互系统。

    负责处理情绪之间的相互影响：
    - 转移交互 (Transfer): 在tick时应用
    - 抑制/增强交互 (Inhibition/Enhancement): 在accumulate时应用

    示例:
        >>> system = EmotionInteractionSystem()
        >>> emotions = {'fear': 80, 'anger': 10, 'happiness': 60}
        >>>
        >>> # tick时应用转移
        >>> system.apply_transfer_interactions(emotions)
        >>>
        >>> # accumulate时获取调节系数
        >>> modifier = system.get_accumulate_modifier('anger', emotions)
    """

    def __init__(
        self, interactions: dict[tuple[str, str], dict[str, Any]] | None = None
    ):
        """
        初始化情绪交互系统。

        Args:
            interactions: 交互配置字典，默认使用EMOTION_INTERACTIONS
        """
        self.interactions = (
            interactions if interactions is not None else EMOTION_INTERACTIONS
        )

    def apply_transfer_interactions(
        self, emotions: dict[str, float]
    ) -> dict[tuple[str, str], float]:
        """
        应用所有转移交互（在tick中调用）。

        遍历所有transfer类型的交互，将超过阈值的情绪量转移到目标情绪。

        Args:
            emotions: 当前情绪字典（会被修改）

        Returns:
            转移量字典 {(source, target): amount}
        """
        results = {}

        for (source, target), config in self.interactions.items():
            if config["type"] == "transfer":
                amount = apply_transfer(emotions, source, target, config)
                if amount > 0:
                    results[(source, target)] = amount

        return results

    def get_accumulate_modifier(
        self, target_emotion: str, emotions: dict[str, float], max_value: float = 100.0
    ) -> float:
        """
        获取目标情绪的累积调节系数（在accumulate中调用）。

        遍历所有影响target_emotion的交互，累乘所有抑制/增强系数。

        Args:
            target_emotion: 目标情绪名称
            emotions: 当前情绪字典
            max_value: 情绪最大值

        Returns:
            累积调节系数
        """
        modifier = 1.0

        for (source, target), config in self.interactions.items():
            if target != target_emotion:
                continue

            if config["type"] == "inhibition":
                # 抑制：source存在时，target增长降低
                rate = config["rate"]
                source_modifier = get_inhibition_modifier(
                    emotions, source, rate, max_value
                )
                modifier *= source_modifier

            elif config["type"] == "enhancement":
                # 增强：source存在时，target增长提高
                rate = config["rate"]
                source_modifier = get_enhancement_modifier(
                    emotions, source, rate, max_value
                )
                modifier *= source_modifier

        return modifier

    def get_interaction_info(self, source: str, target: str) -> dict[str, Any] | None:
        """
        获取两个情绪之间的交互信息。

        Args:
            source: 源情绪名称
            target: 目标情绪名称

        Returns:
            交互配置字典，如果不存在则返回None
        """
        return self.interactions.get((source, target))
