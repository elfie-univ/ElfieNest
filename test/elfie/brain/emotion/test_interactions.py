import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elfie.brain.emotion.interactions import (
    EmotionInteractionSystem,
    apply_transfer,
    get_enhancement_modifier,
    get_inhibition_modifier,
)


class TestApplyTransfer:
    """测试apply_transfer函数"""

    def test_transfer_fear_to_anger(self):
        """恐惧超过阈值时转移到愤怒"""
        emotions = {"fear": 80, "anger": 10}
        config = {"threshold": 70, "rate": 0.1}

        amount = apply_transfer(emotions, "fear", "anger", config)

        assert amount == 1.0  # (80-70) * 0.1 = 1.0
        assert emotions["fear"] == 79.0
        assert emotions["anger"] == 11.0

    def test_transfer_below_threshold(self):
        """低于阈值时不转移"""
        emotions = {"fear": 60, "anger": 10}
        config = {"threshold": 70, "rate": 0.1}

        amount = apply_transfer(emotions, "fear", "anger", config)

        assert amount == 0.0
        assert emotions["fear"] == 60
        assert emotions["anger"] == 10


class TestInhibitionModifier:
    """测试get_inhibition_modifier函数"""

    def test_inhibition_basic(self):
        """基本抑制计算"""
        emotions = {"happiness": 60}
        modifier = get_inhibition_modifier(emotions, "happiness", 0.3)

        assert abs(modifier - 0.82) < 0.01  # 1.0 - 0.3 * 60/100 = 0.82

    def test_inhibition_minimum(self):
        """抑制系数最小为0.1"""
        emotions = {"happiness": 100}
        modifier = get_inhibition_modifier(emotions, "happiness", rate=1.0)

        assert modifier == 0.1  # 1.0 - 1.0 * 100/100 = 0.0, clamped to 0.1

    def test_inhibition_no_source(self):
        """无源情绪时无抑制"""
        emotions = {}
        modifier = get_inhibition_modifier(emotions, "happiness", 0.3)

        assert modifier == 1.0


class TestEnhancementModifier:
    """测试get_enhancement_modifier函数"""

    def test_enhancement_basic(self):
        """基本增强计算"""
        emotions = {"sadness": 50}
        modifier = get_enhancement_modifier(emotions, "sadness", 0.2)

        assert abs(modifier - 1.1) < 0.01  # 1.0 + 0.2 * 50/100 = 1.1

    def test_enhancement_max(self):
        """最大值增强"""
        emotions = {"sadness": 100}
        modifier = get_enhancement_modifier(emotions, "sadness", 0.2)

        assert abs(modifier - 1.2) < 0.01  # 1.0 + 0.2 * 100/100 = 1.2

    def test_enhancement_no_source(self):
        """无源情绪时无增强"""
        emotions = {}
        modifier = get_enhancement_modifier(emotions, "sadness", 0.2)

        assert modifier == 1.0


class TestEmotionInteractionSystem:
    """测试EmotionInteractionSystem类"""

    def test_apply_transfer_interactions(self):
        """测试应用所有转移交互"""
        system = EmotionInteractionSystem()
        emotions = {"fear": 85, "anger": 10}

        results = system.apply_transfer_interactions(emotions)

        assert ("fear", "anger") in results
        assert abs(results[("fear", "anger")] - 1.5) < 0.01  # (85-70) * 0.1 = 1.5

    def test_get_accumulate_modifier_anger(self):
        """测试anger的累积调节系数（受happiness抑制）"""
        system = EmotionInteractionSystem()
        emotions = {"happiness": 60, "anger": 20}

        modifier = system.get_accumulate_modifier("anger", emotions)

        assert abs(modifier - 0.82) < 0.01

    def test_get_accumulate_modifier_attachment(self):
        """测试attachment的累积调节系数（受sadness增强）"""
        system = EmotionInteractionSystem()
        emotions = {"sadness": 50, "attachment": 30}

        modifier = system.get_accumulate_modifier("attachment", emotions)

        assert abs(modifier - 1.1) < 0.01

    def test_get_accumulate_modifier_no_interaction(self):
        """无交互时返回1.0"""
        system = EmotionInteractionSystem()
        emotions = {"happiness": 50}

        modifier = system.get_accumulate_modifier("fear", emotions)

        assert modifier == 1.0

    def test_get_interaction_info(self):
        """测试获取交互信息"""
        system = EmotionInteractionSystem()

        info = system.get_interaction_info("fear", "anger")
        assert info["type"] == "transfer"
        assert info["threshold"] == 70
        assert info["rate"] == 0.1

        info = system.get_interaction_info("happiness", "anger")
        assert info["type"] == "inhibition"

        info = system.get_interaction_info("nonexistent", "anger")
        assert info is None


class TestEmotionSystemInteractions:
    """测试EmotionSystem与EmotionInteractionSystem的集成"""

    def test_fear_transfer_to_anger(self):
        """测试恐惧过高时转移到愤怒"""
        from elfie.brain.emotion.emotion_system import EmotionSystem

        es = EmotionSystem()

        es.emotions["fear"] = 80
        es.emotions["anger"] = 10

        es.tick(1.0)

        assert es.emotions["fear"] < 80
        assert es.emotions["anger"] > 10

    def test_happiness_inhibits_anger(self):
        """测试快乐抑制愤怒增长"""
        from elfie.brain.emotion.emotion_input import EmotionInput
        from elfie.brain.emotion.emotion_system import EmotionSystem

        es = EmotionSystem()

        es.emotions["happiness"] = 60
        es.emotions["anger"] = 20

        inp = EmotionInput(
            emotion="anger", intensity=0.5, source="brain", event_id="e1"
        )
        es.process_input(inp)

        assert es.emotions["anger"] < 28

    def test_sadness_enhances_attachment(self):
        """测试悲伤增强依恋增长"""
        from elfie.brain.emotion.emotion_input import EmotionInput
        from elfie.brain.emotion.emotion_system import EmotionSystem

        es = EmotionSystem()

        es.emotions["sadness"] = 50
        es.emotions["attachment"] = 30

        inp = EmotionInput(
            emotion="attachment", intensity=0.5, source="brain", event_id="e1"
        )
        es.process_input(inp)

        assert es.emotions["attachment"] > 31.7  # without sadness would be ~31.75
