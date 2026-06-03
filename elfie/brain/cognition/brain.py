import logging
import random
from typing import Any

from elfie.brain.cognition.attention_manager import AttentionManager
from elfie.brain.cognition.expectation import ExpectationManager
from elfie.brain.cognition.profile import ElfieProfile

logger = logging.getLogger("elfie.cognition.brain")


class NeocortexBrain:
    """顶层：大脑皮层 (认知、决策与主思考网络)"""

    def __init__(self, config_dir: str = None):
        self.profile = ElfieProfile(config_dir)
        self.attention = AttentionManager()
        self.expectation = ExpectationManager()

    def think_and_decide(
        self, context: dict[str, Any], runtime_agent: Any
    ) -> dict[str, Any]:
        """
        根据中层丘脑拼装的 Context，进行大脑决策
        :param context: 拼装好的全方位上下文 (包含主人消息、生理体力、杏仁核实时情绪、海马体记忆切片、底层环境感官)
        :param runtime_agent: 绑定的外包大模型算力底座 RuntimeAgent 实例
        :return: 精灵皮层生成的决策字典 (包含 action, speech_text, emotion_impact 等)
        """
        sensors = context.get("sensors", {})
        has_new_msg = sensors.get("has_new_message", False)
        salience_score = sensors.get("salience_score", 0.0)

        # 1. 评估预测加工误差
        pred_error = self.expectation.update_and_calculate_error(sensors)

        # 2. 调度注意力脑网络 (DMN / CEN / SN)
        active_network = self.attention.evaluate_state(has_new_msg, salience_score)
        logger.info(f"🧠 [皮层脑网络激活]: {active_network} 模式。")

        # 3. 自定义系统 Prompt 性格约束
        personality_prompt = self.profile.get_system_prompt_segment()

        # 4. 根据不同注意力脑网络执行不同决策通路
        if active_network == "SN":
            # 突显网络：遭受突发扰动，以最快直觉进行生存反射
            alert_text = (
                f"警告！发生高能物理状态突变！传感器反馈: {sensors}，进行受惊反应决策。"
            )
            logger.warning(f"🚨 突发打断！大脑皮层进行 SN 紧急反响: {alert_text}")

            # 使用本地快速模式，不调用联网工具，直接快速喊出受惊叫声并瑟瑟发抖
            response = runtime_agent.ask(
                prompt=f"{alert_text}\n请以一句话迅速回应物理不适，并在回答中携带一个物理姿态动作，如 [ACTION]wag_tail[/ACTION]。",
                energy=context.get("energy", 100.0),
                task_complexity=2,
            )

            return {
                "action": "wiggle_ears",
                "speech_text": response,
                "attention_mode": "SN",
                "mutter": "(艾菲耳朵竖了起来，十分警惕哒！)",
            }

        elif active_network == "CEN":
            # 中央执行网络：高负荷、专注处理任务，直接调度外挂算力底座 (可能切云端高推理并开启防幻觉工具)
            user_msg = sensors.get("user_message", "")

            # 包装丘脑汇聚的多维度 Prompt-Context
            full_prompt = (
                f"【系统性格与机体边界设定】:\n{personality_prompt}\n\n"
                f"【当前的生理与情绪状态】:\n"
                f"- 杏仁核情绪状态: {context.get('emotion_state', '平静')}\n"
                f"- 下丘脑体能值: {context.get('energy', 100.0)}% (灵币充沛度)\n\n"
                f"【海马体历史情景记忆】:\n{context.get('history_episodes', '无相关记忆')}\n\n"
                f"【主人发送的信息】:\n{user_msg}\n\n"
                f"请结合你的性格、情感与记忆，给主人做出最符合艾菲傲娇个性的回复。\n"
                f"你可以通过 `[ACTION]支持动作[/ACTION]` 来指示躯体电机摇尾巴(wag_tail)或动耳朵(wiggle_ears)等动作。"
            )

            # 评定复杂度，如果是包含数字、账单或搜索需求的，提示路由切换深度思考
            complexity = 1
            if "计算" in user_msg or "账单" in user_msg or "最新" in user_msg:
                complexity = 4

            response = runtime_agent.ask(
                prompt=full_prompt,
                energy=context.get("energy", 100.0),
                task_complexity=complexity,
            )

            # 解析可能的动作标签
            action = "nod_head"
            if "[ACTION]" in response:
                action = response.split("[ACTION]")[1].split("[/ACTION]")[0].strip()
                response = response.replace(f"[ACTION]{action}[/ACTION]", "")

            return {
                "action": action,
                "speech_text": response,
                "attention_mode": "CEN",
                "mutter": None,
            }

        else:  # DMN Mode
            # 默认发呆模式：要么主动出击（预测误差大），要么陷入自我发呆或碎碎念
            if self.expectation.should_take_active_action(pred_error):
                # 产生主动交互欲望 (主动找事干)
                logger.info("🔮 预测误差过大！触发主动社交欲望 (DMN 主动模式)")
                active_prompt = (
                    f"【系统设定】:\n{personality_prompt}\n"
                    f"当前的预测误差很大，说明环境有异样。请你以艾菲小狐狸的身份，主动跟主人发起一句生动的对话（比如问问天气，或是吐槽网络不稳定），并搭配动作。"
                )
                response = runtime_agent.ask(
                    prompt=active_prompt,
                    energy=context.get("energy", 100.0),
                    task_complexity=2,
                )
                return {
                    "action": "wag_tail",
                    "speech_text": response,
                    "attention_mode": "DMN_ACTIVE",
                    "mutter": "(脑内预测误差增大，艾菲主动搭讪哒！)",
                }

            # 常规胡思乱想/碎碎念
            mood = context.get("emotion_mood", "bored")
            mutter_templates = self.profile.get_mutter_templates(mood)
            selected_mutter = random.choice(mutter_templates)

            return {
                "action": "blink_eyes",
                "speech_text": "",
                "attention_mode": "DMN_IDLE",
                "mutter": selected_mutter,
            }
