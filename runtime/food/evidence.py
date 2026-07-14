"""粮食规划使用的模型证据存储。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.food.planner import ModelEvidence
from runtime.models.capabilities import (
    canonical_display_name,
    known_capabilities,
)
from runtime.storage.config_store import read_yaml_mapping, write_yaml_mapping
from runtime.storage.data_home import get_model_evidence_path


class ModelEvidenceStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_model_evidence_path()

    def load(self) -> dict[str, ModelEvidence]:
        payload = read_yaml_mapping(self.path)
        raw_models = payload.get("models", {})
        if not isinstance(raw_models, Mapping):
            return {}
        return {
            str(model_id): _from_dict(str(model_id), data)
            for model_id, data in raw_models.items()
            if isinstance(data, Mapping)
        }

    def merge(self, evidence: Sequence[ModelEvidence]) -> None:
        models = self.load()
        models.update({item.model: item for item in evidence})
        self._save(models)

    def replace_provider(
        self,
        provider_id: str,
        evidence: Sequence[ModelEvidence],
    ) -> None:
        """以 Provider 当前完整模型列表替换旧证据。

        只应在 Provider 模型发现成功后调用；这样能清理已删除模型，
        同时不会因临时断网而误删历史证据。
        """
        prefix = f"{provider_id}/"
        replacements = {item.model: item for item in evidence}
        invalid = [model_id for model_id in replacements if not model_id.startswith(prefix)]
        if invalid:
            raise ValueError(f"Provider '{provider_id}' 证据归属不匹配: {invalid[0]}")
        models = {
            model_id: item
            for model_id, item in self.load().items()
            if not model_id.startswith(prefix)
        }
        models.update(replacements)
        self._save(models)

    def _save(self, models: Mapping[str, ModelEvidence]) -> None:
        write_yaml_mapping(
            self.path,
            {"models": {model_id: _to_dict(item) for model_id, item in models.items()}},
        )


def _to_dict(item: ModelEvidence) -> dict[str, Any]:
    return {
        "display_name": item.display_name,
        "capabilities": sorted(item.capabilities),
        "verified": item.verified,
        "cost_grade": item.cost_grade,
        "latency_ms": item.latency_ms,
        "tool_test_passed": item.tool_test_passed,
        "local": item.local,
    }


def _from_dict(model_id: str, data: Mapping[str, Any]) -> ModelEvidence:
    raw_capabilities = data.get("capabilities", ())
    capabilities = (
        frozenset(str(item) for item in raw_capabilities)
        if isinstance(raw_capabilities, (list, tuple, set))
        else frozenset()
    )
    display_name = str(data.get("display_name", ""))
    capabilities = capabilities | known_capabilities(model_id, display_name)
    return ModelEvidence(
        model=model_id,
        display_name=canonical_display_name(model_id, display_name),
        capabilities=capabilities,
        verified=bool(data.get("verified", False)),
        cost_grade=int(data.get("cost_grade", 2)),
        latency_ms=(
            float(data["latency_ms"])
            if isinstance(data.get("latency_ms"), (int, float))
            else None
        ),
        tool_test_passed=bool(data.get("tool_test_passed", False)),
        local=bool(data.get("local", False)),
    )
