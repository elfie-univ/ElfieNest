# -*- coding: utf-8 -*-
"""反射弧模块测试 (Reflex Arc Module Tests)"""
import sys
import unittest

sys.path.insert(0, "/Users/zhenli/git-code/ElfieNest")

from elfie.body.reflex.reflex_arc import SomaticReflexArc
from elfie.body.anatomy.base import SomaticAnatomy
from elfie.body.anatomy.biped import BipedAnatomy
from elfie.body.anatomy.quadruped import QuadrupedAnatomy
from elfie.brain.emotion.emotional_state import AmygdalaEmotionalState


class TestSomaticReflexArc(unittest.TestCase):
    """测试 SomaticReflexArc 反射弧类"""

    def setUp(self):
        """测试前准备"""
        self.reflex_arc = SomaticReflexArc()
        self.biped_anatomy = BipedAnatomy()
        self.quad_anatomy = QuadrupedAnatomy()
        self.amygdala = AmygdalaEmotionalState()

    # ==================== 初始化测试 ====================
    def test_init(self):
        """测试 1: 验证 ReflexArc 正常初始化"""
        reflex = SomaticReflexArc()
        self.assertIsInstance(reflex, SomaticReflexArc)

    # ==================== 反射触发测试 ====================
    def test_shock_reflex_triggered(self):
        """测试 2: 验证强撞击触发避险反射"""
        tactile_sensor = {
            "impact_force": 20.0,
            "impact_direction": "front",
            "gentle_stroke": 0.0
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.quad_anatomy, tactile_sensor, self.amygdala
        )

        self.assertTrue(reflex_event["triggered"])
        self.assertEqual(reflex_event["type"], "shock_avoidance")
        self.assertIn("自卫收缩反射", reflex_event["msg"])

    def test_stroke_reflex_triggered(self):
        """测试 3: 验证温柔抚摸触发舒适反射"""
        tactile_sensor = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 1.5
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.quad_anatomy, tactile_sensor, self.amygdala
        )

        self.assertTrue(reflex_event["triggered"])
        self.assertEqual(reflex_event["type"], "stroke_soothing")
        self.assertIn("尾巴", reflex_event["msg"])

    def test_no_reflex_triggered(self):
        """测试 4: 验证无刺激不触发反射"""
        tactile_sensor = {
            "impact_force": 5.0,
            "impact_direction": "none",
            "gentle_stroke": 0.0
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.biped_anatomy, tactile_sensor, self.amygdala
        )

        self.assertFalse(reflex_event["triggered"])
        self.assertIsNone(reflex_event["type"])
        self.assertEqual(reflex_event["msg"], "")

    # ==================== 反射响应测试 ====================
    def test_shock_joints_override_biped(self):
        """测试 5: 验证 biped 形态撞击时关节覆盖"""
        tactile_sensor = {
            "impact_force": 25.0,
            "impact_direction": "back",
            "gentle_stroke": 0.0
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.biped_anatomy, tactile_sensor, self.amygdala
        )

        # biped 形态: neck_pitch, head_yaw, left_knee, right_knee
        self.assertIn("neck_pitch", override_joints)
        self.assertIn("head_yaw", override_joints)
        self.assertEqual(override_joints["neck_pitch"], 0.5)  # 低头
        self.assertEqual(override_joints["head_yaw"], 0.0)    # 摆正

    def test_shock_joints_override_quadruped(self):
        """测试 6: 验证 quadruped 形态撞击时四肢收缩"""
        tactile_sensor = {
            "impact_force": 16.0,
            "impact_direction": "left",
            "gentle_stroke": 0.0
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.quad_anatomy, tactile_sensor, self.amygdala
        )

        # quadruped 形态: 四条腿都应收缩
        for leg in ["front_left_leg", "front_right_leg", "back_left_leg", "back_right_leg"]:
            self.assertIn(leg, override_joints)
            self.assertEqual(override_joints[leg], -0.5)

    def test_stroke_joints_override(self):
        """测试 7: 验证抚摸时关节响应"""
        tactile_sensor = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 1.2
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.quad_anatomy, tactile_sensor, self.amygdala
        )

        self.assertIn("tail_wag", override_joints)
        self.assertEqual(override_joints["tail_wag"], 0.8)
        self.assertIn("neck_pitch", override_joints)

    # ==================== 阈值测试 ====================
    def test_impact_force_threshold(self):
        """测试 8: 验证撞击力阈值边界 (15.0)"""
        # 边界值: 15.1 应该触发 (代码使用 > 15.0)
        tactile_sensor = {
            "impact_force": 15.1,
            "impact_direction": "front",
            "gentle_stroke": 0.0
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.biped_anatomy, tactile_sensor, self.amygdala
        )

        self.assertTrue(reflex_event["triggered"])

    def test_impact_force_below_threshold(self):
        """测试 9: 验证撞击力低于阈值不触发"""
        tactile_sensor = {
            "impact_force": 14.9,
            "impact_direction": "front",
            "gentle_stroke": 0.0
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.biped_anatomy, tactile_sensor, self.amygdala
        )

        self.assertFalse(reflex_event["triggered"])

    def test_stroke_frequency_threshold(self):
        """测试 10: 验证抚摸频率阈值边界 (0.5 - 2.5)"""
        # 下边界: 0.5 应该触发
        tactile_sensor_low = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 0.5
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.quad_anatomy, tactile_sensor_low, self.amygdala
        )

        self.assertTrue(reflex_event["triggered"])

        # 上边界: 2.5 应该触发
        tactile_sensor_high = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 2.5
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.quad_anatomy, tactile_sensor_high, self.amygdala
        )

        self.assertTrue(reflex_event["triggered"])

    def test_stroke_frequency_out_of_range(self):
        """测试 11: 验证抚摸频率超出范围不触发"""
        # 低于下限
        tactile_sensor_low = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 0.3
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.quad_anatomy, tactile_sensor_low, self.amygdala
        )

        self.assertFalse(reflex_event["triggered"])

        # 高于上限
        tactile_sensor_high = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 3.0
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.quad_anatomy, tactile_sensor_high, self.amygdala
        )

        self.assertFalse(reflex_event["triggered"])

    # ==================== 情绪影响测试 ====================
    def test_shock_emotion_impact(self):
        """测试 12: 验证撞击时情绪变化"""
        amygdala = AmygdalaEmotionalState()
        # 初始值: anxiety=10, happiness=50
        tactile_sensor = {
            "impact_force": 30.0,
            "impact_direction": "right",
            "gentle_stroke": 0.0
        }

        self.reflex_arc.process_sensory_impact(
            self.biped_anatomy, tactile_sensor, amygdala
        )

        # anxiety 暴增 25, happiness 下降 15
        self.assertEqual(amygdala.emotions["anxiety"], 35.0)  # 10 + 25
        self.assertEqual(amygdala.emotions["happiness"], 35.0)  # 50 - 15

    def test_stroke_emotion_impact(self):
        """测试 13: 验证抚摸时情绪变化"""
        amygdala = AmygdalaEmotionalState()
        # 初始值: anxiety=10, boredom=20, happiness=50
        tactile_sensor = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 1.0
        }

        self.reflex_arc.process_sensory_impact(
            self.quad_anatomy, tactile_sensor, amygdala
        )

        # anxiety 减少 15, boredom 减少 20, happiness 增加 15
        self.assertEqual(amygdala.emotions["anxiety"], 0.0)  # max(10-15, 0)
        self.assertEqual(amygdala.emotions["boredom"], 0.0)  # max(20-20, 0)
        self.assertEqual(amygdala.emotions["happiness"], 65.0)  # 50 + 15

    # ==================== 边界情况测试 ====================
    def test_missing_tactile_sensor_keys(self):
        """测试 14: 验证缺少传感器键时的默认行为"""
        # 空传感器
        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.biped_anatomy, {}, self.amygdala
        )

        self.assertFalse(reflex_event["triggered"])

    def test_none_amygdala(self):
        """测试 15: 验证 amygdala 为 None 时的处理"""
        tactile_sensor = {
            "impact_force": 20.0,
            "impact_direction": "front",
            "gentle_stroke": 0.0
        }

        # 不应该抛出异常
        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.biped_anatomy, tactile_sensor, None
        )

        self.assertTrue(reflex_event["triggered"])
        self.assertEqual(reflex_event["type"], "shock_avoidance")

    def test_anatomy_without_matching_joints(self):
        """测试 16: 验证解剖结构缺少对应关节时的处理"""
        # biped 没有 tail_wag 关节
        tactile_sensor = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 1.5
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.biped_anatomy, tactile_sensor, self.amygdala
        )

        # 反射仍应触发，只是 tail_wag 不会被添加
        self.assertTrue(reflex_event["triggered"])
        self.assertNotIn("tail_wag", override_joints)

    def test_apply_joint_angles_respects_limits(self):
        """测试 17: 验证 apply_joint_angles 遵守关节限位"""
        # biped left_knee 范围 [0.0, 2.3]，设置超出范围的值
        tactile_sensor = {
            "impact_force": 20.0,
            "impact_direction": "front",
            "gentle_stroke": 0.0
        }

        self.reflex_arc.process_sensory_impact(
            self.biped_anatomy, tactile_sensor, self.amygdala
        )

        # left_knee = 1.5 应该在有效范围内
        self.assertIn("left_knee", self.biped_anatomy.joints)
        self.assertEqual(self.biped_anatomy.joints["left_knee"].current_angle, 1.5)

    def test_multiple_reflex_calls_isolated(self):
        """测试 18: 验证多次反射调用之间状态隔离"""
        amygdala1 = AmygdalaEmotionalState()
        amygdala2 = AmygdalaEmotionalState()

        tactile_shock = {
            "impact_force": 20.0,
            "impact_direction": "front",
            "gentle_stroke": 0.0
        }

        tactile_stroke = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 1.5
        }

        # 第一次调用影响 amygdala1
        self.reflex_arc.process_sensory_impact(
            self.biped_anatomy, tactile_shock, amygdala1
        )

        # 第二次调用影响 amygdala2
        self.reflex_arc.process_sensory_impact(
            self.quad_anatomy, tactile_stroke, amygdala2
        )

        # 两者应该有不同的情绪状态
        self.assertNotEqual(
            amygdala1.emotions["anxiety"],
            amygdala2.emotions["anxiety"]
        )


