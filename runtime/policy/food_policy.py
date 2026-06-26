from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from runtime.models.groups import DEFAULT_MODEL_GROUPS, ModelGroup, resolve_model_key


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


def load_food_policy(runtime_policy: Mapping[str, Any] | None = None) -> FoodPolicy:
    task_groups = dict(DEFAULT_FOOD_POLICY.task_groups)
    if runtime_policy is None:
        return FoodPolicy(task_groups=task_groups)

    raw_routes = runtime_policy.get("task_routes", {})
    if not isinstance(raw_routes, Mapping):
        return FoodPolicy(task_groups=task_groups)

    for raw_task_type, raw_group_key in raw_routes.items():
        if not isinstance(raw_group_key, str):
            continue
        match raw_task_type:
            case RuntimeTaskType():
                parsed_task_type = raw_task_type
            case str():
                try:
                    parsed_task_type = RuntimeTaskType(raw_task_type)
                except ValueError:
                    continue
            case _:
                continue
        task_groups[parsed_task_type] = raw_group_key

    return FoodPolicy(task_groups=task_groups)


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
    model_groups: Mapping[str, ModelGroup] = DEFAULT_MODEL_GROUPS,
) -> FoodPolicyDecision:
    parsed_task_type = parse_task_type(task_type)
    group_key = food_policy.group_for(parsed_task_type)
    resolved_group_key = group_key if group_key in model_groups else "coarse"
    group = model_groups.get(resolved_group_key, DEFAULT_MODEL_GROUPS["coarse"])
    return FoodPolicyDecision(
        task_type=parsed_task_type,
        group_key=resolved_group_key,
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
