"""精灵侧的语义粮食选择策略。

这里只表达认知意图，不接触模型、Provider 或推理参数。Runtime 会根据每只
精灵的粮食权限再次校验，因此情绪触发的升级也不会越过管理员配置的上限。
"""

from __future__ import annotations

from dataclasses import dataclass

from elfie.brain.brain_types import BrainContext


@dataclass(frozen=True)
class FoodIntent:
    food_key: str
    scene: str
    allowed_tools: tuple[str, ...] = ()
    reason: str = ""


class ElfieFoodSelector:
    """把注意力、情绪和任务语义转换为稳定的粮食 key。"""

    _TOOL_TERMS = (
        "搜索",
        "查一下",
        "最新",
        "联网",
        "文件",
        "读取",
        "目录",
        "代码",
        "运行",
        "计算",
    )
    _HARD_TERMS = (
        "分析",
        "推理",
        "证明",
        "规划",
        "方案",
        "为什么",
        "账单",
        "复杂",
    )
    _DANGER_MOODS = frozenset({"fear", "anger", "panic", "anxiety"})
    _CREATIVE_TERMS = ("创作", "故事", "诗", "想象", "设计", "灵感")

    def select(self, active_network: str, context: BrainContext) -> FoodIntent:
        message = context.sensors.user_message or ""

        if active_network == "SN":
            return FoodIntent("emergency", "salience", reason="突显网络紧急响应")

        if (
            context.emotion_mood in self._DANGER_MOODS
            and context.emotion_intensity >= 75
        ):
            return FoodIntent("premium", "emotion_peak", reason="高强度危险情绪")

        if any(term in message for term in self._TOOL_TERMS):
            tools = ["local_file", "code_sandbox"]
            if context.sensors.is_network_online:
                tools.insert(0, "web_search")
            return FoodIntent(
                "tool",
                "tool_task",
                tuple(tools),
                "任务包含外部能力调用",
            )

        if any(term in message for term in self._HARD_TERMS):
            return FoodIntent("focus", "reasoning", reason="任务需要集中推理")

        if any(term in message for term in self._CREATIVE_TERMS):
            return FoodIntent("creative", "creative", reason="任务需要创作表达")

        if active_network == "CEN":
            return FoodIntent("standard", "chat", reason="中央执行网络常规对话")

        return FoodIntent("coarse", "background", reason="默认网络主动低成本响应")