class TestReflexArcEdgeCases(unittest.TestCase):
    """边界情况额外测试"""

    def setUp(self):
        self.reflex_arc = SomaticReflexArc()
        self.anatomy = BipedAnatomy()
        self.amygdala = AmygdalaEmotionalState()

    def test_extreme_impact_force(self):
        """测试极端撞击力值"""
        tactile_sensor = {
            "impact_force": 1000.0,
            "impact_direction": "back",
            "gentle_stroke": 0.0
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.anatomy, tactile_sensor, self.amygdala
        )

        self.assertTrue(reflex_event["triggered"])
        self.assertEqual(reflex_event["type"], "shock_avoidance")

    def test_both_impact_and_stroke_present(self):
        """测试同时存在撞击和抚摸时的优先级"""
        # 按代码逻辑，impact_force > 15.0 会优先触发
        tactile_sensor = {
            "impact_force": 20.0,
            "impact_direction": "front",
            "gentle_stroke": 1.5  # 满足抚摸条件
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.anatomy, tactile_sensor, self.amygdala
        )

        # 应该触发撞击反射而非抚摸反射
        self.assertTrue(reflex_event["triggered"])
        self.assertEqual(reflex_event["type"], "shock_avoidance")

    def test_zero_all_sensors(self):
        """测试全零传感器值"""
        tactile_sensor = {
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 0.0
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.anatomy, tactile_sensor, self.amygdala
        )

        self.assertFalse(reflex_event["triggered"])

    def test_default_impact_direction(self):
        """测试默认撞击方向"""
        tactile_sensor = {
            "impact_force": 20.0,
            "gentle_stroke": 0.0
        }

        override_joints, reflex_event = self.reflex_arc.process_sensory_impact(
            self.anatomy, tactile_sensor, self.amygdala
        )

        self.assertTrue(reflex_event["triggered"])


if __name__ == "__main__":
    unittest.main()
