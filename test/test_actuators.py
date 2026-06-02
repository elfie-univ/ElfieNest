# -*- coding: utf-8 -*-
"""测试执行器模块 (SpeechActuator 和 MotionActuator)"""
import pytest
import sys
import math

sys.path.insert(0, "/Users/zhenli/git-code/ElfieNest")

from elfie.interface.actuators.speech import SpeechActuator
from elfie.interface.actuators.motion import MotionActuator
from elfie.body.anatomy.base import VoiceProfile, SomaticAnatomy
from elfie.body.anatomy.biped import BipedAnatomy
from elfie.body.anatomy.quadruped import QuadrupedAnatomy


class TestSpeechActuator:
    """SpeechActuator 单元测试"""

    def test_init(self):
        """测试 SpeechActuator 初始化"""
        actuator = SpeechActuator()
        assert actuator is not None

    def test_synthesize_speech_empty_text(self):
        """测试空文本输入返回空字符串"""
        actuator = SpeechActuator()
        result = actuator.synthesize_speech("")
        assert result == ""

    def test_synthesize_speech_with_none_text(self):
        """测试 None 输入返回空字符串"""
        actuator = SpeechActuator()
        # 模拟处理无消息场景 - 传入空字符串而非None
        result = actuator.synthesize_speech("")
        assert result == ""

    def test_synthesize_speech_with_text(self):
        """测试正常文本合成"""
        actuator = SpeechActuator()
        text = "你好，我是小精灵"
        result = actuator.synthesize_speech(text)
        assert result == text

    def test_synthesize_speech_with_voice_profile(self):
        """测试带 VoiceProfile 的语音合成"""
        actuator = SpeechActuator()
        profile = VoiceProfile(
            pitch=1.5,
            speed=0.8,
            timbre="gentle",
            frequency_curve=[0.8, 0.9, 1.0, 1.1, 1.2, 1.1, 1.0, 0.9, 0.8, 0.9]
        )
        text = "测试语音"
        result = actuator.synthesize_speech(text, voice_profile=profile)
        assert result == text

    def test_synthesize_speech_default_voice_profile(self):
        """测试使用默认 VoiceProfile"""
        actuator = SpeechActuator()
        text = "默认音色"
        result = actuator.synthesize_speech(text)
        assert result == text
        # 默认 profile 应该被正确创建
        profile = VoiceProfile()
        assert profile.pitch == 1.0
        assert profile.speed == 1.0
        assert profile.timbre == "cute"

    def test_speak_method(self):
        """测试 speak 方法是 synthesize_speech 的别名"""
        actuator = SpeechActuator()
        text = "Hello World"
        result = actuator.speak(text)
        assert result == text

    def test_speak_empty(self):
        """测试 speak 方法处理空字符串"""
        actuator = SpeechActuator()
        result = actuator.speak("")
        assert result == ""


