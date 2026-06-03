from enum import Enum


class EmotionType(Enum):
    HAPPINESS = "happiness"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    BOREDOM = "boredom"
    ATTACHMENT = "attachment"


# 旧情绪名称到新情绪的迁移映射（向后兼容）
# anxiety → fear: 焦虑与恐惧在情绪谱上接近，都属于负面唤醒情绪
# jealousy → attachment: 吃醋/嫉妒是依恋情绪的一种表现，源于占有欲
EMOTION_ALIASES = {
    "anxiety": "fear",
    "jealousy": "attachment",
}


def resolve_emotion_name(name: str) -> str:
    """
    将旧情绪名称解析为新情绪名称。

    Args:
        name: 情绪名称（旧名称或新名称）

    Returns:
        解析后的标准情绪名称

    Example:
        >>> resolve_emotion_name('anxiety')
        'fear'
        >>> resolve_emotion_name('fear')
        'fear'
    """
    return EMOTION_ALIASES.get(name, name)


# 迁移策略文档：
# 1. 旧代码使用 update_emotion('anxiety', 10) 会自动映射到 fear
# 2. 旧代码使用 update_emotion('jealousy', 10) 会自动映射到 attachment
# 3. 新情绪名称（happiness, sadness, anger, fear, surprise, disgust, boredom, attachment）直接使用
# 4. 通过 resolve_emotion_name() 函数确保向后兼容

# 情绪配置说明：
# - base_delta: 基础增量（用于饱和增长公式）
# - baseline: 基线值（衰减到该值）
# - half_life: 基础半衰期（秒）
# - max_value: 最大值（通常100）
# - accumulate_rate: 累积速率（默认0.5）
# - decay_high_multiplier: 高值区衰减倍数（默认0.3，值越高衰减越快）
# - decay_low_multiplier: 低值区衰减倍数（默认3.0，值越低衰减越慢）
# - decay_threshold: 高低值区分界线（默认50.0）
# - frequency_slow_coefficient: 频率慢化系数（默认0.5）

EMOTION_CONFIGS = {
    "happiness": {
        "base_delta": 20,
        "baseline": 50,
        "half_life": 300,
        "max_value": 100,
        "accumulate_rate": 0.5,
        "decay_high_multiplier": 0.3,
        "decay_low_multiplier": 3.0,
        "decay_threshold": 50.0,
        "frequency_slow_coefficient": 0.5,
    },
    "sadness": {
        "base_delta": 20,
        "baseline": 10,
        "half_life": 300,
        "max_value": 100,
        "accumulate_rate": 0.5,
        "decay_high_multiplier": 0.3,
        "decay_low_multiplier": 3.0,
        "decay_threshold": 50.0,
        "frequency_slow_coefficient": 0.5,
    },
    "anger": {
        "base_delta": 30,
        "baseline": 10,
        "half_life": 180,
        "max_value": 100,
        "accumulate_rate": 0.5,
        "decay_high_multiplier": 0.3,
        "decay_low_multiplier": 3.0,
        "decay_threshold": 50.0,
        "frequency_slow_coefficient": 0.5,
    },
    "fear": {
        "base_delta": 40,
        "baseline": 10,
        "half_life": 180,
        "max_value": 100,
        "accumulate_rate": 0.5,
        "decay_high_multiplier": 0.3,
        "decay_low_multiplier": 3.0,
        "decay_threshold": 50.0,
        "frequency_slow_coefficient": 0.5,
    },
    "surprise": {
        "base_delta": 25,
        "baseline": 10,
        "half_life": 120,
        "max_value": 100,
        "accumulate_rate": 0.5,
        "decay_high_multiplier": 0.3,
        "decay_low_multiplier": 3.0,
        "decay_threshold": 50.0,
        "frequency_slow_coefficient": 0.5,
    },
    "disgust": {
        "base_delta": 15,
        "baseline": 10,
        "half_life": 300,
        "max_value": 100,
        "accumulate_rate": 0.5,
        "decay_high_multiplier": 0.3,
        "decay_low_multiplier": 3.0,
        "decay_threshold": 50.0,
        "frequency_slow_coefficient": 0.5,
    },
    "boredom": {
        "base_delta": 5,
        "baseline": 20,
        "half_life": 600,
        "max_value": 100,
        "accumulate_rate": 0.5,
        "decay_high_multiplier": 0.3,
        "decay_low_multiplier": 3.0,
        "decay_threshold": 50.0,
        "frequency_slow_coefficient": 0.5,
    },
    "attachment": {
        "base_delta": 15,
        "baseline": 30,
        "half_life": 400,
        "max_value": 100,
        "accumulate_rate": 0.5,
        "decay_high_multiplier": 0.3,
        "decay_low_multiplier": 3.0,
        "decay_threshold": 50.0,
        "frequency_slow_coefficient": 0.5,
    },
}


# 情绪交互配置
# 定义情绪之间的相互影响关系
#
# 交互类型说明：
# - transfer: 转移，当source情绪超过threshold时，rate比例转移到target
# - inhibition: 抑制，source情绪抑制target情绪的增长
# - enhancement: 增强，source情绪增强target情绪的增长
#
# 示例：
# - 恐惧(fear)过高时转化为愤怒(anger)（自卫本能）
# - 快乐(happiness)抑制愤怒(anger)（情绪缓冲）
# - 悲伤(sadness)增强依恋(attachment)（寻求安慰）
EMOTION_INTERACTIONS = {
    # 转移：恐惧 → 愤怒（自卫本能）
    # 当fear超过70时，超过部分的10%转移到anger
    ("fear", "anger"): {
        "type": "transfer",
        "threshold": 70,
        "rate": 0.1,
    },
    # 抑制：快乐 → 愤怒（情绪缓冲）
    # happiness存在时，anger的增长降低30%
    ("happiness", "anger"): {
        "type": "inhibition",
        "rate": 0.3,
    },
    # 增强：悲伤 → 依恋（寻求安慰）
    # sadness存在时，attachment的增长增强20%
    ("sadness", "attachment"): {
        "type": "enhancement",
        "rate": 0.2,
    },
}
