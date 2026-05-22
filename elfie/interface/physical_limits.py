import logging
from typing import Dict, Any

logger = logging.getLogger("elfie.interface.physical_limits")

class PhysicalLimitsReflex:
    """底层：躯体安全反射弧 (校验皮层行为决策是否超出硬件承受能力边界)"""

    def __init__(self, capabilities_config: Dict[str, Any] = None):
        caps = capabilities_config.get("actuators", {}) if capabilities_config else {}
        self.allowed_motions = caps.get("motion", {}).get("supported_actions", ["mutter"])
        self.physics = capabilities_config.get("physics_limits", {}) if capabilities_config else {}

    def intercept_and_validate(self, action_name: str) -> Dict[str, Any]:
        """
        拦截并校验动作名称是否可行
        :param action_name: 顶层大脑做出的动作选择
        :return: {"allowed": bool, "feedback_error": str}
        """
        # 1. 允许静默/空动作
        if not action_name or action_name == "blink_eyes":
            return {"allowed": True, "feedback_error": ""}

        # 2. 检查是否有企图飞天、潜水的物理幻觉
        if "fly" in action_name.lower() or "jump" in action_name.lower():
            if not self.physics.get("can_fly", False):
                err = "【反射拦截】 躯体能力警报！本物理毛绒玩具不具备抗重力飞行器，无法起飞！"
                logger.error(err)
                return {"allowed": False, "feedback_error": err}
                
        # 3. 校验肢体电机动作是否在注册清单中
        if action_name not in self.allowed_motions:
            err = f"【反射拦截】 肢体约束警告！舵机控制器不支持 '{action_name}' 这一复杂物理动作，无法执行。"
            logger.error(err)
            return {"allowed": False, "feedback_error": err}

        return {"allowed": True, "feedback_error": ""}
