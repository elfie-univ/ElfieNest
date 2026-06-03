import logging
from typing import Any

logger = logging.getLogger("elfie.interface.signal_filter")


class SensoryDamSignalFilter:
    """底层：感知大坝 (信号过滤器，拦截背景白噪声与重复噪点以节省 Token 与体能)"""

    def __init__(self):
        self.last_temperature = None
        self.last_user_message = ""

    def filter_noise(self, raw_sensors: dict[str, Any]) -> bool:
        """
        判断传感器捕获到的信号是否是无价值背景噪音，是否应该过滤掉
        :param raw_sensors: 瞬时裸感官数据
        :return: True 表示有变化、值得上报；False 表示没有变化、过滤阻断
        """
        has_change = False

        # 1. 检查主人有没有发新消息 (强行放行，绝不可漏掉任何微信消息！)
        if raw_sensors.get("has_new_message", False):
            msg = raw_sensors.get("user_message", "")
            if msg != self.last_user_message:
                self.last_user_message = msg
                has_change = True

        # 2. 检查温度是否有大幅浮动 (变化 > 0.5°C 允许放行)
        temp = raw_sensors.get("temperature", 24.0)
        if self.last_temperature is None:
            self.last_temperature = temp
            has_change = True
        elif abs(temp - self.last_temperature) >= 0.5:
            logger.info(
                f"皮肤感知：物理温度由 {self.last_temperature}°C 变为 {temp}°C，引起丘脑注意！"
            )
            self.last_temperature = temp
            has_change = True

        # 如果无任何有用变化，阻断过滤
        if not has_change:
            # logger.debug("感知大坝过滤：无任何显式物理状态变化，拦截无效背景噪点。")
            pass

        return has_change
