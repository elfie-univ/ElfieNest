import logging
import math

from elfie.body.anatomy.base import SomaticAnatomy
from elfie.body.anatomy.biped import BipedAnatomy
from elfie.body.anatomy.quadruped import QuadrupedAnatomy

logger = logging.getLogger("elfie.body.actuators.gait")


class GaitEngine:
    """小脑步态与运动学协同引擎 (CPG Central Pattern Generator Wave Form)"""

    def __init__(self):
        # 内部相角累积器
        self.phase = 0.0

    def generate_step_angles(
        self, anatomy: SomaticAnatomy, gait_type: str, speed: float, elapsed_time: float
    ) -> dict[str, float]:
        """
        根据当前步态类型、速度和累计时间，计算各关节的目标旋转弧度序列
        :param anatomy: 精灵形态解剖实例 (SomaticAnatomy)
        :param gait_type: 动作类型 ("walk", "run", "idle", "wave_hands", "wag_tail")
        :param speed: 动作运动速度因子 (0.0 到 2.0)
        :param elapsed_time: 自仿真开始累积的运行总秒数 (s)
        :return: 关节角度控制字典 (Dict[joint_name, angle_radian])
        """
        angles = {}

        # 频率因子：运动速度越快，正弦波摆动频率越高
        freq = 2.0 * speed if speed > 0 else 1.0
        # 基础正弦震荡波
        t = elapsed_time * freq

        if gait_type == "idle":
            # 呼吸起伏：胸腔与头部极其细微的上下呼吸波动
            angles["neck_pitch"] = 0.05 * math.sin(2.0 * math.pi * 0.25 * elapsed_time)
            if "head_yaw" in anatomy.joints:
                angles["head_yaw"] = 0.0
            if "tail_wag" in anatomy.joints:
                angles["tail_wag"] = 0.05 * math.sin(
                    2.0 * math.pi * 0.1 * elapsed_time
                )  # 尾巴微摇
            return angles

        # A. 双足直立步态解算
        if isinstance(anatomy, BipedAnatomy):
            if gait_type in ["walk", "run"]:
                amplitude = 0.6 if gait_type == "run" else 0.35  # 摆幅

                # 对称迈步摆动 (左大腿与右大腿呈反相位, 左膝盖在特定角度弯曲)
                angles["left_hip"] = amplitude * math.sin(t)
                angles["right_hip"] = -amplitude * math.sin(t)

                # 双脚摆动时，双臂需要反相协调摆动 (左臂与右脚同相位，右臂与左脚同相位)
                angles["left_shoulder"] = 0.5 * amplitude * math.sin(t + math.pi)
                angles["right_shoulder"] = 0.5 * amplitude * math.sin(t)

                # 膝盖随大腿运动有节奏地自然屈伸 (取正值，膝盖只能向后收缩)
                angles["left_knee"] = abs(amplitude * 1.2 * math.sin(t - math.pi / 4))
                angles["right_knee"] = abs(
                    amplitude * 1.2 * math.sin(t + math.pi - math.pi / 4)
                )

                # 头部轻微随步态左右颠簸
                angles["head_yaw"] = 0.08 * math.sin(2 * t)
                angles["neck_pitch"] = 0.05 * math.cos(2 * t)

            elif gait_type == "wave_hands":
                # 欢乐挥手动作：肩膀上下小幅摆，手肘手臂大幅招手
                angles["left_shoulder"] = 1.2 + 0.3 * math.sin(8.0 * elapsed_time)
                angles["right_shoulder"] = -0.5 * math.sin(1.0 * elapsed_time)

        # B. 四足爬行步态解算 (如小狗 Trot 步态)
        elif isinstance(anatomy, QuadrupedAnatomy):
            if gait_type in ["walk", "run"]:
                amplitude = 0.7 if gait_type == "run" else 0.4

                # Trot 对角小跑：前左腿与后右腿同相；前右腿与后左腿同相且相差180度
                angles["front_left_leg"] = amplitude * math.sin(t)
                angles["back_right_leg"] = amplitude * math.sin(t)

                angles["front_right_leg"] = amplitude * math.sin(t + math.pi)
                angles["back_left_leg"] = amplitude * math.sin(t + math.pi)

                # 尾巴随着快步轻快摇摆
                angles["tail_wag"] = 0.5 * amplitude * math.sin(1.5 * t)

                # 头部上下起伏
                angles["neck_pitch"] = 0.1 * math.cos(t)

            elif gait_type == "wag_tail":
                # 极快开心摇尾巴
                angles["tail_wag"] = 0.8 * math.sin(12.0 * elapsed_time)
                angles["head_yaw"] = 0.1 * math.sin(2.0 * elapsed_time)

        return angles
