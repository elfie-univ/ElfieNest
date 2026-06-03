from elfie.body.anatomy.base import SomaticAnatomy, VoiceProfile


class BipedAnatomy(SomaticAnatomy):
    """双足直立行走精灵形态 (Humanoid/Biped Body Schema)"""

    def __init__(
        self,
        gltf_path: str = "res://character/eflie_3d.tscn",
        voice_profile: VoiceProfile = None,
    ):
        super().__init__(gltf_path, voice_profile)

    def setup_skeleton(self):
        """
        初始化双足骨骼限位 (弧度 Radian，1.57 Rad 约为 90 度)
        """
        # 头部摇头： 左右各 90 度
        self.add_joint("head_yaw", -1.57, 1.57, 0.0)
        # 脖子仰俯： 仰 30 度，俯 45 度
        self.add_joint("neck_pitch", -0.52, 0.78, 0.0)

        # 左右肩关节活动 (摆臂角度限制)
        self.add_joint("left_shoulder", -2.0, 2.0, 0.0)
        self.add_joint("right_shoulder", -2.0, 2.0, 0.0)

        # 左右髋/大腿关节限位
        self.add_joint("left_hip", -1.0, 1.57, 0.0)
        self.add_joint("right_hip", -1.0, 1.57, 0.0)

        # 左右膝关节限制 (膝盖只能向后弯曲)
        self.add_joint("left_knee", 0.0, 2.3, 0.0)
        self.add_joint("right_knee", 0.0, 2.3, 0.0)

    def get_style_tag(self) -> str:
        return "Bipedal (Humanoid)"
