"""饱和增长累加器 - Saturation Accumulator

情感值累积时使用饱和增长公式，使情感值逐渐趋向最大值但不会无限增长。
公式: delta = base_delta * intensity * accumulate_rate * (1 - value/max_value)
"""


def calculate_accumulation_delta(current_value, base_delta, intensity, config=None, max_value=100.0):
    """计算累积增量
    
    Args:
        current_value: 当前情感值
        base_delta: 基础增量
        intensity: 情感强度 (0.0-1.0)
        config: 配置字典，需包含:
            - accumulate_rate: 累积速率 (可选，默认0.5)
        max_value: 最大值（如果config中有则优先使用config中的）
    
    Returns:
        实际的累积增量
    """
    # 从config读取参数，保持向后兼容
    if config is not None:
        accumulate_rate = config.get('accumulate_rate', 0.5)
        max_value = config.get('max_value', max_value)
    else:
        accumulate_rate = 0.5
    if max_value <= 0:
        return 0.0
    
    saturation = 1.0 - (current_value / max_value)
    saturation = max(0.0, saturation)
    
    delta = base_delta * intensity * accumulate_rate * saturation
    return delta


def accumulate(value, delta, intensity, config):
    """累积情感值（不修改原值，返回新值）
    
    Args:
        value: 当前情感值
        delta: 基础增量
        intensity: 情感强度 (0.0-1.0)
        config: 配置字典，需包含:
            - max_value: 最大值
            - accumulate_rate: 累积速率 (可选，默认0.5)
    
    Returns:
        新的情感值
    """
    max_value = config.get('max_value', 100.0)
    accumulate_rate = config.get('accumulate_rate', 0.5)
    
    actual_delta = calculate_accumulation_delta(
        current_value=value,
        base_delta=delta,
        intensity=intensity,
        config=config,
        max_value=max_value
    )
    
    return value + actual_delta


# 默认配置
DEFAULT_CONFIG = {
    'max_value': 100.0,
    'accumulate_rate': 0.5
}
