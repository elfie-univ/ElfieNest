"""严格的模型引用：粮食只能指向一个明确连接实例的一个模型。"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PROVIDER_ID = re.compile(r"^[a-z][a-z0-9_-]*$")


class ModelReferenceError(ValueError):
    """Model references must never imply a provider through a fallback."""


@dataclass(frozen=True)
class ModelReference:
    connection_id: str
    model_id: str

    @property
    def provider_id(self) -> str:
        """Compatibility alias while Runtime call sites migrate terminology."""
        return self.connection_id


def parse_model_reference(value: str) -> ModelReference:
    """Parse exactly ``connection_id/model_id`` without guessing a connection."""
    if not isinstance(value, str) or "/" not in value:
        raise ModelReferenceError("模型必须使用 connection_id/model_id")
    connection_id, model_id = value.split("/", 1)
    if (
        not _PROVIDER_ID.fullmatch(connection_id)
        or not model_id
        or model_id.strip() != model_id
    ):
        raise ModelReferenceError("模型必须使用 connection_id/model_id")
    return ModelReference(connection_id=connection_id, model_id=model_id)