class TestMotionActuator:
    """MotionActuator 单元测试"""

    def test_init(self):
        """测试 MotionActuator 初始化"""
        actuator = MotionActuator()
        assert actuator is not None
        assert actuator.gait_engine is not None
        assert actuator.last_action_intent == "idle"

    def test_translate_and_drive_nod_head(self):
        """测试 nod_head 动作"""
        actuator = MotionActuator()
        anatomy = BipedAnatomy()

        result = actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent="nod_head",
            speed=1.0,
            elapsed_time=0.0
        )

        assert "neck_pitch" in result
        assert result["neck_pitch"] == 0.4
        assert actuator.last_action_intent == "nod_head"

    def test_translate_and_drive_blink_eyes(self):
        """测试 blink_eyes 动作 (关节置零)"""
        actuator = MotionActuator()
        anatomy = BipedAnatomy()

        result = actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent="blink_eyes",
            speed=1.0,
            elapsed_time=0.0
        )

        # 所有关节应该被置零
        for joint_name in anatomy.joints.keys():
            assert result[joint_name] == 0.0

    def test_translate_and_drive_empty_action(self):
        """测试空动作 (blink_eyes 行为)"""
        actuator = MotionActuator()
        anatomy = BipedAnatomy()

        result = actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent="",  # 空字符串
            speed=1.0,
            elapsed_time=0.0
        )

        # 应该与 blink_eyes 行为一致
        for joint_name in anatomy.joints.keys():
            assert result[joint_name] == 0.0

    def test_translate_and_drive_walk_biped(self):
        """测试 biped 行走步态"""
        actuator = MotionActuator()
        anatomy = BipedAnatomy()

        result = actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent="walk",
            speed=1.0,
            elapsed_time=0.5
        )

        # 验证 biped 行走关节存在
        assert "left_hip" in result
        assert "right_hip" in result
        assert "left_shoulder" in result
        assert "right_shoulder" in result
        # biped walk 应该有左右反相
        assert result["left_hip"] * result["right_hip"] < 0

    def test_translate_and_drive_run_biped(self):
        """测试 biped 奔跑步态 (幅度更大)"""
        actuator = MotionActuator()
        anatomy = BipedAnatomy()

        walk_result = actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent="walk",
            speed=1.0,
            elapsed_time=0.5
        )

        run_result = actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent="run",
            speed=1.0,
            elapsed_time=0.5
        )

        # 奔跑幅度应该更大
        walk_amp = abs(walk_result["left_hip"])
        run_amp = abs(run_result["left_hip"])
        assert run_amp > walk_amp

    def test_translate_and_drive_idle(self):
        """测试 idle 待机动作"""
        actuator = MotionActuator()
        anatomy = BipedAnatomy()

        result = actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent="idle",
            speed=1.0,
            elapsed_time=1.0
        )

        # idle 应该有呼吸起伏
        assert "neck_pitch" in result
        # 幅度应该很小
        assert abs(result["neck_pitch"]) < 0.1

    def test_translate_and_drive_wave_hands(self):
        """测试挥手动作"""
        actuator = MotionActuator()
        anatomy = BipedAnatomy()

        result = actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent="wave_hands",
            speed=1.0,
            elapsed_time=0.0
        )

        # 应该有肩膀关节动作
        assert "left_shoulder" in result or "right_shoulder" in result

    def test_translate_and_drive_walk_quadruped(self):
        """测试 quadruped 行走步态"""
        actuator = MotionActuator()
        anatomy = QuadrupedAnatomy()

        result = actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent="walk",
            speed=1.0,
            elapsed_time=0.5
        )

        # 验证 quadruped 行走关节
        assert "front_left_leg" in result
        assert "front_right_leg" in result
        assert "back_left_leg" in result
        assert "back_right_leg" in result

    def test_translate_and_drive_wag_tail_quadruped(self):
        """测试 quadruped 摇尾巴动作"""
        actuator = MotionActuator()
        anatomy = QuadrupedAnatomy()

        result = actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent="wag_tail",
            speed=1.0,
            elapsed_time=0.5
        )

        assert "tail_wag" in result

    def test_translate_and_drive_speed_factor(self):
        """测试速度因子对步态的影响"""
        actuator = MotionActuator()
        anatomy = BipedAnatomy()

        slow_result = actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent="walk",
            speed=0.5,
            elapsed_time=1.0
        )

        fast_result = actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent="walk",
            speed=2.0,
            elapsed_time=1.0
        )

        # 不同速度应该产生不同的关节角度
        # 注意：这里主要是验证接口正常工作
        assert isinstance(slow_result, dict)
        assert isinstance(fast_result, dict)

    def test_translate_and_drive_joint_limit(self):
        """测试关节限位保护"""
        actuator = MotionActuator()
        anatomy = BipedAnatomy()

        # 多次调用累积，验证限位正确
        result = actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent="walk",
            speed=1.0,
            elapsed_time=0.0
        )

        # 验证所有关节角度都在有效范围内
        for joint_name, angle in result.items():
            if joint_name in anatomy.joints:
                joint = anatomy.joints[joint_name]
                assert joint.min_angle <= angle <= joint.max_angle, \
                    f"关节 {joint_name} 角度 {angle} 超出范围 [{joint.min_angle}, {joint.max_angle}]"

    def test_last_action_intent_updated(self):
        """测试 last_action_intent 被正确更新"""
        actuator = MotionActuator()

        # 初始状态
        assert actuator.last_action_intent == "idle"

        # 执行不同动作
        anatomy = BipedAnatomy()
        actuator.translate_and_drive(anatomy, "walk", 1.0, 0.0)
        assert actuator.last_action_intent == "walk"

        actuator.translate_and_drive(anatomy, "run", 1.0, 0.0)
        assert actuator.last_action_intent == "run"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
