"""情绪系统单元测试 - Emotion System Unit Tests

测试覆盖：
- 初始化
- 旧API (update_emotion)
- 新API (process_input)
- 别名映射
- 去重
- 频率慢化
- 时间衰减
- 主导情绪
- 饱和增长
"""

import os
import sys

import pytest

# 直接添加项目根目录到sys.path，避免通过elfie/__init__.py触发依赖链
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 直接从具体模块导入，避免elfie/__init__.py中的Elfie导入问题
from elfie.brain.emotion.emotion_input import EmotionInput
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.emotion.emotion_types import EMOTION_CONFIGS


class TestEmotionSystem:
    """EmotionSystem核心功能测试"""

    def test_init(self):
        """测试初始化 - 验证8种情绪正确初始化为baseline值"""
        es = EmotionSystem()
        assert len(es.emotions) == 8
        for name, config in EMOTION_CONFIGS.items():
            assert es.emotions[name] == config["baseline"]

    def test_update_emotion_old_api(self):
        """测试旧API（向后兼容）- update_emotion直接修改情绪值"""
        es = EmotionSystem()
        # fear的baseline是10
        es.update_emotion("fear", 20)
        assert es.emotions["fear"] == 30  # baseline 10 + 20

    def test_update_emotion_alias(self):
        """测试别名映射（anxiety -> fear）- 旧情绪名称自动映射"""
        es = EmotionSystem()
        es.update_emotion("anxiety", 20)  # 旧名称
        assert es.emotions["fear"] == 30  # 映射到fear

    def test_update_emotion_jealousy_alias(self):
        """测试jealousy别名映射（jealousy -> attachment）"""
        es = EmotionSystem()
        # attachment的baseline是30
        es.update_emotion("jealousy", 15)
        assert es.emotions["attachment"] == 45  # baseline 30 + 15

    def test_update_emotion_bounds(self):
        """测试情绪值边界裁切（0-100）"""
        es = EmotionSystem()
        # 测试上限
        es.update_emotion("happiness", 200)
        assert es.emotions["happiness"] == 100  # 裁切到100

        # 测试下限
        es.update_emotion("happiness", -150)
        assert es.emotions["happiness"] == 0  # 裁切到0

    def test_process_input(self):
        """测试新API - process_input处理情绪输入"""
        es = EmotionSystem()
        # happiness的baseline是50
        inp = EmotionInput("happiness", 0.8, "text", "event_001")
        es.process_input(inp)
        assert es.emotions["happiness"] > 50  # 应该增加

    def test_process_input_with_metadata(self):
        """测试带metadata的情绪输入"""
        es = EmotionSystem()
        inp = EmotionInput(
            emotion="surprise",
            intensity=0.5,
            source="audio",
            event_id="event_002",
            metadata={"volume": 0.8, "pitch": "high"},
        )
        es.process_input(inp)
        # surprise的baseline是10
        assert es.emotions["surprise"] > 10

    def test_deduplication(self):
        """测试去重 - 相同event_id的输入应该被忽略"""
        es = EmotionSystem()
        inp1 = EmotionInput("fear", 0.8, "text", "event_001")
        inp2 = EmotionInput("fear", 0.9, "text", "event_001")  # 相同event_id
        es.process_input(inp1)
        val1 = es.emotions["fear"]
        es.process_input(inp2)  # 应该被去重
        assert es.emotions["fear"] == val1  # 值不变

    def test_deduplication_different_events(self):
        """测试不同event_id不会被去重"""
        es = EmotionSystem()
        inp1 = EmotionInput("fear", 0.8, "text", "event_001")
        inp2 = EmotionInput("fear", 0.8, "text", "event_002")  # 不同event_id
        es.process_input(inp1)
        val1 = es.emotions["fear"]
        es.process_input(inp2)  # 不应该被去重
        assert es.emotions["fear"] > val1  # 值应该增加

    def test_frequency_slowdown(self):
        """测试频率慢化 - 高频输入时增长变慢"""
        es = EmotionSystem()
        # 多次输入同一情绪
        for i in range(5):
            inp = EmotionInput("fear", 1.0, "text", f"event_{i}")
            es.process_input(inp)
        # 频率高，增长应该变慢
        assert es.frequency_trackers["fear"].get_recent_count() == 5

    def test_frequency_slow_factor_calculation(self):
        """测试slow_factor计算公式: 1.0 + recent_count * 0.5"""
        es = EmotionSystem()
        # 输入3次
        for i in range(3):
            inp = EmotionInput("anger", 0.5, "text", f"event_{i}")
            es.process_input(inp)
        # slow_factor = 1.0 + 3 * 0.5 = 2.5
        slow_factor = es.frequency_trackers["anger"].get_slow_factor()
        assert slow_factor == 2.5

    def test_tick_decay(self):
        """测试时间衰减 - 情绪值应该随时间衰减到baseline"""
        es = EmotionSystem()
        es.update_emotion("fear", 50)  # 设为较高值: 10 + 50 = 60
        old_val = es.emotions["fear"]
        es.tick(60)  # 60秒
        assert es.emotions["fear"] < old_val  # 应该衰减

    def test_tick_decay_to_baseline(self):
        """测试衰减趋向baseline - 长时间衰减后接近baseline"""
        es = EmotionSystem()
        es.update_emotion("happiness", 40)  # 设为90 (baseline 50 + 40)
        # 多次tick模拟长时间
        for _ in range(10):
            es.tick(60)
        # 应该衰减接近baseline (50)
        assert es.emotions["happiness"] < 70
        assert es.emotions["happiness"] > 40  # 但不会低于baseline太多

    def test_tick_decay_below_baseline(self):
        """测试低于baseline的情绪值衰减 - 应该向baseline回升"""
        es = EmotionSystem()
        # happiness baseline是50
        es.emotions["happiness"] = 20  # 设为低于baseline
        es.tick(60)
        # 应该向baseline回升
        assert es.emotions["happiness"] > 20

    def test_get_dominant_mood(self):
        """测试主导情绪 - 返回当前值最高的情绪"""
        es = EmotionSystem()
        es.update_emotion("fear", 80)  # fear = 90
        assert es.get_dominant_mood() == "fear"

    def test_get_dominant_mood_default(self):
        """测试默认主导情绪 - 初始状态下"""
        es = EmotionSystem()
        # happiness baseline是50，是最高的
        assert es.get_dominant_mood() == "happiness"

    def test_saturation(self):
        """测试饱和增长 - 高值时增长变慢"""
        es = EmotionSystem()
        es.emotions["happiness"] = 90  # 设为高值
        inp = EmotionInput("happiness", 1.0, "text", "event_001")
        es.process_input(inp)
        # 高值时增长应该很少（饱和）
        assert es.emotions["happiness"] < 95

    def test_saturation_low_value(self):
        """测试低值时增长较快"""
        es = EmotionSystem()
        es.emotions["happiness"] = 10
        inp = EmotionInput("happiness", 1.0, "text", "event_001")
        es.process_input(inp)
        assert es.emotions["happiness"] > 10

    def test_get_emotion_summary(self):
        """测试情绪摘要输出"""
        es = EmotionSystem()
        summary = es.get_emotion_summary()
        assert isinstance(summary, str)
        assert "happiness" in summary
        assert "sadness" in summary

    def test_get_emotion_value(self):
        """测试获取指定情绪值"""
        es = EmotionSystem()
        es.update_emotion("anger", 30)
        assert es.get_emotion_value("anger") == 40  # baseline 10 + 30

    def test_get_emotion_value_alias(self):
        """测试通过别名获取情绪值"""
        es = EmotionSystem()
        es.update_emotion("anxiety", 25)
        # anxiety映射到fear
        assert es.get_emotion_value("anxiety") == es.get_emotion_value("fear")

    def test_invalid_emotion_name(self):
        """测试无效情绪名称 - 应该被忽略"""
        es = EmotionSystem()
        old_happiness = es.emotions["happiness"]
        es.update_emotion("invalid_emotion", 50)
        # 不应该有任何变化
        assert es.emotions["happiness"] == old_happiness

    def test_invalid_intensity(self):
        """测试无效强度值 - 应该被忽略"""
        es = EmotionSystem()
        old_fear = es.emotions["fear"]
        # intensity超出范围 [0, 1]
        inp = EmotionInput("fear", 1.5, "text", "event_001")
        es.process_input(inp)
        # 验证失败，不应该更新
        assert es.emotions["fear"] == old_fear

    def test_invalid_source(self):
        """测试无效来源 - 应该被忽略"""
        es = EmotionSystem()
        old_fear = es.emotions["fear"]
        # source不在有效集合中
        inp = EmotionInput("fear", 0.8, "invalid_source", "event_001")
        es.process_input(inp)
        # 验证失败，不应该更新
        assert es.emotions["fear"] == old_fear

    def test_multiple_emotions(self):
        """测试同时处理多种情绪"""
        es = EmotionSystem()
        es.process_input(EmotionInput("happiness", 0.7, "text", "e1"))
        es.process_input(EmotionInput("sadness", 0.5, "text", "e2"))
        es.process_input(EmotionInput("anger", 0.3, "text", "e3"))

        # 所有情绪都应该更新
        assert es.emotions["happiness"] > 50
        assert es.emotions["sadness"] > 10
        assert es.emotions["anger"] > 10

    def test_emotion_configs_complete(self):
        """测试所有情绪都有完整配置"""
        required_keys = ["base_delta", "baseline", "half_life", "max_value"]
        for emotion, config in EMOTION_CONFIGS.items():
            for key in required_keys:
                assert key in config, f"{emotion} missing {key}"

    def test_frequency_tracker_reset(self):
        """测试频率追踪器重置"""
        es = EmotionSystem()
        for i in range(5):
            inp = EmotionInput("boredom", 0.5, "text", f"event_{i}")
            es.process_input(inp)

        assert es.frequency_trackers["boredom"].get_recent_count() == 5

        # 重置
        es.frequency_trackers["boredom"].reset()
        assert es.frequency_trackers["boredom"].get_recent_count() == 0


