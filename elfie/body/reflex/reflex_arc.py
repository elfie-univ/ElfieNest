import logging
from typing import Any, Dict, Tuple

from elfie.body.anatomy.base import SomaticAnatomy

logger = logging.getLogger("elfie.body.reflex.reflex_arc")


class SomaticReflexArc:
    """脑干自主神经反射弧 (Somatic Brainstem Reflex Arc)"""

    def __init__(self):
        pass

    def process_sensory_impact(
        self, anatomy: SomaticAnatomy, tactile_sensor: Dict[str, Any], amygdala: Any
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        """
        在极短的时间（毫秒级）内处理身体传入的具身刺激脉冲。如触发避险反射，直接越过大脑皮层改写关节角度与情绪！
        :param anatomy: 精灵形态学解剖结构
        :param tactile_sensor: 触觉传感器传入的瞬间脉冲数据, 包括:
                               - "impact_force": 碰撞力度 (float, 0.0 表示无碰撞, > 15.0 表示强烈撞击)
                               - "impact_direction": 碰撞来源方向 (str, "front", "back", "left", "right")
                               - "gentle_stroke": 温柔抚摸频率 (float, 0.0-3.0 Hz, 1.0 左右最舒适)
        :param amygdala: 杏仁核情绪状态机实例 (AmygdalaEmotionalState)
        :return: Tuple[关节紧急干预字典, 反射事件报告]
        """
        override_joints = {}
        reflex_event = {"triggered": False, "type": None, "msg": ""}

        # 1. 🚨 剧烈撞击紧急避险反射 (Somatosensory Shock Reflex)
        impact_force = tactile_sensor.get("impact_force", 0.0)
        if impact_force > 15.0:
            direction = tactile_sensor.get("impact_direction", "front")
            logger.warning(
                f"🚨 [脑干反射弧] 检测到强撞击力度: {impact_force}! 启动毫秒级肌肉收缩避险反射!"
            )

            # 紧急缩头：将脖子和头部关节缩回至安全低头位，防止骨骼破损
            if "neck_pitch" in anatomy.joints:
                override_joints["neck_pitch"] = 0.5  # 低头
            if "head_yaw" in anatomy.joints:
                override_joints["head_yaw"] = 0.0  # 摆正

            # 紧急下蹲/缩腿：降低重心
            if "left_knee" in anatomy.joints and "right_knee" in anatomy.joints:
                override_joints["left_knee"] = 1.5  # 大幅弯曲
                override_joints["right_knee"] = 1.5
            elif "front_left_leg" in anatomy.joints:
                # 四足形态缩紧四肢
                for leg in [
                    "front_left_leg",
                    "front_right_leg",
                    "back_left_leg",
                    "back_right_leg",
                ]:
                    if leg in anatomy.joints:
                        override_joints[leg] = -0.5

            # 直接物理修改关节
            anatomy.apply_joint_angles(override_joints)

            # 神经刺激：恐慌值瞬间暴增，快乐值下降
            if amygdala:
                amygdala.update_emotion("anxiety", 25.0)  # 极度惊慌
                amygdala.update_emotion("happiness", -15.0)  # 快乐骤降

            reflex_event.update(
                {
                    "triggered": True,
                    "type": "shock_avoidance",
                    "msg": f"痛痛痛！突然被从【{direction}】方向狠狠撞了一下，大脑一片空白，身体自动启动了自卫收缩反射哒！",
                }
            )
            return override_joints, reflex_event

        # 2. 🐱 温柔抚摸打呼反射 (Tactile Stroke Soothing Reflex)
        stroke_freq = tactile_sensor.get("gentle_stroke", 0.0)
        if 0.5 <= stroke_freq <= 2.5:
            logger.info(f"❤️ [脑干反射弧] 接收到频率为 {stroke_freq}Hz 的舒适抚摸脉冲")

            # 摇尾巴，或者耸肩膀表现出温顺
            if "tail_wag" in anatomy.joints:
                override_joints["tail_wag"] = 0.8  # 欢乐摆尾
            if "neck_pitch" in anatomy.joints:
                override_joints["neck_pitch"] = -0.2  # 惬意抬起下巴

            # 直接物理修改关节
            anatomy.apply_joint_angles(override_joints)

            # 神经滋养：焦虑与无聊瞬间消散，幸福感极高
            if amygdala:
                amygdala.update_emotion("anxiety", -15.0)  # 宁静
                amygdala.update_emotion("boredom", -20.0)  # 充实
                amygdala.update_emotion("happiness", 15.0)  # 高兴

            reflex_event.update(
                {
                    "triggered": True,
                    "type": "stroke_soothing",
                    "msg": "呼噜噜~ 主人的手抚摸得艾菲超级舒服，尾巴自己都不听话地摇摆起来了哒！",
                }
            )
            return override_joints, reflex_event

        return override_joints, reflex_event
