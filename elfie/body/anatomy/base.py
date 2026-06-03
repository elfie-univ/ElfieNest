import logging
from typing import Any, Dict, List

logger = logging.getLogger("elfie.body.anatomy.base")


class VoiceProfile:
    """精灵声音声学特性曲线 profile"""

    def __init__(
        self,
        pitch: float = 1.0,
        speed: float = 1.0,
        timbre: str = "cute",
        frequency_curve: List[float] = None,
    ):
        self.pitch = pitch  # 音高倍率 (0.5 - 2.0)
        self.speed = speed  # 语速倍率 (0.5 - 2.0)
        self.timbre = timbre  # 音色风格描述
        # 频率特性曲线，表示不同赫兹段的共振衰减值 (如 10个频段的 gain 数组)
        self.frequency_curve = frequency_curve or [
            1.0,
            1.2,
            1.5,
            1.3,
            1.0,
            0.8,
            0.7,
            0.9,
            1.1,
            1.0,
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pitch": self.pitch,
            "speed": self.speed,
            "timbre": self.timbre,
            "frequency_curve": self.frequency_curve,
        }


class JointLimit:
    """数字孪生可动关节描述"""

    def __init__(
        self, name: str, min_angle: float, max_angle: float, current_angle: float = 0.0
    ):
        self.name = name
        self.min_angle = min_angle  # 最小旋转弧度 (Radian)
        self.max_angle = max_angle  # 最大旋转弧度 (Radian)
        self.current_angle = current_angle

    def set_angle(self, angle: float) -> float:
        """安全限位设置，超出部分自动截断"""
        if angle < self.min_angle:
            self.current_angle = self.min_angle
        elif angle > self.max_angle:
            self.current_angle = self.max_angle
        else:
            self.current_angle = angle
        return self.current_angle

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "min_angle": self.min_angle,
            "max_angle": self.max_angle,
            "current_angle": round(self.current_angle, 3),
        }


class SomaticAnatomy:
    """身体解剖学形态学定义基类"""

    def __init__(self, gltf_path: str, voice_profile: VoiceProfile = None):
        self.gltf_path = gltf_path  # Godot 项目中 3D 模型的加载资源路径，例如 res://assets/models/elfie.gltf
        self.voice_profile = voice_profile or VoiceProfile()
        self.joints: Dict[str, JointLimit] = {}
        self.setup_skeleton()

    def setup_skeleton(self):
        """抽象方法：子类根据具体的直立/爬行骨架形态进行关节实例化与限位初始化"""
        pass

    def add_joint(
        self, name: str, min_angle: float, max_angle: float, current_angle: float = 0.0
    ):
        self.joints[name] = JointLimit(name, min_angle, max_angle, current_angle)

    def get_joint_angles(self) -> Dict[str, float]:
        return {name: joint.current_angle for name, joint in self.joints.items()}

    def apply_joint_angles(self, angles: Dict[str, float]) -> Dict[str, float]:
        """将外界/小脑计算的角度序列安全灌入关节，并限制在安全范围内"""
        actual_angles = {}
        for name, angle in angles.items():
            if name in self.joints:
                actual_angles[name] = self.joints[name].set_angle(angle)
        return actual_angles

    def get_anatomy_descriptor(self) -> Dict[str, Any]:
        """输出形态学完整描述字典，用于向 Godot 精灵盒发送实例化参数"""
        return {
            "gltf_path": self.gltf_path,
            "voice_profile": self.voice_profile.to_dict(),
            "joints": {name: j.to_dict() for name, j in self.joints.items()},
        }
