"""频率追踪器 - Frequency Tracker

使用滑动时间窗口维护输入频率信息。
用于计算slow_factor（减速因子），当输入频率高时减缓处理速度。

公式:
    slow_factor = 1.0 + recent_count * 0.5

示例:
    0次输入 → slow_factor = 1.0
    5次输入 → slow_factor = 3.5
    10次输入 → slow_factor = 6.0
"""

import time
from collections import deque


class FrequencyTracker:
    """频率追踪器 - 使用时间滑动窗口"""

    def __init__(self, window_size=60.0):
        """初始化频率追踪器

        Args:
            window_size: 时间窗口大小（秒），默认60秒
        """
        self.window_size = window_size
        self.expire_times: deque = deque()  # 存储每个输入的过期时间

    def record_input(self, current_time=None):
        """记录一次输入

        Args:
            current_time: 当前时间戳（秒），默认使用time.time()
        """
        if current_time is None:
            current_time = time.time()

        # 过期时间 = 当前时间 + 窗口大小
        expire_time = current_time + self.window_size
        self.expire_times.append(expire_time)

        # 清理已过期的记录
        self._clean_expired(current_time)

    def _clean_expired(self, current_time):
        """清理已过期的记录

        Args:
            current_time: 当前时间戳
        """
        while self.expire_times and self.expire_times[0] < current_time:
            self.expire_times.popleft()

    def get_recent_count(self, current_time=None):
        """获取最近窗口内的输入次数

        Args:
            current_time: 当前时间戳，默认使用time.time()

        Returns:
            最近窗口内的输入次数
        """
        if current_time is None:
            current_time = time.time()

        self._clean_expired(current_time)
        return len(self.expire_times)

    def get_slow_factor(self, current_time=None, config=None):
        """获取减速因子

        公式: slow_factor = 1.0 + recent_count * coefficient

        Args:
            current_time: 当前时间戳，默认使用time.time()
            config: 配置字典，需包含:
                - frequency_slow_coefficient: 频率减缓系数 (可选，默认0.5)

        Returns:
            减速因子（输入越多，因子越大）
        """
        # 从config读取参数，保持向后兼容
        if config is not None:
            coefficient = config.get("frequency_slow_coefficient", 0.5)
        else:
            coefficient = 0.5

        recent_count = self.get_recent_count(current_time)
        return 1.0 + recent_count * coefficient

    def reset(self):
        """重置所有记录"""
        self.expire_times.clear()


# 默认配置
DEFAULT_CONFIG = {"window_size": 60.0}
