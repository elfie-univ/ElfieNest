"""Runtime 任务类型识别。

模型和 Provider 不属于此模块。任务只用于选择固定粮食 key，实际模型由
``FoodCatalog`` 配方和 ``FoodExecutor`` 决定。
"""

from __future__ import annotations

from enum import Enum


class RuntimeTaskType(str, Enum):
    CHAT = "chat"
    REASONING = "reasoning"
    VISION = "vision"
    CODE = "code"
    ORGANIZE = "organize"


def task_type_from_prompt(prompt: str) -> RuntimeTaskType:
    """根据输入内容推断粮食任务类型。"""
    if any(keyword in prompt for keyword in ("代码", "脚本", "Python", "bug")):
        return RuntimeTaskType.CODE
    if any(keyword in prompt for keyword in ("整理", "总结", "归纳", "汇总")):
        return RuntimeTaskType.ORGANIZE
    if any(keyword in prompt for keyword in ("图片", "照片", "视觉", "看一下")):
        return RuntimeTaskType.VISION
    if any(keyword in prompt for keyword in ("分析", "推理", "计划", "复杂")):
        return RuntimeTaskType.REASONING
    return RuntimeTaskType.CHAT
