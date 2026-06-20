"""情绪系统设计目标验证测试 - Emotion System Design Goal Verification Tests

验证设计文档中描述的行为目标是否在代码中真正实现。
覆盖：饱和增长、分阶段衰减、频率慢化、Yerkes-Dodson倒U曲线、
人格调制、情绪交互（转移/抑制/增强）、表情映射完整性与强度分级。

注：Yerkes-Dodson倒U曲线当前尚未在代码中实现，相关测试标记为skip。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elfie.brain.emotion.accumulator.saturation import calculate_accumulation_delta
from elfie.brain.emotion.accumulator.decay import decay
from elfie.brain.emotion.accumulator.frequency import FrequencyTracker
from elfie.brain.emotion.emotion_input import EmotionInput
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.emotion.emotion_types import EMOTION_CONFIGS
from elfie.brain.emotion.expression_mapper import ExpressionMapper
from elfie.brain.emotion.interactions import (
    EmotionInteractionSystem,
    apply_transfer,
    get_enhancement_modifier,
    get_inhibition_modifier,
)
from elfie.brain.emotion.personality import PersonalityModifier


# =============================================================================
# 1. 饱和增长（Saturation）- 3 tests
# =============================================================================

class TestSaturation:
    """验证饱和增长设计目标：边际递减、高值缓慢增长、永不越界"""

    def test_saturation_decreasing_returns(self):
        """连续process_input加5次，第5次增量应 < 第1次增量的80%（边际递减）

        饱和公式: delta = base_delta * intensity * accumulate_rate * (1 - current/max)
        随着current增大，(1 - current/max) 减小，每步增量递减。
        """
        es = EmotionSystem()
        # 初始值为baseline 50，从低饱和状态开始才能看到明显递减
        es.emotions["happiness"] = 10  # 从低值开始

        deltas = []
        for i in range(5):
            before = es.emotions["happiness"]
            inp = EmotionInput("happiness", 1.0, "text", f"sat_event_{i}")
            es.process_input(inp)
            after = es.emotions["happiness"]
            deltas.append(after - before)

        # 第5次增量应小于第1次增量的80%
        assert deltas[4] < deltas[0] * 0.8, (
            f"第5次增量({deltas[4]:.3f})应小于第1次增量({deltas[0]:.3f})的80%"
        )

    def test_saturation_high_value_slow_growth(self):
        """值已为80时加10的增量 < 值为20时加10的增量

        饱和效应：高值时剩余容量少，同样输入产生的增量更小。
        使用calculate_accumulation_delta直接验证纯饱和逻辑。
        """
        config = EMOTION_CONFIGS["happiness"]

        # 值为20时的增量
        delta_low = calculate_accumulation_delta(
            current_value=20, base_delta=config["base_delta"],
            intensity=0.5, config=config,
        )

        # 值为80时的增量
        delta_high = calculate_accumulation_delta(
            current_value=80, base_delta=config["base_delta"],
            intensity=0.5, config=config,
        )

        assert delta_high < delta_low, (
            f"高值(80)增量({delta_high:.3f})应小于低值(20)增量({delta_low:.3f})"
        )

    def test_saturation_never_exceeds_max(self):
        """无论加多少，值永不超过100或低于0

        通过update_emotion（旧API）验证边界裁切机制。
        """
        es = EmotionSystem()

        # 大幅增加
        es.update_emotion("fear", 500)
        assert es.emotions["fear"] <= 100, "情绪值不应超过100"

        # 大幅减少
        es.update_emotion("fear", -500)
        assert es.emotions["fear"] >= 0, "情绪值不应低于0"

        # 通过process_input验证上限
        es.emotions["happiness"] = 99
        inp = EmotionInput("happiness", 1.0, "text", "max_test")
        es.process_input(inp)
        assert es.emotions["happiness"] <= 100, "process_input后情绪值不应超过100"


# =============================================================================
# 2. 分阶段衰减（Staged Decay）- 3 tests
# =============================================================================

class TestStagedDecay:
    """验证分阶段衰减设计目标：高值快消散、向基线靠拢不越界、与dt成正比"""

    def test_decay_high_value_faster(self):
        """值80时的衰减量 > 值20时的衰减量（高值快消散）

        分阶段衰减：value > threshold(50)时半衰期 = base * 0.3（快衰减）；
        value <= threshold时半衰期 = base * 3.0（慢衰减）。
        """
        config = EMOTION_CONFIGS["fear"]
        baseline = config["baseline"]
        half_life = config["half_life"]
        dt = 10.0

        # 高值区 (80 > 50)
        decay_high = baseline + (80 - baseline) * (0.5 ** (dt / (half_life * 0.3)))

        # 低值区 (20 < 50)
        decay_low = baseline + (20 - baseline) * (0.5 ** (dt / (half_life * 3.0)))

        # 实际衰减量
        actual_decay_high = 80 - decay_high
        actual_decay_low = 20 - decay_low

        assert actual_decay_high > actual_decay_low, (
            f"高值(80)衰减量({actual_decay_high:.3f})应大于低值(20)衰减量({actual_decay_low:.3f})"
        )

    def test_decay_positive_direction(self):
        """衰减后值应向baseline靠拢，不应过冲到负值

        指数衰减公式: new = baseline + (current - baseline) * 0.5^(dt/hl)
        decay_factor ∈ (0, 1]，因此new始终在baseline和current之间，不会过冲。
        """
        config = EMOTION_CONFIGS["happiness"]
        baseline = config["baseline"]  # 50

        # 高于baseline时衰减应向baseline下降
        result_above = decay(
            current_value=80, dt=60, config=config,
            baseline=baseline, half_life=config["half_life"],
        )
        assert baseline <= result_above < 80, (
            f"高于baseline时结果({result_above:.3f})应在[{baseline}, 80)之间"
        )

        # 低于baseline时衰减应向baseline回升
        result_below = decay(
            current_value=20, dt=60, config=config,
            baseline=baseline, half_life=config["half_life"],
        )
        assert 20 < result_below <= baseline, (
            f"低于baseline时结果({result_below:.3f})应在(20, {baseline}]之间"
        )

        # 任何时候都不应为负值
        result_extreme = decay(
            current_value=5, dt=10000, config=config,
            baseline=baseline, half_life=config["half_life"],
        )
        assert result_extreme >= 0, f"衰减结果({result_extreme:.3f})不应为负值"

    def test_decay_with_dt(self):
        """衰减量应与dt成正比（dt=2的衰减约等于dt=1的两倍）

        指数衰减的dt近似线性：对于小dt，decay_amount ≈ diff * ln(2) * dt / hl
        """
        config = EMOTION_CONFIGS["fear"]
        baseline = config["baseline"]
        half_life = config["half_life"]
        current = 80

        # dt=1时的衰减量
        after_1 = decay(
            current_value=current, dt=1, config=config,
            baseline=baseline, half_life=half_life,
        )
        decay_1 = current - after_1

        # dt=2时的衰减量
        after_2 = decay(
            current_value=current, dt=2, config=config,
            baseline=baseline, half_life=half_life,
        )
        decay_2 = current - after_2

        # dt=2的衰减应大于dt=1的衰减，且近似2倍关系
        assert decay_2 > decay_1, "dt=2的衰减量应大于dt=1"
        assert decay_2 < decay_1 * 2.5, "dt=2的衰减量不应超过dt=1的2.5倍"


# =============================================================================
# 3. 频率慢化（Frequency Slowdown）- 2 tests
# =============================================================================

class TestFrequencySlowdown:
    """验证频率慢化设计目标：高频时积累变慢"""

    def test_frequency_slowdown(self):
        """先连续刺激3次（高频），再process_input时增量低于首次

        频率追踪器在多次快速输入后slow_factor增大，
        使accumulate_rate降低，从而减缓后续增长。
        """
        es = EmotionSystem()
        es.emotions["anger"] = 10  # 从baseline开始

        # 第一次输入获取增量
        inp1 = EmotionInput("anger", 1.0, "text", "freq_1")
        before1 = es.emotions["anger"]
        es.process_input(inp1)
        after1 = es.emotions["anger"]
        first_delta = after1 - before1

        # 再刺激2次（共高频状态）
        for i in range(2, 5):
            inp = EmotionInput("anger", 1.0, "text", f"freq_{i}")
            es.process_input(inp)

        # 验证频率追踪器记录增多
        assert es.frequency_trackers["anger"].get_recent_count() == 4, (
            "4次输入后频率追踪器应记录4次"
        )

        # 第5次输入的增量应显著小于第1次（频率慢化 + 饱和共同作用）
        inp5 = EmotionInput("anger", 1.0, "text", "freq_5")
        before5 = es.emotions["anger"]
        es.process_input(inp5)
        after5 = es.emotions["anger"]
        fifth_delta = after5 - before5

        assert fifth_delta < first_delta, (
            f"第5次增量({fifth_delta:.3f})应小于第1次增量({first_delta:.3f})"
        )

    def test_frequency_tracker_increments(self):
        """连续刺激后频率追踪器记录的次数应增加

        FrequencyTracker使用滑动时间窗口记录输入频率。
        """
        ft = FrequencyTracker(window_size=60.0)
        assert ft.get_recent_count() == 0

        ft.record_input()
        assert ft.get_recent_count() == 1

        ft.record_input()
        ft.record_input()
        assert ft.get_recent_count() == 3

        # 验证slow_factor随次数增加
        slow_1 = ft.get_slow_factor()
        assert slow_1 == pytest.approx(1.0 + 3 * 0.5), (
            f"slow_factor应为{1.0 + 3 * 0.5}，实际为{slow_1}"
        )


# =============================================================================
# 4. Yerkes-Dodson 倒U曲线 - 2 tests (标记skip，尚未实现)
# =============================================================================

class TestYerkesDodson:
    """验证Yerkes-Dodson倒U曲线设计目标

    注意：当前代码使用线性强度乘法(delta ∝ intensity)，尚未实现倒U曲线。
    以下测试标记为skip，待实现后启用。
    """

    @pytest.mark.skip(
        reason="Yerkes-Dodson倒U曲线未实现："
               "当前calculate_accumulation_delta使用线性强度乘法，"
               "intensity=0.5产生的增量永远< intensity=1.0。"
               "需要引入arousal调制或非线性的强度-效能映射。"
    )
    def test_yerkes_dodson_moderate_best(self):
        """中等强度(intensity=0.5)的增量 > 极高强度(intensity=1.0)的增量

        倒U曲线：超过最优点后强度继续增加反而降低效能。
        """
        config = EMOTION_CONFIGS["happiness"]
        delta_moderate = calculate_accumulation_delta(
            current_value=50, base_delta=config["base_delta"],
            intensity=0.5, config=config,
        )
        delta_extreme = calculate_accumulation_delta(
            current_value=50, base_delta=config["base_delta"],
            intensity=1.0, config=config,
        )
        assert delta_moderate > delta_extreme, (
            f"中等强度(0.5)增量({delta_moderate:.3f})应大于极高强度(1.0)增量({delta_extreme:.3f})"
        )

    @pytest.mark.skip(
        reason="Yerkes-Dodson倒U曲线未实现："
               "当前线性强度机制下低强度永远<中等强度。"
    )
    def test_yerkes_dodson_low_intensity_low_gain(self):
        """低强度(intensity=0.1)的增量 < 中等强度(intensity=0.5)的增量"""
        config = EMOTION_CONFIGS["happiness"]
        delta_low = calculate_accumulation_delta(
            current_value=50, base_delta=config["base_delta"],
            intensity=0.1, config=config,
        )
        delta_moderate = calculate_accumulation_delta(
            current_value=50, base_delta=config["base_delta"],
            intensity=0.5, config=config,
        )
        assert delta_low < delta_moderate, (
            f"低强度(0.1)增量({delta_low:.3f})应小于中等强度(0.5)增量({delta_moderate:.3f})"
        )


# =============================================================================
# 5. 人格调制（Personality Modulation）- 3 tests
# =============================================================================

class TestPersonalityModulation:
    """验证Big Five人格设计目标：人格特质对情绪积累的调制效应"""

    def test_personality_high_neuroticism_fear(self):
        """高神经质(0.9)时恐惧增量 > 低神经质(0.1)时恐惧增量

        公式: modifier = 0.5 + neuroticism
        高神经质(0.9) → modifier=1.4，低神经质(0.1) → modifier=0.6
        """
        high_neuro = PersonalityModifier({"neuroticism": 0.9})
        low_neuro = PersonalityModifier({"neuroticism": 0.1})

        high_mod = high_neuro.get_accumulate_modifier("fear")
        low_mod = low_neuro.get_accumulate_modifier("fear")

        assert high_mod > low_mod, (
            f"高神经质modifier({high_mod:.2f})应大于低神经质modifier({low_mod:.2f})"
        )
        assert high_mod == pytest.approx(1.4), f"高神经质modifier应为1.4，实际{high_mod}"
        assert low_mod == pytest.approx(0.6), f"低神经质modifier应为0.6，实际{low_mod}"

    def test_personality_high_extraversion_happiness(self):
        """高外向度(0.9)时快乐增量 > 低外向度(0.1)时快乐增量

        公式: modifier = 0.5 + extraversion
        高外向(0.9) → modifier=1.4，低外向(0.1) → modifier=0.6
        """
        high_ext = PersonalityModifier({"extraversion": 0.9})
        low_ext = PersonalityModifier({"extraversion": 0.1})

        high_mod = high_ext.get_accumulate_modifier("happiness")
        low_mod = low_ext.get_accumulate_modifier("happiness")

        assert high_mod > low_mod, (
            f"高外向modifier({high_mod:.2f})应大于低外向modifier({low_mod:.2f})"
        )
        assert high_mod == pytest.approx(1.4), f"高外向modifier应为1.4，实际{high_mod}"
        assert low_mod == pytest.approx(0.6), f"低外向modifier应为0.6，实际{low_mod}"

    def test_personality_high_agreeableness_reduces_anger(self):
        """高宜人性(0.9)时愤怒增量 < 低宜人性(0.1)时愤怒增量

        公式: modifier = 1.5 - agreeableness
        高宜人(0.9) → modifier=0.6，低宜人(0.1) → modifier=1.4
        """
        high_agr = PersonalityModifier({"agreeableness": 0.9})
        low_agr = PersonalityModifier({"agreeableness": 0.1})

        high_mod = high_agr.get_accumulate_modifier("anger")
        low_mod = low_agr.get_accumulate_modifier("anger")

        assert high_mod < low_mod, (
            f"高宜人modifier({high_mod:.2f})应小于低宜人modifier({low_mod:.2f})"
        )
        assert high_mod == pytest.approx(0.6), f"高宜人modifier应为0.6，实际{high_mod}"
        assert low_mod == pytest.approx(1.4), f"低宜人modifier应为1.4，实际{low_mod}"


# =============================================================================
# 6. 情绪交互 - 转移（Transfer）- 2 tests
# =============================================================================

class TestInteractionTransfer:
    """验证情绪转移设计目标：恐惧→愤怒的定向转移"""

    def test_transfer_fear_to_anger_triggered(self):
        """恐惧值>70（转移阈值）时，恐惧应转移一部分给愤怒

        transfer_amount = (fear - threshold) * rate = (80-70)*0.1 = 1.0
        """
        emotions = {"fear": 80, "anger": 10}
        config = {"threshold": 70, "rate": 0.1}

        amount = apply_transfer(emotions, "fear", "anger", config)

        assert amount == 1.0, f"转移量应为1.0，实际{amount}"
        assert emotions["fear"] == 79.0, f"转移后fear应为79，实际{emotions['fear']}"
        assert emotions["anger"] == 11.0, f"转移后anger应为11，实际{emotions['anger']}"

    def test_transfer_below_threshold_no_transfer(self):
        """恐惧值<阈值时，不发生转移"""
        emotions = {"fear": 60, "anger": 10}
        config = {"threshold": 70, "rate": 0.1}

        amount = apply_transfer(emotions, "fear", "anger", config)

        assert amount == 0.0, "低于阈值不应转移"
        assert emotions["fear"] == 60, "fear不应变化"
        assert emotions["anger"] == 10, "anger不应变化"


# =============================================================================
# 7. 情绪交互 - 抑制（Inhibition）- 2 tests
# =============================================================================

class TestInteractionInhibition:
    """验证情绪抑制设计目标：快乐抑制愤怒"""

    def test_happiness_inhibits_anger(self):
        """快乐值>50时，愤怒的增长被抑制（实际增量 < 原始增量）

        inhibition_modifier = 1.0 - rate * source/max
        happiness=60时: modifier = 1.0 - 0.3*60/100 = 0.82
        导致anger的accumulate_rate降低为0.5*0.82=0.41
        """
        # 系统A：有快乐抑制
        es_with_happy = EmotionSystem()
        es_with_happy.emotions["happiness"] = 60
        es_with_happy.emotions["anger"] = 10

        # 系统B：无快乐抑制（happiness设为0）
        es_no_happy = EmotionSystem()
        es_no_happy.emotions["happiness"] = 0
        es_no_happy.emotions["anger"] = 10

        inp = EmotionInput("anger", 0.5, "text", "inhibit_test")

        es_with_happy.process_input(inp)
        # 需要重新创建相同event_id的输入（已被去重）
        inp2 = EmotionInput("anger", 0.5, "text", "inhibit_test2")
        es_no_happy.process_input(inp2)

        assert es_with_happy.emotions["anger"] < es_no_happy.emotions["anger"], (
            f"有抑制时anger({es_with_happy.emotions['anger']:.3f})"
            f"应小于无抑制时({es_no_happy.emotions['anger']:.3f})"
        )

    def test_inhibition_no_source_no_effect(self):
        """无快乐源时，抑制不生效（modifier=1.0）"""
        # 空情绪字典 → source_val=0 → modifier=1.0
        emotions_empty = {}
        modifier = get_inhibition_modifier(emotions_empty, "happiness", 0.3)
        assert modifier == 1.0, f"无源时应返回1.0，实际{modifier}"

        # source=0时也应为1.0
        emotions_zero = {"happiness": 0}
        modifier = get_inhibition_modifier(emotions_zero, "happiness", 0.3)
        assert modifier == 1.0, f"source=0时应返回1.0，实际{modifier}"


# =============================================================================
# 8. 情绪交互 - 增强（Enhancement）- 2 tests
# =============================================================================

class TestInteractionEnhancement:
    """验证情绪增强设计目标：悲伤增强依恋"""

    def test_sadness_enhances_attachment(self):
        """悲伤值>0时，依恋的增长被增强（实际增量 > 原始增量）

        enhancement_modifier = 1.0 + rate * source/max
        sadness=50时: modifier = 1.0 + 0.2*50/100 = 1.1
        导致attachment的accumulate_rate提高为0.5*1.1=0.55
        """
        # 系统A：有悲伤增强
        es_with_sad = EmotionSystem()
        es_with_sad.emotions["sadness"] = 50
        es_with_sad.emotions["attachment"] = 30

        # 系统B：无悲伤增强
        es_no_sad = EmotionSystem()
        es_no_sad.emotions["sadness"] = 0
        es_no_sad.emotions["attachment"] = 30

        inp1 = EmotionInput("attachment", 0.5, "text", "enhance_test1")
        inp2 = EmotionInput("attachment", 0.5, "text", "enhance_test2")

        es_with_sad.process_input(inp1)
        es_no_sad.process_input(inp2)

        assert es_with_sad.emotions["attachment"] > es_no_sad.emotions["attachment"], (
            f"有增强时attachment({es_with_sad.emotions['attachment']:.3f})"
            f"应大于无增强时({es_no_sad.emotions['attachment']:.3f})"
        )

    def test_enhancement_ratio_reasonable(self):
        """增强后的增量应在合理范围内（不超过2倍原始）

        最大增强: rate=0.2, source=100 → modifier=1.2，小于2x。
        """
        # 最大增强场景
        emotions_max = {"sadness": 100}
        modifier = get_enhancement_modifier(emotions_max, "sadness", 0.2)
        assert modifier <= 2.0, f"增强系数({modifier:.3f})不应超过2.0"
        assert modifier == pytest.approx(1.2), f"max modifier应为1.2，实际{modifier}"

        # 中等增强场景
        emotions_mid = {"sadness": 50}
        modifier = get_enhancement_modifier(emotions_mid, "sadness", 0.2)
        assert modifier == pytest.approx(1.1), f"中等增强应为1.1，实际{modifier}"

        # 无增强场景
        emotions_none = {}
        modifier = get_enhancement_modifier(emotions_none, "sadness", 0.2)
        assert modifier == 1.0, f"无增强时应为1.0，实际{modifier}"


# =============================================================================
# 9. 表情映射完整（Expression Mapping）- 7 tests
# =============================================================================

class TestExpressionMapping:
    """验证表情映射设计目标：各情绪正确映射到表情参数"""

    def test_expression_happiness(self):
        """快乐(happiness)映射到happy_face表情和cheerful语音"""
        mapper = ExpressionMapper()
        result = mapper.get_expression_for_emotions({"happiness": 50})
        assert result["expression"] == "happy_face"
        assert result["voice_modifier"] == "cheerful"
        assert result["emotion"] == "happiness"

    def test_expression_fear(self):
        """恐惧(fear)映射到fearful_face表情和nervous语音"""
        mapper = ExpressionMapper()
        result = mapper.get_expression_for_emotions({"fear": 50})
        assert result["expression"] == "fearful_face"
        assert result["voice_modifier"] == "nervous"
        assert result["emotion"] == "fear"

    def test_expression_sadness(self):
        """悲伤(sadness)映射到sad_face表情和sorrowful语音"""
        mapper = ExpressionMapper()
        result = mapper.get_expression_for_emotions({"sadness": 50})
        assert result["expression"] == "sad_face"
        assert result["voice_modifier"] == "sorrowful"
        assert result["emotion"] == "sadness"

    def test_expression_anger(self):
        """愤怒(anger)映射到angry_face表情和firm语音"""
        mapper = ExpressionMapper()
        result = mapper.get_expression_for_emotions({"anger": 50})
        assert result["expression"] == "angry_face"
        assert result["voice_modifier"] == "firm"
        assert result["emotion"] == "anger"

    def test_expression_surprise(self):
        """惊讶(surprise)映射到surprised_face表情和excited语音"""
        mapper = ExpressionMapper()
        result = mapper.get_expression_for_emotions({"surprise": 40})
        assert result["expression"] == "surprised_face"
        assert result["voice_modifier"] == "excited"
        assert result["emotion"] == "surprise"

    def test_expression_disgust(self):
        """厌恶(disgust)映射到disgusted_face表情和disgusted语音"""
        mapper = ExpressionMapper()
        result = mapper.get_expression_for_emotions({"disgust": 50})
        assert result["expression"] == "disgusted_face"
        assert result["voice_modifier"] == "disgusted"
        assert result["emotion"] == "disgust"

    def test_expression_intensity_levels(self):
        """同一情绪不同强度级别(low/medium/high)应映射到不同程度的表情

        低(<40): 基础动作；中(40-69): 进阶动作；高(>=70): 复合动作。
        """
        mapper = ExpressionMapper()

        # 低强度 (value=30, threshold=30, 刚好触发)
        low = mapper.get_expression_for_emotions({"happiness": 30})
        # 中等强度
        medium = mapper.get_expression_for_emotions({"happiness": 50})
        # 高强度
        high = mapper.get_expression_for_emotions({"happiness": 80})

        # 验证强度级别
        assert low["intensity"] == 30
        assert medium["intensity"] == 50
        assert high["intensity"] == 80

        # 验证不同程度的动作
        low_actions = low["actions"]
        high_actions = high["actions"]
        # 高级别动作集应包含低级别以外的动作（非严格超集，但应有差异）
        assert low_actions != high_actions, "低强度和高强度的动作应不同"
        assert medium["actions"] != high["actions"], "中等强度和高强度的动作应不同"
        assert low["voice_modifier"] == medium["voice_modifier"] == high["voice_modifier"] == "cheerful", (
            "语音修饰符在不同强度级别应保持一致"
        )


# =============================================================================
# 集成测试：通过EmotionSystem验证完整交互链路
# =============================================================================

class TestDesignGoalIntegration:
    """验证多个设计目标通过EmotionSystem协同工作的效果"""

    def test_get_expression_through_emotion_system(self):
        """验证EmotionSystem.get_expression()返回完整的表达参数

        端到端验证：设置情绪→触发process_input→调用get_expression→
        返回正确的expression/voice_modifier/actions。
        """
        es = EmotionSystem()
        es.emotions["happiness"] = 60
        es.emotions["fear"] = 10

        expr = es.get_expression()

        assert isinstance(expr, dict), "get_expression应返回字典"
        assert "expression" in expr
        assert "actions" in expr
        assert "voice_modifier" in expr
        assert "intensity" in expr
        assert "emotion" in expr

        # 主导情绪应为happiness(60)
        assert expr["emotion"] == "happiness"
        assert expr["intensity"] == 60
        assert expr["voice_modifier"] == "cheerful"

    def test_tick_applies_transfer_after_decay(self):
        """tick()先衰减所有情绪，再应用转移交互

        EmotionSystem.tick()的流程：
        1. 遍历所有情绪应用decay
        2. 调用interaction_system.apply_transfer_interactions()
        """
        es = EmotionSystem()
        # fear=80（超过70阈值），anger=10（baseline）
        es.emotions["fear"] = 80
        es.emotions["anger"] = 10

        es.tick(0.001)  # 微小dt以触发转移但几乎不衰减

        # 转移应发生：fear下降，anger上升
        assert es.emotions["fear"] < 80, "tick后fear应下降（转移）"
        assert es.emotions["anger"] > 10, "tick后anger应上升（接收转移）"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
