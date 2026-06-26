from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ModelGroup:
    key: str
    display_name: str
    model_keys: tuple[str, ...]


DEFAULT_MODEL_GROUPS: Mapping[str, ModelGroup] = {
    "coarse": ModelGroup(
        key="coarse",
        display_name="粗粮",
        model_keys=("local_fast",),
    ),
    "standard": ModelGroup(
        key="standard",
        display_name="标准粮",
        model_keys=("remote_cheap", "local_fast"),
    ),
    "premium": ModelGroup(
        key="premium",
        display_name="精粮",
        model_keys=("remote_deep", "local_fast"),
    ),
    "vision": ModelGroup(
        key="vision",
        display_name="视觉粮",
        model_keys=("remote_multimodal", "local_vision", "local_fast"),
    ),
    "code": ModelGroup(
        key="code",
        display_name="代码粮",
        model_keys=("remote_deep", "local_fast"),
    ),
    "organize": ModelGroup(
        key="organize",
        display_name="整理粮",
        model_keys=("remote_cheap", "local_fast"),
    ),
}


def resolve_model_key(group: ModelGroup, available_model_keys: set[str]) -> str:
    for model_key in group.model_keys:
        if model_key in available_model_keys:
            return model_key
    return "local_fast"
