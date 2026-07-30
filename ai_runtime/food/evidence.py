"""Derived model evidence backed by AI Runtime report observations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from ai_runtime.food.planner import ModelEvidence
from ai_runtime.models.capabilities import (
    canonical_display_name,
    known_capabilities,
)
from ai_runtime.providers.profiles import get_product
from ai_runtime.storage.provider_connections import ProviderConnectionStore
from ai_runtime.storage.report_repository import (
    ReportRepository,
    ValidationObservation,
)


class ModelEvidenceStore:
    """Compatibility facade over the report database's current projection."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self._repository: Optional[ReportRepository] = None

    @property
    def repository(self) -> ReportRepository:
        if self._repository is None:
            self._repository = ReportRepository(self.path)
        return self._repository

    def load(self) -> dict[str, ModelEvidence]:
        connections = ProviderConnectionStore().load().connections
        result: dict[str, ModelEvidence] = {}
        for observation in self.repository.current(subject_kind="model"):
            if observation.details.get("unavailable", False):
                continue
            connection_id, separator, model_id = observation.subject_id.partition("/")
            connection = connections.get(connection_id)
            if not separator or connection is None:
                continue
            model = next(
                (
                    item
                    for item in connection.models
                    if item.endpoint_model_id == model_id
                ),
                None,
            )
            if (
                model is None
                or connection.archived
                or not connection.enabled
                or model.hidden
                or model.retired
                or not model.available
            ):
                continue
            profile = get_product(connection.catalog_id)
            result[observation.subject_id] = _from_observation(
                observation,
                display_name=model.display_name,
                local=bool(profile and profile.connection_method == "local"),
                supports_tools=model.supports_tools,
                supports_vision=model.supports_vision,
                supports_reasoning=model.supports_reasoning,
            )
        return result

    def merge(self, evidence: Sequence[ModelEvidence]) -> None:
        if not evidence:
            return
        run_id = self.repository.start_run(
            scope="model_evidence",
            trigger="evidence",
        )
        for item in evidence:
            self._append(run_id, item)
        self.repository.finish_run(run_id, status="partial")

    def replace_provider(
        self,
        provider_id: str,
        evidence: Sequence[ModelEvidence],
    ) -> None:
        prefix = f"{provider_id}/"
        replacements = {item.model: item for item in evidence}
        invalid = [
            model_id for model_id in replacements if not model_id.startswith(prefix)
        ]
        if invalid:
            raise ValueError(f"Provider '{provider_id}' 证据归属不匹配: {invalid[0]}")
        current = self.load()
        run_id = self.repository.start_run(
            scope=f"provider_models:{provider_id}",
            trigger="discovery",
        )
        for model_id, item in current.items():
            if model_id.startswith(prefix) and model_id not in replacements:
                self._append(
                    run_id,
                    ModelEvidence(
                        model=item.model,
                        display_name=item.display_name,
                        capabilities=item.capabilities,
                        verified=False,
                        cost_grade=item.cost_grade,
                        latency_ms=item.latency_ms,
                        tool_test_passed=item.tool_test_passed,
                        local=item.local,
                    ),
                    unavailable=True,
                )
        for item in replacements.values():
            self._append(run_id, item)
        self.repository.finish_run(run_id, status="partial")

    def _append(
        self,
        run_id: str,
        item: ModelEvidence,
        *,
        unavailable: bool = False,
    ) -> None:
        self.repository.append_observation(
            run_id=run_id,
            subject_kind="model",
            subject_id=item.model,
            status="skipped"
            if unavailable
            else "passed"
            if item.verified
            else "failed",
            latency_ms=item.latency_ms,
            details={
                "display_name": item.display_name,
                "capabilities": sorted(item.capabilities),
                "cost_grade": item.cost_grade,
                "tool_test_passed": item.tool_test_passed,
                "local": item.local,
                "unavailable": unavailable,
            },
        )


def _from_observation(
    observation: ValidationObservation,
    *,
    display_name: str = "",
    local: bool = False,
    supports_tools: Optional[bool] = None,
    supports_vision: Optional[bool] = None,
    supports_reasoning: Optional[bool] = None,
) -> ModelEvidence:
    details = observation.details
    raw_capabilities = details.get("capabilities", ())
    capabilities = (
        frozenset(str(item) for item in raw_capabilities)
        if isinstance(raw_capabilities, (list, tuple, set))
        else frozenset()
    )
    display_name = display_name or str(details.get("display_name", ""))
    capabilities = capabilities | known_capabilities(
        observation.subject_id,
        display_name,
    )
    if supports_tools:
        capabilities = capabilities | {"tools"}
    if supports_vision:
        capabilities = capabilities | {"vision"}
    if supports_reasoning:
        capabilities = capabilities | {"reasoning"}
    return ModelEvidence(
        model=observation.subject_id,
        display_name=canonical_display_name(
            observation.subject_id,
            display_name,
        ),
        capabilities=capabilities,
        verified=observation.status == "passed",
        cost_grade=_int_value(details, "cost_grade", 2),
        latency_ms=observation.latency_ms,
        tool_test_passed=bool(details.get("tool_test_passed", False)),
        local=local or bool(details.get("local", False)),
        observed_at=observation.observed_at,
    )


def _int_value(data: Mapping[str, Any], key: str, default: int) -> int:
    value = data.get(key)
    return int(value) if isinstance(value, int) else default
