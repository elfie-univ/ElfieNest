import logging
from typing import Any

from elfie.body.anatomy.base import SomaticAnatomy
from elfie.body.anatomy.biped import BipedAnatomy
from elfie.body.anatomy.quadruped import QuadrupedAnatomy

logger = logging.getLogger("elfie.interface.physical_limits")


class PhysicalLimitsReflex:
    """神经交互总线：躯体物理限位与形态学拦截反射 (形态学硬拦截，防止大脑运动幻觉)"""

    def __init__(self, capabilities_config: dict[str, Any] = None):
        # 兼容旧版本初始化
        pass

    def intercept_and_validate(
        self, action_name: str, anatomy: SomaticAnatomy
    ) -> dict[str, Any]:
        """
        根据精灵当前具身的 3D 骨架形态，硬性拦截违背形态学规律的大脑行为指令
        :param action_name: 大脑皮层做出的高阶动作选择
        :param anatomy: 当前精灵的 3D 解剖身体形态
        :return: {"allowed": bool, "feedback_error": str}
        """
        if not action_name or action_name in ["blink_eyes", "idle", "nod_head"]:
            return {"allowed": True, "feedback_error": ""}

        # 1. 拦截违背重力的飞天幻觉
        if "fly" in action_name.lower() or "jump" in action_name.lower():
            err = "【物理重力限制】 哎呀！宿舍重力常数是 9.8m/s²，本精灵没有反重力推进器，无法飞起来哒！"
            logger.warning(err)
            return {"allowed": False, "feedback_error": err}

        # 2. 针对双足形态 BipedAnatomy 的物理约束校验
        if isinstance(anatomy, BipedAnatomy):
            if action_name == "wag_tail":
                err = "【形态学限制】 呜呜... 艾菲现在是【双足直立形象】，并没有长出毛茸茸的尾巴，无法执行摇尾巴动作哒！"
                logger.warning(err)
                return {"allowed": False, "feedback_error": err}

        # 3. 针对四足形态 QuadrupedAnatomy 的物理约束校验
        elif isinstance(anatomy, QuadrupedAnatomy):
            if action_name == "wave_hands":
                err = "【形态学限制】 哎呦... 艾菲当前是【四足小狗形象】，四条腿都在地上支撑身体，没有双手可以用来挥手打招呼哒！"
                logger.warning(err)
                return {"allowed": False, "feedback_error": err}

        return {"allowed": True, "feedback_error": ""}
