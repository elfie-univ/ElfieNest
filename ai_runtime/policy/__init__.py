"""Runtime 任务分类公共入口。"""

from ai_runtime.policy.food_policy import RuntimeTaskType, task_type_from_prompt

__all__ = ["RuntimeTaskType", "task_type_from_prompt"]
