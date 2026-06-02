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

EMOTION_CONFIGS = {
    "happiness": {
        "base_delta": 20,
        "baseline": 50,
        "half_life": 300,
        "max_value": 100,
    },
    "sadness": {
        "base_delta": 20,
        "baseline": 10,
        "half_life": 300,
        "max_value": 100,
    },
    "anger": {
        "base_delta": 30,
        "baseline": 10,
        "half_life": 180,
        "max_value": 100,
    },
    "fear": {
        "base_delta": 40,
        "baseline": 10,
        "half_life": 180,
        "max_value": 100,
    },
    "surprise": {
        "base_delta": 25,
        "baseline": 10,
        "half_life": 120,
        "max_value": 100,
    },
    "disgust": {
        "base_delta": 15,
        "baseline": 10,
        "half_life": 300,
        "max_value": 100,
    },
    "boredom": {
        "base_delta": 5,
        "baseline": 20,
        "half_life": 600,
        "max_value": 100,
    },
    "attachment": {
        "base_delta": 15,
        "baseline": 30,
        "half_life": 400,
        "max_value": 100,
    },
}
