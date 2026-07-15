"""
解剖学模块测试
测试 VoiceProfile, JointLimit, SomaticAnatomy, BipedAnatomy, QuadrupedAnatomy
"""

import math
import unittest

from elfie.body.anatomy.base import JointLimit, SomaticAnatomy, VoiceProfile
from elfie.body.anatomy.biped import BipedAnatomy
from elfie.body.anatomy.quadruped import QuadrupedAnatomy


class TestVoiceProfile(unittest.TestCase):
    """VoiceProfile 声学特性曲线测试"""

    def test_default_initialization(self):
        """测试默认初始化"""
        vp = VoiceProfile()
        self.assertEqual(vp.pitch, 1.0)
        self.assertEqual(vp.speed, 1.0)
        self.assertEqual(vp.timbre, "cute")
        self.assertIsInstance(vp.frequency_curve, list)
        self.assertEqual(len(vp.frequency_curve), 10)

    def test_custom_initialization(self):
        """测试自定义参数初始化"""
        freq_curve = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]
        vp = VoiceProfile(
            pitch=1.5, speed=0.8, timbre="deep", frequency_curve=freq_curve
        )
        self.assertEqual(vp.pitch, 1.5)
        self.assertEqual(vp.speed, 0.8)
        self.assertEqual(vp.timbre, "deep")
        self.assertEqual(vp.frequency_curve, freq_curve)

    def test_to_dict(self):
        """测试转换为字典"""
        vp = VoiceProfile(pitch=1.2, speed=0.9, timbre="bright")
        result = vp.to_dict()
        self.assertIn("pitch", result)
        self.assertIn("speed", result)
        self.assertIn("timbre", result)
        self.assertIn("frequency_curve", result)
        self.assertEqual(result["pitch"], 1.2)
        self.assertEqual(result["speed"], 0.9)
        self.assertEqual(result["timbre"], "bright")


class TestJointLimit(unittest.TestCase):
    """JointLimit 关节限位测试"""

    def test_initialization(self):
        """测试初始化"""
        jl = JointLimit("test_joint", -1.57, 1.57, 0.5)
        self.assertEqual(jl.name, "test_joint")
        self.assertEqual(jl.min_angle, -1.57)
        self.assertEqual(jl.max_angle, 1.57)
        self.assertEqual(jl.current_angle, 0.5)

    def test_set_angle_within_range(self):
        """测试设置角度在有效范围内"""
        jl = JointLimit("test_joint", -1.57, 1.57)
        result = jl.set_angle(0.5)
        self.assertEqual(result, 0.5)
        self.assertEqual(jl.current_angle, 0.5)

    def test_set_angle_below_min(self):
        """测试设置角度低于最小值 - 应截断到最小值"""
        jl = JointLimit("test_joint", -1.57, 1.57)
        result = jl.set_angle(-2.0)
        self.assertEqual(result, -1.57)
        self.assertEqual(jl.current_angle, -1.57)

    def test_set_angle_above_max(self):
        """测试设置角度高于最大值 - 应截断到最大值"""
        jl = JointLimit("test_joint", -1.57, 1.57)
        result = jl.set_angle(2.0)
        self.assertEqual(result, 1.57)
        self.assertEqual(jl.current_angle, 1.57)

    def test_set_angle_at_boundaries(self):
        """测试边界值"""
        jl = JointLimit("test_joint", -1.57, 1.57)
        self.assertEqual(jl.set_angle(-1.57), -1.57)
        self.assertEqual(jl.set_angle(1.57), 1.57)

    def test_to_dict(self):
        """测试转换为字典"""
        jl = JointLimit("test_joint", -1.0, 2.0, 0.5)
        result = jl.to_dict()
        self.assertEqual(result["name"], "test_joint")
        self.assertEqual(result["min_angle"], -1.0)
        self.assertEqual(result["max_angle"], 2.0)
        self.assertEqual(result["current_angle"], 0.5)