class TestEmotionInput:
    """EmotionInput数据结构测试"""

    def test_valid_input(self):
        """测试有效输入"""
        inp = EmotionInput("happiness", 0.5, "text", "event_001")
        assert inp.validate() is True

    def test_invalid_intensity_high(self):
        """测试强度超出上限"""
        inp = EmotionInput("happiness", 1.5, "text", "event_001")
        assert inp.validate() is False

    def test_invalid_intensity_low(self):
        """测试强度低于下限"""
        inp = EmotionInput("happiness", -0.1, "text", "event_001")
        assert inp.validate() is False

    def test_invalid_source(self):
        """测试无效来源"""
        inp = EmotionInput("happiness", 0.5, "invalid", "event_001")
        assert inp.validate() is False

    def test_valid_sources(self):
        """测试所有有效来源"""
        valid_sources = ["text", "image", "audio", "physical", "brain"]
        for source in valid_sources:
            inp = EmotionInput("happiness", 0.5, source, f"event_{source}")
            assert inp.validate() is True

    def test_timestamp_auto_generated(self):
        """测试时间戳自动生成"""
        import time

        before = time.time()
        inp = EmotionInput("happiness", 0.5, "text", "event_001")
        after = time.time()
        assert before <= inp.timestamp <= after


class TestBackwardCompatibility:
    """向后兼容性测试"""

    def test_old_api_still_works(self):
        """测试旧API仍然可用"""
        es = EmotionSystem()
        # 旧代码可能这样调用
        es.update_emotion("happiness", 10)
        es.update_emotion("sadness", -5)
        es.update_emotion("anger", 20)

        assert es.emotions["happiness"] == 60  # 50 + 10
        assert es.emotions["sadness"] == 5  # 10 - 5
        assert es.emotions["anger"] == 30  # 10 + 20

    def test_alias_migration(self):
        """测试情绪别名迁移"""
        es = EmotionSystem()

        # 旧代码使用anxiety
        es.update_emotion("anxiety", 30)
        # 应该映射到fear
        assert es.emotions["fear"] == 40  # 10 + 30

        # 旧代码使用jealousy
        es.update_emotion("jealousy", 20)
        # 应该映射到attachment
        assert es.emotions["attachment"] == 50  # 30 + 20

    def test_new_and_old_api_mixed(self):
        """测试新旧API混合使用"""
        es = EmotionSystem()

        # 旧API
        es.update_emotion("fear", 20)

        # 新API
        es.process_input(EmotionInput("fear", 0.5, "text", "event_001"))

        # 两种API应该能协同工作
        assert es.emotions["fear"] > 30  # 应该比只用旧API更高


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
