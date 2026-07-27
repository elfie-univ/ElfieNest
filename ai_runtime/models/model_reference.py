"""严格的模型引用：粮食只能指向一个明确 Provider 的一个模型。"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PROVIDER_ID = re.compile(r"^[a-z][a-z0-9_-]*$")


class ModelReferenceError(ValueError):
    """Model references must never imply a provider through a fallback."""


@dataclass(frozen=True)
class ModelReference:
    provider_id: str
    model_id: str


def parse_model_reference(value: str) -> ModelReference:
    """Parse exactly ``provider_id/model_id`` without guessing an Ollama provider."""
    if not isinstance(value, str) or value.count("/") != 1:
        raise ModelReferenceError("模型必须使用 provider_id/model_id")
    provider_id, model_id = value.split("/", 1)
    if (
        not _PROVIDER_ID.fullmatch(provider_id)
        or not model_id
        or model_id.strip() != model_id
    ):
        raise ModelReferenceError("模型必须使用 provider_id/model_id")
    return ModelReference(provider_id=provider_id, model_id=model_id)
