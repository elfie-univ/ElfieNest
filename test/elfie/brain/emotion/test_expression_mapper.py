"""情绪表达映射器单元测试 - Expression Mapper Unit Tests

测试覆盖：
- 配置加载
- 强度阈值
- 主导情绪选择
- 边界情况
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elfie.brain.emotion.expression_mapper import ExpressionMapper


class TestExpressionMapper:
    """ExpressionMapper 核心功能测试"""

    def test_config_loading(self):
        """测试配置加载 - 验证6种情绪配置正确加载"""
        mapper = ExpressionMapper()
        config = mapper._config
        
        assert config is not None
        assert "emotions" in config
        assert "default_expression" in config
        
        emotions = config["emotions"]
        expected_emotions = {"happiness", "sadness", "anger", "fear", "surprise", "disgust"}
        assert set(emotions.keys()) == expected_emotions

    def test_intensity_level_low(self):
        """测试低强度等级判定 - 值 < 40"""
        mapper = ExpressionMapper()
        assert mapper._get_intensity_level(20) == "low"
        assert mapper._get_intensity_level(39) == "low"

    def test_intensity_level_medium(self):
        """测试中等强度等级判定 - 40 <= 值 < 70"""
        mapper = ExpressionMapper()
        assert mapper._get_intensity_level(40) == "medium"
        assert mapper._get_intensity_level(69) == "medium"

    def test_intensity_level_high(self):
        """测试高强度等级判定 - 值 >= 70"""
        mapper = ExpressionMapper()
        assert mapper._get_intensity_level(70) == "high"
        assert mapper._get_intensity_level(100) == "high"

    def test_dominant_emotion_selection(self):
        """测试主导情绪选择 - 超过阈值的最高情绪"""
        mapper = ExpressionMapper()
        
        emotions = {
            "happiness": 35,   # 超过阈值30
            "sadness": 20,     # 未超过阈值40
            "anger": 45        # 超过阈值40
        }
        
        result = mapper.get_expression_for_emotions(emotions)
        
        # anger的值45更高，所以主导情绪是anger
        assert result["emotion"] == "anger"
        assert result["intensity"] == 45

    def test_dominant_emotion_higher_value(self):
        """测试主导情绪 - 值越高越优先"""
        mapper = ExpressionMapper()
        
        emotions = {
            "happiness": 50,
            "anger": 45
        }
        
        result = mapper.get_expression_for_emotions(emotions)
        
        assert result["emotion"] == "happiness"
        assert result["intensity"] == 50

    def test_no_emotion_above_threshold(self):
        """测试无情绪超过阈值 - 返回默认表达"""
        mapper = ExpressionMapper()
        
        emotions = {
            "happiness": 20,
            "sadness": 25,
            "anger": 30
        }
        
        result = mapper.get_expression_for_emotions(emotions)
        
        assert result["emotion"] == "neutral"
        assert result["expression"] == "neutral_face"

    def test_empty_emotions(self):
        """测试空情绪字典 - 返回默认表达"""
        mapper = ExpressionMapper()
        
        result = mapper.get_expression_for_emotions({})
        
        assert result["emotion"] == "neutral"
        assert result["expression"] == "neutral_face"

    def test_actions_by_intensity(self):
        """测试不同强度选择不同动作"""
        mapper = ExpressionMapper()
        
        emotions_low = {"happiness": 30}
        emotions_medium = {"happiness": 50}
        emotions_high = {"happiness": 80}
        
        result_low = mapper.get_expression_for_emotions(emotions_low)
        result_medium = mapper.get_expression_for_emotions(emotions_medium)
        result_high = mapper.get_expression_for_emotions(emotions_high)
        
        assert result_low["actions"] == ["wag_tail"]
        assert result_medium["actions"] == ["wiggle_ears"]
        assert result_high["actions"] == ["jump", "wag_tail"]

    def test_voice_modifier(self):
        """测试语音修饰符正确返回"""
        mapper = ExpressionMapper()
        
        emotions = {"happiness": 50}
        result = mapper.get_expression_for_emotions(emotions)
        
        assert result["voice_modifier"] == "cheerful"

    def test_sadness_expression(self):
        """测试悲伤情绪表达映射"""
        mapper = ExpressionMapper()
        
        emotions = {"sadness": 60}
        result = mapper.get_expression_for_emotions(emotions)
        
        assert result["expression"] == "sad_face"
        assert result["actions"] == ["slow_movement"]
        assert result["voice_modifier"] == "sorrowful"

    def test_anger_expression(self):
        """测试愤怒情绪表达映射"""
        mapper = ExpressionMapper()
        
        emotions = {"anger": 75}
        result = mapper.get_expression_for_emotions(emotions)
        
        assert result["expression"] == "angry_face"
        assert result["actions"] == ["shake_head", "stomp"]
        assert result["voice_modifier"] == "firm"

    def test_fear_expression(self):
        """测试恐惧情绪表达映射"""
        mapper = ExpressionMapper()
        
        emotions = {"fear": 55}
        result = mapper.get_expression_for_emotions(emotions)
        
        assert result["expression"] == "fearful_face"
        assert result["actions"] == ["hide"]
        assert result["voice_modifier"] == "nervous"

    def test_surprise_expression(self):
        """测试惊讶情绪表达映射"""
        mapper = ExpressionMapper()
        
        emotions = {"surprise": 40}
        result = mapper.get_expression_for_emotions(emotions)
        
        assert result["expression"] == "surprised_face"
        assert result["actions"] == ["jump"]
        assert result["voice_modifier"] == "excited"

    def test_disgust_expression(self):
        """测试厌恶情绪表达映射"""
        mapper = ExpressionMapper()
        
        emotions = {"disgust": 50}
        result = mapper.get_expression_for_emotions(emotions)
        
        assert result["expression"] == "disgusted_face"
        assert result["actions"] == ["step_back"]
        assert result["voice_modifier"] == "disgusted"

    def test_threshold_respected(self):
        """测试阈值被正确遵守"""
        mapper = ExpressionMapper()
        
        emotions_below = {"happiness": 29}
        emotions_at = {"happiness": 30}
        emotions_above = {"happiness": 31}
        
        result_below = mapper.get_expression_for_emotions(emotions_below)
        result_at = mapper.get_expression_for_emotions(emotions_at)
        result_above = mapper.get_expression_for_emotions(emotions_above)
        
        assert result_below["emotion"] == "neutral"
        assert result_at["emotion"] == "happiness"
        assert result_above["emotion"] == "happiness"

    def test_unknown_emotion_ignored(self):
        """测试未知情绪被忽略"""
        mapper = ExpressionMapper()
        
        emotions = {
            "happiness": 50,
            "unknown_emotion": 80
        }
        
        result = mapper.get_expression_for_emotions(emotions)
        
        assert result["emotion"] == "happiness"
