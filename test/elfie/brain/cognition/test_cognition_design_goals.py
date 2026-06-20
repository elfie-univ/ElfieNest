"""认知系统设计目标验证测试

验证三网络优先级、预测驱动主动行为、人格注入、动作解析等设计目标。
不依赖真实 LLM，使用 MockRuntimeAgent。
"""

import pytest

from elfie.brain.brain_types import BrainContext, SensorData
from elfie.brain.cognition.attention_manager import AttentionManager
from elfie.brain.cognition.brain import NeocortexBrain
from elfie.brain.cognition.expectation import ExpectationManager


class MockRuntimeAgent:
    """Mock LLM runtime agent，不调用真实大模型"""
    class MockConfig:
        remote_api_key = ""
    config = MockConfig()

    def __init__(self, response: str = "你好呀主人！ [ACTION]wag_tail[/ACTION]"):
        self._response = response

    def ask(self, prompt: str, energy: float, task_complexity: int) -> str:
        return self._response


# =============================================================================
# 三网络优先级测试
# =============================================================================

class TestNetworkPriority:
    """验证 DMN / CEN / SN 三脑网络的优先级调度"""

    def test_priority_sn_overrides_cen(self):
        """同时有新消息(CEN条件)和高突显度80(SN条件)→应返回SN模式"""
        am = AttentionManager()
        # has_new_message=True -> CEN, 但 salience_score=80 >= 70 -> SN
        result = am.evaluate_state(has_new_user_message=True, salience_score=80.0)
        assert result == "SN", "SN 应优先于 CEN"

    def test_priority_cen_when_message_no_salience(self):
        """有新消息但突显度低→应返回CEN模式"""
        am = AttentionManager()
        result = am.evaluate_state(has_new_user_message=True, salience_score=0.0)
        assert result == "CEN", "有新消息、低突显度时应进入 CEN"

    def test_priority_dmn_idle_when_nothing(self):
        """无消息无突显→应返回DMN_IDLE模式"""
        am = AttentionManager()
        result = am.evaluate_state(has_new_user_message=False, salience_score=0.0)
        assert result == "DMN", "无消息、无突显度时应回退至 DMN"


# =============================================================================
# 预测驱动主动行为测试
# =============================================================================

class TestPredictionDrivenBehavior:
    """验证预测加工机制(Predictive Processing)对主动行为的驱动"""

    def test_prediction_error_triggers_active(self):
        """温度40度(远超预期24)→预测误差>30→应进入DMN_ACTIVE模式→返回有speech_text"""
        brain = NeocortexBrain()
        mock_agent = MockRuntimeAgent(response="今天好热呀，开个空调吧！")

        context = BrainContext(
            sensors=SensorData(
                temperature=40.0,       # 远超预期 24°C
                has_new_message=False,
                salience_score=0.0,
            ),
            energy=100.0,
            emotion_mood="bored",
        )

        decision = brain.think_and_decide(context, mock_agent)

        assert decision.attention_mode == "DMN_ACTIVE", (
            f"高预测误差应进入 DMN_ACTIVE，实际为 {decision.attention_mode}"
        )
        assert decision.speech_text != "", "DMN_ACTIVE 应有 speech_text"

    def test_prediction_error_low_stays_idle(self):
        """温度25(接近预期)→误差<30→应进入DMN_IDLE→mutter不为None"""
        brain = NeocortexBrain()
        mock_agent = MockRuntimeAgent(response="不应被调用")

        context = BrainContext(
            sensors=SensorData(
                temperature=25.0,       # 接近预期 24°C（|25-24|=1，<=2，误差=0）
                has_new_message=False,
                salience_score=0.0,
            ),
            energy=100.0,
            emotion_mood="bored",
        )

        decision = brain.think_and_decide(context, mock_agent)

        assert decision.attention_mode == "DMN_IDLE", (
            f"低预测误差应进入 DMN_IDLE，实际为 {decision.attention_mode}"
        )
        assert decision.mutter is not None, "DMN_IDLE 应有 mutter 碎碎念"
        assert decision.speech_text == "", "DMN_IDLE 不应有 speech_text"


# =============================================================================
# 人格注入测试
# =============================================================================

class TestPersonalityInjection:
    """验证大五人格和物理限制注入到系统提示词"""

    def test_personality_prompt_contains_big_five(self):
        """NeocortexBrain().profile.get_system_prompt_segment()
        返回的文本应包含"开放度"、"外向度"、"宜人性"等大五人格关键词"""
        brain = NeocortexBrain()
        prompt = brain.profile.get_system_prompt_segment()

        assert "开放度" in prompt, "prompt 应包含开放度(Openness)"
        assert "外向度" in prompt, "prompt 应包含外向度(Extraversion)"
        assert "宜人性" in prompt, "prompt 应包含宜人性(Agreeableness)"
        assert "尽责度" in prompt, "prompt 应包含尽责度(Conscientiousness)"
        assert "情绪不稳定度" in prompt, "prompt 应包含情绪不稳定度(Neuroticism)"

    def test_personality_prompt_contains_physical_limits(self):
        """prompt应包含"飞行"或"游泳"等物理限制相关文字"""
        brain = NeocortexBrain()
        prompt = brain.profile.get_system_prompt_segment()

        assert "飞行" in prompt, "prompt 应包含飞行能力描述"
        assert "游泳" in prompt, "prompt 应包含游泳能力描述"


# =============================================================================
# 动作解析测试
# =============================================================================

class TestActionParsing:
    """验证 LLM 返回中的 [ACTION] 标签正确解析"""

    def test_action_tag_parsed_correctly(self):
        """LLM返回含[ACTION]wag_tail[/ACTION]→BrainDecision.action应为"wag_tail"，
        speech_text不含ACTION标签"""
        brain = NeocortexBrain()
        mock_agent = MockRuntimeAgent(
            response="好的主人，我摇摇尾巴！ [ACTION]wag_tail[/ACTION]"
        )

        context = BrainContext(
            sensors=SensorData(
                has_new_message=True,
                salience_score=0.0,
                user_message="来，摇个尾巴",
            ),
            energy=100.0,
            emotion_state="平静",
        )

        decision = brain.think_and_decide(context, mock_agent)

        assert decision.action == "wag_tail", (
            f"动作标签应解析为 wag_tail，实际为 {decision.action}"
        )
        assert "[ACTION]" not in decision.speech_text, (
            "speech_text 中不应残留 ACTION 标签"
        )
        assert "wag_tail" not in decision.speech_text, (
            "speech_text 中不应残留动作标签内容"
        )

    def test_no_action_tag_defaults_to_nod(self):
        """LLM返回无ACTION标签→BrainDecision.action应为"nod_head" """
        brain = NeocortexBrain()
        mock_agent = MockRuntimeAgent(response="你好呀，今天有什么可以帮你的吗？")

        context = BrainContext(
            sensors=SensorData(
                has_new_message=True,
                salience_score=0.0,
                user_message="你好",
            ),
            energy=100.0,
            emotion_state="平静",
        )

        decision = brain.think_and_decide(context, mock_agent)

        assert decision.action == "nod_head", (
            f"无动作标签时默认动作应为 nod_head，实际为 {decision.action}"
        )
        assert decision.attention_mode == "CEN"
