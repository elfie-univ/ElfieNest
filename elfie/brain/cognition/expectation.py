import logging
from typing import Any

logger = logging.getLogger("elfie.cognition.expectation")


class ExpectationManager:
    """预期管理系统 (基于预测加工机制 - Predictive Processing)"""

    def __init__(self):
        # 维持的脑中预期世界参数
        self.expected_temperature = 24.0  # 理想舒适温度
        self.expected_user_active = False  # 预期主人在忙别的
        self.prediction_error_threshold = 30.0  # 预期误差阈值，超出该值则强行驱动行为

    def update_and_calculate_error(self, real_sensors: dict[str, Any]) -> float:
        """
        根据现实世界的传感器反馈，对比脑内预期，算出预测误差
        :param real_sensors: 底层传入的真实传感器数值 (如温度、光线、电量、主人消息状态)
        :return: 预测误差百分比 (0.0 - 100.0)
        """
        error_score = 0.0

        # 1. 物理环境温度偏离预期
        real_temp = real_sensors.get("temperature", 24.0)
        temp_diff = abs(real_temp - self.expected_temperature)
        if temp_diff > 2.0:
            error_score += min(temp_diff * 10, 40.0)  # 温度变化最高贡献 40 分

        # 2. 社交活动偏差 (例如主人突然发微信，远远超出了平时没人发信息的预期)
        has_msg = real_sensors.get("has_new_message", False)
        if has_msg != self.expected_user_active:
            error_score += 50.0  # 极大的惊喜/惊吓误差

        # 3. 网络异常断开
        is_online = real_sensors.get("is_network_online", True)
        if not is_online:
            error_score += 35.0  # 断网恐慌误差

        # 更新大脑预测
        self.expected_user_active = has_msg

        if error_score > 0:
            logger.info(
                f"🔮 [预测加工] 现实与大脑脑补预期不符！综合预测误差: {error_score}"
            )

        return error_score

    def should_take_active_action(self, error_score: float) -> bool:
        """预测误差如果大于阈值，说明大脑产生困惑，触发主动“自我表达”"""
        return error_score >= self.prediction_error_threshold
