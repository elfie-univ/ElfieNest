from elfie.body.anatomy.base import SomaticAnatomy, VoiceProfile


class QuadrupedAnatomy(SomaticAnatomy):
    """四足爬行精灵形态 (Quadrupedal/Animal Body Schema)"""

    def __init__(
        self,
        gltf_path: str = "res://assets/models/quadruped_elfie.gltf",
        voice_profile: VoiceProfile = None,
    ):
        super().__init__(gltf_path, voice_profile)

    def setup_skeleton(self):
        """
        初始化四足骨骼关节限位 (弧度)
        """
        # 头部与脖子
        self.add_joint("head_yaw", -1.2, 1.2, 0.0)
        self.add_joint("neck_pitch", -0.4, 0.6, 0.0)

        # 尾巴关节： 尾巴可以左右欢乐摆动
        self.add_joint("tail_wag", -1.0, 1.0, 0.0)

        # 前肢关节 (前后大范围跨步摆动)
        self.add_joint("front_left_leg", -1.2, 1.2, 0.0)
        self.add_joint("front_right_leg", -1.2, 1.2, 0.0)

        # 后肢关节
        self.add_joint("back_left_leg", -1.2, 1.2, 0.0)
        self.add_joint("back_right_leg", -1.2, 1.2, 0.0)

    def get_style_tag(self) -> str:
        return "Quadrupedal (Animal)"
