"""Personality Modifier Unit Tests

Test Big Five personality model effects on emotion accumulation and decay.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elfie.brain.emotion.personality import PersonalityModifier, calculate_personality_modifier


class TestPersonalityModifier:
    """PersonalityModifier功能测试"""
    
    def test_high_neuroticism_accumulate(self):
        """高神经质(0.9)：负面情绪增长快40%（modifier=1.4）"""
        personality = {'neuroticism': 0.9}
        pm = PersonalityModifier(personality)
        assert pm.get_accumulate_modifier('fear') == pytest.approx(1.4)
        assert pm.get_accumulate_modifier('anger') == pytest.approx(1.4)
        assert pm.get_accumulate_modifier('sadness') == pytest.approx(1.4)
    
    def test_low_neuroticism_accumulate(self):
        """低神经质(0.2)：负面情绪增长慢30%（modifier=0.7）"""
        personality = {'neuroticism': 0.2}
        pm = PersonalityModifier(personality)
        assert pm.get_accumulate_modifier('fear') == pytest.approx(0.7)
        assert pm.get_accumulate_modifier('anger') == pytest.approx(0.7)
        assert pm.get_accumulate_modifier('sadness') == pytest.approx(0.7)
    
    def test_high_agreeableness_anger(self):
        """高宜人性(0.9)：愤怒增长慢40%（modifier=0.6）"""
        personality = {'agreeableness': 0.9}
        pm = PersonalityModifier(personality)
        assert pm.get_accumulate_modifier('anger') == pytest.approx(0.6)
    
    def test_high_agreeableness_attachment(self):
        """高宜人性(0.9)：依恋增长快40%（modifier=1.4）"""
        personality = {'agreeableness': 0.9}
        pm = PersonalityModifier(personality)
        assert pm.get_accumulate_modifier('attachment') == pytest.approx(1.4)
    
    def test_high_extraversion_happiness(self):
        """高外向性(0.9)：快乐增长快40%（modifier=1.4）"""
        personality = {'extraversion': 0.9}
        pm = PersonalityModifier(personality)
        assert pm.get_accumulate_modifier('happiness') == pytest.approx(1.4)
    
    def test_decay_inverse_of_accumulate(self):
        """衰减速率与累积速率相反（高神经质衰减慢）"""
        personality = {'neuroticism': 0.9}
        pm = PersonalityModifier(personality)
        accumulate = pm.get_accumulate_modifier('fear')
        decay = pm.get_decay_modifier('fear')
        assert decay == pytest.approx(1.0 / accumulate)
    
    def test_default_personality(self):
        """默认性格（全0.5）：modifier=1.0"""
        pm = PersonalityModifier()
        assert pm.get_accumulate_modifier('fear') == pytest.approx(1.0)
        assert pm.get_accumulate_modifier('anger') == pytest.approx(1.0)
        assert pm.get_accumulate_modifier('happiness') == pytest.approx(1.0)
        assert pm.get_accumulate_modifier('attachment') == pytest.approx(1.0)
    
    def test_accumulate_range(self):
        """累积调节系数范围0.5-1.5"""
        pm_low = PersonalityModifier({'neuroticism': 0.0, 'extraversion': 0.0, 'agreeableness': 0.0})
        pm_high = PersonalityModifier({'neuroticism': 1.0, 'extraversion': 1.0, 'agreeableness': 1.0})
        
        assert 0.4 <= pm_low.get_accumulate_modifier('fear') <= 0.6
        assert 1.4 <= pm_high.get_accumulate_modifier('fear') <= 1.6
    
    def test_decay_range(self):
        """衰减调节系数范围（高累积=低衰减，反之亦然）"""
        pm_low = PersonalityModifier({'neuroticism': 0.2})
        pm_high = PersonalityModifier({'neuroticism': 0.8})
        
        assert pm_low.get_decay_modifier('fear') > pm_high.get_decay_modifier('fear')


class TestCalculatePersonalityModifier:
    """calculate_personality_modifier函数测试"""
    
    def test_neuroticism_formula(self):
        """验证神经质公式：0.5 + neuroticism"""
        personality = {'neuroticism': 0.5}
        result = calculate_personality_modifier(personality, 'fear')
        assert result == pytest.approx(1.0)
    
    def test_agreeableness_anger_formula(self):
        """验证宜人性愤怒公式：1.5 - agreeableness"""
        personality = {'agreeableness': 0.5}
        result = calculate_personality_modifier(personality, 'anger')
        assert result == pytest.approx(1.0)
    
    def test_agreeableness_attachment_formula(self):
        """验证宜人性依恋公式：0.5 + agreeableness"""
        personality = {'agreeableness': 0.5}
        result = calculate_personality_modifier(personality, 'attachment')
        assert result == pytest.approx(1.0)
    
    def test_extraversion_happiness_formula(self):
        """验证外向性快乐公式：0.5 + extraversion"""
        personality = {'extraversion': 0.5}
        result = calculate_personality_modifier(personality, 'happiness')
        assert result == pytest.approx(1.0)
    
    def test_unaffected_emotion(self):
        """不受性格影响的情绪"""
        personality = {'neuroticism': 0.9, 'agreeableness': 0.9, 'extraversion': 0.9}
        result = calculate_personality_modifier(personality, 'surprise')
        assert result == pytest.approx(1.0)