class TestSomaticAnatomy(unittest.TestCase):
    """SomaticAnatomy 基类测试"""

    def test_default_initialization(self):
        """测试默认初始化"""

        class TestAnatomy(SomaticAnatomy):
            def setup_skeleton(self):
                self.add_joint("test_joint", -1.0, 1.0)

        anatomy = TestAnatomy("res://test.gltf")
        self.assertEqual(anatomy.gltf_path, "res://test.gltf")
        self.assertIsInstance(anatomy.voice_profile, VoiceProfile)
        self.assertIsInstance(anatomy.joints, dict)

    def test_custom_voice_profile(self):
        """测试自定义语音配置"""
        vp = VoiceProfile(pitch=1.5, timbre="deep")
        anatomy = SomaticAnatomy("res://test.gltf", voice_profile=vp)
        self.assertEqual(anatomy.voice_profile.pitch, 1.5)
        self.assertEqual(anatomy.voice_profile.timbre, "deep")

    def test_add_joint(self):
        """测试添加关节"""
        anatomy = SomaticAnatomy("res://test.gltf")
        anatomy.add_joint("neck", -0.5, 0.8, 0.1)
        self.assertIn("neck", anatomy.joints)
        self.assertIsInstance(anatomy.joints["neck"], JointLimit)

    def test_get_joint_angles(self):
        """测试获取所有关节角度"""

        class TestAnatomy(SomaticAnatomy):
            def setup_skeleton(self):
                self.add_joint("joint_a", -1.0, 1.0, 0.3)
                self.add_joint("joint_b", -0.5, 0.5, 0.2)

        anatomy = TestAnatomy("res://test.gltf")
        angles = anatomy.get_joint_angles()
        self.assertEqual(angles["joint_a"], 0.3)
        self.assertEqual(angles["joint_b"], 0.2)

    def test_apply_joint_angles(self):
        """测试应用关节角度并验证限位"""

        class TestAnatomy(SomaticAnatomy):
            def setup_skeleton(self):
                self.add_joint("joint_a", -1.0, 1.0)
                self.add_joint("joint_b", -0.5, 0.5)

        anatomy = TestAnatomy("res://test.gltf")

        # 正常值
        actual = anatomy.apply_joint_angles({"joint_a": 0.5, "joint_b": 0.3})
        self.assertEqual(actual["joint_a"], 0.5)
        self.assertEqual(actual["joint_b"], 0.3)

        # 超出上限 - 应被截断
        actual = anatomy.apply_joint_angles({"joint_a": 2.0, "joint_b": 0.3})
        self.assertEqual(actual["joint_a"], 1.0)  # 被截断到 max

        # 超出下限 - 应被截断
        actual = anatomy.apply_joint_angles({"joint_a": -2.0, "joint_b": 0.3})
        self.assertEqual(actual["joint_a"], -1.0)  # 被截断到 min

    def test_apply_joint_angles_unknown_joint(self):
        """测试应用未知关节角度 - 应被忽略"""

        class TestAnatomy(SomaticAnatomy):
            def setup_skeleton(self):
                self.add_joint("joint_a", -1.0, 1.0)

        anatomy = TestAnatomy("res://test.gltf")
        actual = anatomy.apply_joint_angles({"unknown_joint": 0.5})
        self.assertEqual(actual, {})  # 未知关节被忽略

    def test_get_anatomy_descriptor(self):
        """测试获取完整解剖学描述"""

        class TestAnatomy(SomaticAnatomy):
            def setup_skeleton(self):
                self.add_joint("joint_a", -1.0, 1.0)

        anatomy = TestAnatomy("res://test.gltf")
        descriptor = anatomy.get_anatomy_descriptor()

        self.assertIn("gltf_path", descriptor)
        self.assertIn("voice_profile", descriptor)
        self.assertIn("joints", descriptor)
        self.assertEqual(descriptor["gltf_path"], "res://test.gltf")


class TestBipedAnatomy(unittest.TestCase):
    """BipedAnatomy 双足形态测试"""

    def test_default_initialization(self):
        """测试默认初始化"""
        anatomy = BipedAnatomy()
        self.assertEqual(
            anatomy.gltf_path, "res://characters/elfie/elfie_3d.tscn"
        )
        self.assertIsInstance(anatomy.voice_profile, VoiceProfile)

    def test_custom_gltf_path(self):
        """测试自定义模型路径"""
        anatomy = BipedAnatomy(gltf_path="res://custom/model.gltf")
        self.assertEqual(anatomy.gltf_path, "res://custom/model.gltf")

    def test_setup_skeleton(self):
        """测试骨骼初始化 - 验证所有关节存在"""
        anatomy = BipedAnatomy()

        # 头部关节
        self.assertIn("head_yaw", anatomy.joints)
        self.assertIn("neck_pitch", anatomy.joints)

        # 上肢关节
        self.assertIn("left_shoulder", anatomy.joints)
        self.assertIn("right_shoulder", anatomy.joints)

        # 下肢关节
        self.assertIn("left_hip", anatomy.joints)
        self.assertIn("right_hip", anatomy.joints)
        self.assertIn("left_knee", anatomy.joints)
        self.assertIn("right_knee", anatomy.joints)

    def test_joint_limits(self):
        """测试关节限位值正确"""
        anatomy = BipedAnatomy()

        # head_yaw: -1.57 ~ 1.57 (90度)
        self.assertAlmostEqual(
            anatomy.joints["head_yaw"].min_angle, -math.pi / 2, places=2
        )
        self.assertAlmostEqual(
            anatomy.joints["head_yaw"].max_angle, math.pi / 2, places=2
        )

        # knee: 0 ~ 2.3 (只能向后弯曲)
        self.assertEqual(anatomy.joints["left_knee"].min_angle, 0.0)
        self.assertEqual(anatomy.joints["left_knee"].max_angle, 2.3)

    def test_get_style_tag(self):
        """测试获取形态标签"""
        anatomy = BipedAnatomy()
        self.assertEqual(anatomy.get_style_tag(), "Bipedal (Humanoid)")


