"""Provider 不支持模型枚举时的手工模型与已知端点建议。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ai_runtime.models.capabilities import canonical_display_name

_PLACEHOLDER_MODELS = {"custom-model"}


@dataclass(frozen=True)
class ProviderModelSpec:
    model_id: str
    display_name: str


def configured_model_specs(provider: Mapping[str, Any]) -> list[ProviderModelSpec]:
    """返回手工模型目录，并兼容旧版字符串列表。"""
    specs: list[ProviderModelSpec] = []
    raw_models = provider.get("models", ())
    if isinstance(raw_models, str):
        specs.extend(_spec(item) for item in _split_models(raw_models))
    elif isinstance(raw_models, (list, tuple, set)):
        for item in raw_models:
            if isinstance(item, Mapping):
                model_id = str(item.get("id") or item.get("model_id") or "").strip()
                display_name = str(item.get("display_name") or model_id).strip()
                if model_id:
                    specs.append(
                        ProviderModelSpec(
                            model_id,
                            canonical_display_name(model_id, display_name),
                        )
                    )
            else:
                specs.append(_spec(str(item).strip()))

    test_model = str(provider.get("test_model", "")).strip()
    if test_model and test_model not in _PLACEHOLDER_MODELS:
        specs.append(_spec(test_model))

    unique = _unique_specs(
        item for item in specs if item.model_id not in _PLACEHOLDER_MODELS
    )
    if unique:
        return unique
    return [
        ProviderModelSpec(model_id, model_id)
        for model_id in suggested_model_names(str(provider.get("api_base", "")))
    ]


def configured_model_names(provider: Mapping[str, Any]) -> list[str]:
    """返回 Provider 手工配置的模型；未配置时使用已知端点建议。"""
    return [item.model_id for item in configured_model_specs(provider)]


def suggested_model_names(api_base: str) -> list[str]:
    """仅对官方明确规定固定调用 ID 的已知端点给出建议。"""
    normalized = api_base.lower().rstrip("/")
    if "maas-coding-api.cn-huabei-1.xf-yun.com" in normalized:
        return ["astron-code-latest"]
    return []


def parse_model_input(value: str) -> list[str]:
    """把终端中的逗号分隔模型 ID 转换为去重列表。"""
    return _unique(_split_models(value))


def _split_models(value: str) -> list[str]:
    return [item.strip() for item in value.replace("，", ",").split(",")]


def _unique(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _spec(model_id: str) -> ProviderModelSpec:
    return ProviderModelSpec(model_id, model_id)


def _unique_specs(values) -> list[ProviderModelSpec]:
    unique: dict[str, ProviderModelSpec] = {}
    for item in values:
        if item.model_id:
            # 新版 models 目录在前，旧 test_model 只用于补缺，
            # 不得覆盖用户编辑的显示名称。
            unique.setdefault(item.model_id, item)
    return list(unique.values())
