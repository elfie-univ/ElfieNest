from dataclasses import dataclass
from typing import Any, Mapping


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


def load_model_groups(runtime_policy: Mapping[str, Any] | None = None) -> dict[str, ModelGroup]:
    groups = dict(DEFAULT_MODEL_GROUPS)
    if runtime_policy is None:
        return groups

    raw_groups = runtime_policy.get("model_groups", {})
    if not isinstance(raw_groups, Mapping):
        return groups

    for group_key, raw_group in raw_groups.items():
        if not isinstance(group_key, str) or not isinstance(raw_group, Mapping):
            continue

        raw_model_keys = raw_group.get("model_keys", ())
        if not isinstance(raw_model_keys, list | tuple):
            continue

        model_keys = tuple(
            model_key for model_key in raw_model_keys if isinstance(model_key, str)
        )
        if not model_keys:
            continue

        display_name = raw_group.get("display_name", group_key)
        groups[group_key] = ModelGroup(
            key=group_key,
            display_name=display_name if isinstance(display_name, str) else group_key,
            model_keys=model_keys,
        )

    return groups


def model_groups_to_payload(groups: Mapping[str, ModelGroup]) -> dict[str, dict[str, Any]]:
    return {
        group_key: {
            "display_name": group.display_name,
            "model_keys": list(group.model_keys),
        }
        for group_key, group in groups.items()
    }
