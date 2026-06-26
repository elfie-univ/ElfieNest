from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from runtime.models.groups import DEFAULT_MODEL_GROUPS, resolve_model_key


class RuntimeTaskType(str, Enum):
    CHAT = "chat"
    REASONING = "reasoning"
    VISION = "vision"
    CODE = "code"
    ORGANIZE = "organize"


@dataclass(frozen=True, slots=True)
class FoodPolicyDecision:
    task_type: RuntimeTaskType
    group_key: str
    model_key: str

    def to_dict(self) -> dict[str, str]:
        return {
            "task_type": self.task_type.value,
            "group_key": self.group_key,
            "model_key": self.model_key,
        }


@dataclass(frozen=True, slots=True)
class FoodPolicy:
    task_groups: Mapping[RuntimeTaskType, str]

    def group_for(self, task_type: RuntimeTaskType | str) -> str:
        parsed_task_type = parse_task_type(task_type)
        return self.task_groups[parsed_task_type]


DEFAULT_FOOD_POLICY = FoodPolicy(
    task_groups={
        RuntimeTaskType.CHAT: "coarse",
        RuntimeTaskType.REASONING: "premium",
        RuntimeTaskType.VISION: "vision",
        RuntimeTaskType.CODE: "code",
        RuntimeTaskType.ORGANIZE: "organize",
    }
)


def parse_task_type(task_type: RuntimeTaskType | str) -> RuntimeTaskType:
    if isinstance(task_type, RuntimeTaskType):
        return task_type
    try:
        return RuntimeTaskType(task_type)
    except ValueError:
        return RuntimeTaskType.CHAT


def resolve_food_policy(
    task_type: RuntimeTaskType | str,
    available_model_keys: set[str],
    food_policy: FoodPolicy = DEFAULT_FOOD_POLICY,
) -> FoodPolicyDecision:
    parsed_task_type = parse_task_type(task_type)
    group_key = food_policy.group_for(parsed_task_type)
    group = DEFAULT_MODEL_GROUPS[group_key]
    return FoodPolicyDecision(
        task_type=parsed_task_type,
        group_key=group_key,
        model_key=resolve_model_key(group, available_model_keys),
    )


def task_type_from_prompt(prompt: str) -> RuntimeTaskType:
    if any(keyword in prompt for keyword in ("代码", "脚本", "Python", "bug")):
        return RuntimeTaskType.CODE
    if any(keyword in prompt for keyword in ("整理", "总结", "归纳", "汇总")):
        return RuntimeTaskType.ORGANIZE
    if any(keyword in prompt for keyword in ("图片", "照片", "视觉", "看一下")):
        return RuntimeTaskType.VISION
    if any(keyword in prompt for keyword in ("分析", "推理", "计划", "复杂")):
        return RuntimeTaskType.REASONING
    return RuntimeTaskType.CHAT
