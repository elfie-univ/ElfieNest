"""分阶段衰减计算器 - Staged Decay Calculator

情感值分阶段衰减：高值区快速衰减，低值区慢速衰减。
公式:
    高值区 (value > threshold): 半衰期 = base_half_life × 0.3
    低值区 (value ≤ threshold): 半衰期 = base_half_life × 3.0

    decay_factor = 0.5 ^ (dt / effective_half_life)
    new_value = baseline + (value - baseline) × decay_factor
"""


def decay(
    current_value, dt, config=None, baseline=0.0, half_life=100.0, threshold=50.0
):
    """分阶段衰减计算

    Args:
        current_value: 当前情感值
        dt: 时间增量（秒）
        config: 配置字典，需包含:
            - decay_high_multiplier: 高值区衰减乘数 (可选，默认0.3)
            - decay_low_multiplier: 低值区衰减乘数 (可选，默认3.0)
            - decay_threshold: 高值区分界线 (可选，默认50.0)
        baseline: 基线值（默认0.0）
        half_life: 基础半衰期（默认100.0秒）
        threshold: 高值区分界线（默认50.0）

    Returns:
        衰减后的新值
    """
    # 从config读取参数，保持向后兼容
    if config is not None:
        high_multiplier = config.get("decay_high_multiplier", 0.3)
        low_multiplier = config.get("decay_low_multiplier", 3.0)
        threshold = config.get("decay_threshold", threshold)
    else:
        high_multiplier = 0.3
        low_multiplier = 3.0

    # 分阶段计算实际半衰期
    if current_value > threshold:
        effective_half_life = half_life * high_multiplier
    else:
        effective_half_life = half_life * low_multiplier

    # 指数衰减公式
    decay_factor = 0.5 ** (dt / effective_half_life)
    diff = current_value - baseline
    new_value = baseline + diff * decay_factor

    return new_value


# 默认配置
DEFAULT_CONFIG = {"baseline": 0.0, "half_life": 100.0, "threshold": 50.0}