class TestQuadrupedAnatomy(unittest.TestCase):
    """QuadrupedAnatomy 四足形态测试"""

    def test_default_initialization(self):
        """测试默认初始化"""
        anatomy = QuadrupedAnatomy()
        self.assertEqual(anatomy.gltf_path, "res://assets/models/quadruped_elfie.gltf")
        self.assertIsInstance(anatomy.voice_profile, VoiceProfile)

    def test_custom_gltf_path(self):
        """测试自定义模型路径"""
        anatomy = QuadrupedAnatomy(gltf_path="res://custom/quadruped.gltf")
        self.assertEqual(anatomy.gltf_path, "res://custom/quadruped.gltf")

    def test_setup_skeleton(self):
        """测试骨骼初始化 - 验证所有关节存在"""
        anatomy = QuadrupedAnatomy()

        # 头部关节
        self.assertIn("head_yaw", anatomy.joints)
        self.assertIn("neck_pitch", anatomy.joints)

        # 尾巴关节 (四足特有)
        self.assertIn("tail_wag", anatomy.joints)

        # 四肢关节
        self.assertIn("front_left_leg", anatomy.joints)
        self.assertIn("front_right_leg", anatomy.joints)
        self.assertIn("back_left_leg", anatomy.joints)
        self.assertIn("back_right_leg", anatomy.joints)

    def test_joint_limits(self):
        """测试关节限位值正确"""
        anatomy = QuadrupedAnatomy()

        # tail_wag: -1.0 ~ 1.0
        self.assertEqual(anatomy.joints["tail_wag"].min_angle, -1.0)
        self.assertEqual(anatomy.joints["tail_wag"].max_angle, 1.0)

        # 四肢限位
        self.assertEqual(anatomy.joints["front_left_leg"].min_angle, -1.2)
        self.assertEqual(anatomy.joints["front_left_leg"].max_angle, 1.2)

    def test_get_style_tag(self):
        """测试获取形态标签"""
        anatomy = QuadrupedAnatomy()
        self.assertEqual(anatomy.get_style_tag(), "Quadrupedal (Animal)")


class TestAnatomyInheritance(unittest.TestCase):
    """解剖学类继承关系测试"""

    def test_biped_inherits_somatic(self):
        """验证 BipedAnatomy 继承自 SomaticAnatomy"""
        self.assertTrue(issubclass(BipedAnatomy, SomaticAnatomy))

    def test_quadruped_inherits_somatic(self):
        """验证 QuadrupedAnatomy 继承自 SomaticAnatomy"""
        self.assertTrue(issubclass(QuadrupedAnatomy, SomaticAnatomy))

    def test_biped_inherits_base_methods(self):
        """验证双足类继承基类方法"""
        anatomy = BipedAnatomy()

        # 测试继承的 get_joint_angles
        angles = anatomy.get_joint_angles()
        self.assertIsInstance(angles, dict)

        # 测试继承的 apply_joint_angles
        actual = anatomy.apply_joint_angles({"head_yaw": 0.5})
        self.assertIn("head_yaw", actual)

        # 测试继承的 get_anatomy_descriptor
        descriptor = anatomy.get_anatomy_descriptor()
        self.assertIn("gltf_path", descriptor)
        self.assertIn("joints", descriptor)

    def test_quadruped_inherits_base_methods(self):
        """验证四足类继承基类方法"""
        anatomy = QuadrupedAnatomy()

        # 测试继承的 get_joint_angles
        angles = anatomy.get_joint_angles()
        self.assertIsInstance(angles, dict)

        # 测试继承的 apply_joint_angles
        actual = anatomy.apply_joint_angles({"tail_wag": 0.5})
        self.assertIn("tail_wag", actual)

        # 测试继承的 get_anatomy_descriptor
        descriptor = anatomy.get_anatomy_descriptor()
        self.assertIn("gltf_path", descriptor)
        self.assertIn("joints", descriptor)


if __name__ == "__main__":
    unittest.main()
