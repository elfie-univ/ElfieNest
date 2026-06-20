import math
import sys
import unittest

# 将工程路径引入 Python path
sys.path.insert(0, "/Users/zhenli/git-code/ElfieNest")

from elfie import ElfieIndividual
from elfie.body import BipedAnatomy
from runtime.agent import RuntimeAgent
from runtime.config import LLMRuntimeConfig


class TestEmbodiedPerception(unittest.TestCase):
    def setUp(self):
        # 1. 模拟初始化一个 RuntimeAgent
        self.config = LLMRuntimeConfig()
        self.agent = RuntimeAgent(self.config)

    def test_joint_safety_limits(self):
        """测试 1：数字孪生躯壳关节旋转极限与安全弧度阶段 (Joint Limit Protection)"""
        # 以双足直立形象为例
        anatomy = BipedAnatomy()

        # 头部摇头 head_yaw 极限为 [-1.57, 1.57] 弧度
        # 我们企图将其旋转 3.14 Radian (180度，这会拧断小精灵的脖子！)
        actual_yaw = anatomy.joints["head_yaw"].set_angle(3.14)

        # 验证被物理安全截断在最大活动限位 1.57 弧度
        self.assertAlmostEqual(actual_yaw, 1.57)
        self.assertAlmostEqual(anatomy.joints["head_yaw"].current_angle, 1.57)

        # 企图向左拧 -2.5 弧度
        actual_yaw = anatomy.joints["head_yaw"].set_angle(-2.5)
        # 验证被限制在 -1.57 弧度
        self.assertAlmostEqual(actual_yaw, -1.57)

        # 膝关节只能向后弯曲 (限制在 [0.0, 2.3] 弧度)
        # 企图反向反物理弯曲膝盖 -1.0 弧度
        actual_knee = anatomy.joints["left_knee"].set_angle(-1.0)
        self.assertAlmostEqual(actual_knee, 0.0)

    def test_morphological_restrictions(self):
        """测试 2：交互总线形态学拦截 (Morphological Restrictions Against Illusion Actions)"""
        # (A) 实例化双足精灵
        biped_elfie = ElfieIndividual(anatomy_type="biped")

        # 提供一个有变化的 user_message，防止被感知大坝过滤
        sensor_data = {"has_new_message": True, "user_message": "摇尾巴指令请求"}

        # 模拟大脑产出动作意图 "wag_tail" 动作标签，以契合皮层动作剥离机制
        class MockBipedAgent:
            class MockConfig:
                remote_api_key = ""
                providers = {
                    "deepseek": {"api_key": "", "api_base": ""},
                    "openai": {"api_key": "", "api_base": ""},
                    "gemini": {"api_key": "", "api_base": ""},
                    "qwen": {"api_key": "", "api_base": ""},
                    "ollama": {"api_key": "", "api_base": "http://localhost:11434"},
                }

            config = MockConfig()

            def ask(self, *args, **kwargs):
                return "我是一只快乐的小狐狸，我要摇尾巴！ [ACTION]wag_tail[/ACTION]"

        response = biped_elfie.perceive_and_respond(sensor_data, MockBipedAgent())

        # 验证该动作被拦截，强制转为 nod_head (点头动作)，并泵入焦虑感，修改言语
        self.assertEqual(response["action"], "nod_head")
        self.assertIn("形态学限制", response["speech"])
        self.assertIn("动作因形态学不兼容被强行拦截了", response["mutter"])

        # 验证杏仁核情绪扰动 (焦虑值上升，anxiety -> fear)
        self.assertGreater(biped_elfie.amygdala.emotions["fear"], 10.0)

        # (B) 实例化四足爬行精灵
        quad_elfie = ElfieIndividual(anatomy_type="quadruped")

        # 重新配置 sensor_data 规避大坝缓存
        sensor_data_quad = {"has_new_message": True, "user_message": "挥手动作请求"}

        class MockQuadAgent:
            class MockConfig:
                remote_api_key = ""
                providers = {
                    "deepseek": {"api_key": "", "api_base": ""},
                    "openai": {"api_key": "", "api_base": ""},
                    "gemini": {"api_key": "", "api_base": ""},
                    "qwen": {"api_key": "", "api_base": ""},
                    "ollama": {"api_key": "", "api_base": "http://localhost:11434"},
                }

            config = MockConfig()

            def ask(self, *args, **kwargs):
                return "主人你好呀，我给你挥手致敬！ [ACTION]wave_hands[/ACTION]"

        response_quad = quad_elfie.perceive_and_respond(
            sensor_data_quad, MockQuadAgent()
        )

        # 验证动作被硬性拦截
        self.assertEqual(response_quad["action"], "nod_head")
        self.assertIn("形态学限制", response_quad["speech"])

    def test_cerebellar_gait_cpg(self):
        """测试 3：小脑时域步态协同正弦解算 (Cerebellar Gait Engine CPG Generator)"""
        # 以双足精灵直立行走为例
        elfie = ElfieIndividual(anatomy_type="biped")

        # 模拟在 0.5s 时大腿和肩膀的关节相位
        # 时间流动 0.5 秒，速度 1.0
        joints_t05 = elfie.motion_actuator.translate_and_drive(
            anatomy=elfie.anatomy, action_intent="walk", speed=1.0, elapsed_time=0.5
        )

        # 模拟 0.5s 时的迈腿相位： 左大腿 (left_hip) 与 右大腿 (right_hip) 应处于反相正向正弦波
        left_hip = joints_t05["left_hip"]
        right_hip = joints_t05["right_hip"]

        # 校验方向相反
        self.assertTrue(
            (left_hip > 0 and right_hip < 0) or (left_hip < 0 and right_hip > 0)
        )

        # 模拟 0.5s 时的摆臂： 左臂与左脚反相位，左肩 (left_shoulder) 与右大腿同相位
        left_shoulder = joints_t05["left_shoulder"]
        self.assertEqual(
            math.copysign(1.0, left_shoulder), math.copysign(1.0, right_hip)
        )

    def test_brainstem_avoidance_reflex(self):
        """测试 4：脑干紧急激烈碰撞避险自主反射 (Brainstem Avoidance Shock Reflex)"""
        elfie = ElfieIndividual(anatomy_type="quadruped")  # 四足小狐狸

        # 模拟来自 Godot 物理宿舍床脚 of 突发猛烈侧向碰撞 (撞击力 25.0 > 15.0，来源: right)
        sensor_data = {
            "has_new_message": False,
            "impact_force": 25.0,
            "impact_direction": "right",
            "gentle_stroke": 0.0,
        }

        # 由于是毫秒级脑干反射，应该直接触发避险反射，不调用大模型思考，极速响应
        response = elfie.perceive_and_respond(sensor_data, self.agent)

        # 验证瞬间返回了避险动作与痛叫，绕过了皮层大模型
        self.assertEqual(response["action"], "reflex_avoidance")
        self.assertIn("shock_avoidance", response["mutter"])
        self.assertIn("自卫收缩反射", response["speech"])
        self.assertIn("痛痛痛", response["speech"])

        # 验证四腿关节被反射弧强制回缩限制
        self.assertEqual(response["joint_angles"]["front_left_leg"], -0.5)
        self.assertEqual(response["joint_angles"]["front_right_leg"], -0.5)

        # 验证情绪系统受到警报：焦虑度 (anxiety->fear) 瞬间暴涨，快乐度骤降
        self.assertGreater(elfie.amygdala.emotions["fear"], 20.0)
        self.assertLess(elfie.amygdala.emotions["happiness"], 50.0)

        # 验证海马体成功载入紧急痛觉反射事件
        recent_memory = [ep["content"] for ep in elfie.hippocampus.get_all_episodes()]
        recent_memory_str = " ".join(recent_memory)
        self.assertIn("脑干反射", recent_memory_str)

    def test_brainstem_stroke_reflex(self):
        """测试 5：脑干温柔抚摸摇尾舒适反射 (Tactile Stroke Soothing Reflex)"""
        elfie = ElfieIndividual(anatomy_type="quadruped")

        # 模拟主人在屏幕/面板上以 1.2Hz 的平缓频率轻柔抚摸精灵
        sensor_data = {
            "has_new_message": False,
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 1.2,  # 1.2 Hz Comfort Frequency
        }

        response = elfie.perceive_and_respond(sensor_data, self.agent)

        # 验证触发了舒适抚摸摇尾打呼反射
        self.assertEqual(response["action"], "reflex_soothing")
        self.assertIn("尾巴自己都不听话地摇摆起来了哒", response["speech"])
        self.assertIn("stroke_soothing", response["mutter"])

        # 验证关节成功摇尾巴 (tail_wag = 0.8)
        self.assertEqual(response["joint_angles"]["tail_wag"], 0.8)

        # 验证杏仁核情绪池极度舒缓：焦虑值(anxiety->fear)清零，快乐值暴涨
        self.assertEqual(elfie.amygdala.emotions["fear"], 0.0)
        self.assertGreater(elfie.amygdala.emotions["happiness"], 50.0)

    def test_vision_viewport_perception(self):
        """测试 6：多模态虚拟视角大模型决策 (Embodied Vision Pipeline)"""
        elfie = ElfieIndividual(anatomy_type="biped")

        mock_image_path = "/tmp/dormitory_door_viewport.png"

        # 1. 神经总线 Vision 传感器接收这张 3D 视口照片，并做解析
        _ = elfie.speech_actuator.synthesize_speech(
            "眼前的红木门紧闭着哒", elfie.anatomy.voice_profile
        )

        # 2. 灌入视口输入并 mock ask 方法
        class MockVLMObserverAgent:
            class MockConfig:
                remote_api_key = ""
                providers = {
                    "deepseek": {"api_key": "", "api_base": ""},
                    "openai": {"api_key": "", "api_base": ""},
                    "gemini": {"api_key": "", "api_base": ""},
                    "qwen": {"api_key": "", "api_base": ""},
                    "ollama": {"api_key": "", "api_base": "http://localhost:11434"},
                }

            config = MockConfig()

            def ask(self, *args, **kwargs):
                return "我看到前方有一扇紧闭的宿舍红木门哒，我得走过去看个究竟！ [ACTION]walk[/ACTION]"

        sensor_data = {
            "has_new_message": True,
            "user_message": "看看你的前面有什么？",
            "viewport_image_path": mock_image_path,
            "impact_force": 0.0,
            "gentle_stroke": 0.0,
        }

        response = elfie.perceive_and_respond(sensor_data, MockVLMObserverAgent())

        # 验证精灵读懂了视觉，做出了 'walk' 行动的宏观决策
        self.assertEqual(response["action"], "walk")
        self.assertIn("红木门", response["speech"])

        # 验证在 CEN 模式（专注任务思考中）下，大脑不吐出 mutter 发呆碎碎念，契合皮层 DMN/CEN 调度规范
        self.assertIsNone(response["mutter"])

        # 验证小脑步态开始协同计算迈腿姿态，并返回了有效的时序关节输出
        self.assertIn("left_hip", response["joint_angles"])
        self.assertIn("right_hip", response["joint_angles"])


if __name__ == "__main__":
    unittest.main()
