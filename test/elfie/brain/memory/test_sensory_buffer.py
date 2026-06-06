"""感知缓冲单元测试

测试 SensoryBuffer 的增删查、过期淘汰、容量限制、筛选巩固等功能。
"""

from datetime import datetime, timedelta

import pytest

from elfie.brain.memory.sensory_buffer import SensoryBuffer


class TestSensoryBuffer:
    """测试感知缓冲区的核心功能"""

    @pytest.fixture
    def buf(self):
        """创建一个容量 10、窗口 1 小时的 SensoryBuffer 实例"""
        sb = SensoryBuffer(max_size=10, window_seconds=3600)
        yield sb

    def test_add_and_query(self, buf):
        """添加事件后可按关键词检索"""
        buf.add("看到一只红色的鸟在树上", emotion="好奇", intensity=60.0)
        buf.add("听到远处传来狗叫声", emotion="警觉", intensity=80.0)
        buf.add("闻到花香很舒服", emotion="平静", intensity=30.0)

        results = buf.query(keywords=["鸟"])
        assert len(results) == 1
        assert "鸟" in results[0]["content"]

        results = buf.query(keywords=["狗"])
        assert len(results) == 1
        assert "狗" in results[0]["content"]

    def test_evict_expired(self, buf):
        """超过时间窗口的事件被清除"""
        # 先写入一个事件，然后把它的时间戳改到 2 小时前
        buf.add("旧的事件", emotion="neutral", intensity=10.0)
        past_time = datetime.now() - timedelta(hours=2)
        buf._buffer[0]["timestamp"] = past_time

        # 再写入一个当前事件
        buf.add("新的事件", emotion="happy", intensity=50.0)

        assert len(buf) == 2

        buf.evict()

        # 过期事件被清除，只剩新事件
        assert len(buf) == 1
        assert buf._buffer[0]["content"] == "新的事件"

    def test_filter_candidates(self, buf):
        """筛选 intensity > threshold 或有 stimulus 的事件"""
        buf.add("低强度无刺激", emotion="平静", intensity=10.0)
        buf.add("高强度", emotion="兴奋", intensity=80.0)
        buf.add("有刺激源", emotion="好奇", intensity=20.0, stimulus="视觉")
        buf.add(
            "高强有刺激",
            emotion="震惊",
            intensity=90.0,
            stimulus="听觉",
            sensory={"auditory": "爆炸声"},
        )

        candidates = buf.filter_candidates(threshold_intensity=30.0)

        # 低强度无刺激不应入选；其他三个都应入选
        assert len(candidates) == 3
        contents = [c["content"] for c in candidates]
        assert "低强度无刺激" not in contents
        assert "高强度" in contents
        assert "有刺激源" in contents
        assert "高强有刺激" in contents

    def test_capacity_limit(self, buf):
        """超过 max_size 时自动淘汰最旧事件"""
        # 填充到容量上限
        for i in range(10):
            buf.add(f"事件{i}", emotion="平静", intensity=5.0)

        assert len(buf) == 10

        # 再添加一个事件，触发淘汰
        buf.add("新事件", emotion="高兴", intensity=50.0)

        # 最旧的事件 "事件0" 应被淘汰
        assert len(buf) == 10
        assert buf._buffer[0]["content"] == "事件1"
        assert buf._buffer[-1]["content"] == "新事件"

    def test_clear(self, buf):
        """清空整个缓冲区"""
        buf.add("事件1", emotion="平静", intensity=10.0)
        buf.add("事件2", emotion="平静", intensity=20.0)
        assert len(buf) == 2

        buf.clear()
        assert len(buf) == 0

    def test_query_empty_buffer(self, buf):
        """空缓冲区查询返回空列表"""
        results = buf.query(keywords=["测试"])
        assert results == []

    def test_query_no_match(self, buf):
        """查询无匹配关键词返回空列表"""
        buf.add("今天天气真好", emotion="平静", intensity=10.0)
        results = buf.query(keywords=["人工智能"])
        assert results == []

    def test_multiple_keywords(self, buf):
        """多关键词查询"""
        buf.add("一只猫在屋顶上", emotion="好奇", intensity=40.0)
        buf.add("狗在公园里奔跑", emotion="开心", intensity=60.0)
        buf.add("猫和狗是好朋友", emotion="温馨", intensity=50.0)
        buf.add("今天天气晴朗", emotion="平静", intensity=20.0)

        # 多关键词查询"猫"和"狗"
        results = buf.query(keywords=["猫", "狗"])

        # 应该返回匹配数最多的（猫和狗都匹配的排第一）
        assert len(results) >= 3  # 至少匹配到这三个

        # 猫和狗都匹配的事件应该排第一
        assert results[0]["content"] == "猫和狗是好朋友"

    def test_add_custom_sensory(self, buf):
        """添加事件时附带自定义感官数据"""
        buf.add(
            "看到红色的花",
            emotion="愉悦",
            intensity=70.0,
            stimulus="视觉",
            sensory={"visual": "红色", "olfactory": "花香"},
        )

        results = buf.query(keywords=["红色"])
        assert len(results) == 1
        assert results[0]["sensory"]["visual"] == "红色"

    def test_len(self, buf):
        """__len__ 返回缓冲区的正确事件数"""
        assert len(buf) == 0
        buf.add("事件1", emotion="平静", intensity=10.0)
        assert len(buf) == 1
        buf.add("事件2", emotion="平静", intensity=20.0)
        assert len(buf) == 2
