"""Model-execution overview report and Provider × Model matrix."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.features.configuration.food import StoredModelEvidence, project_food_health
from elfie.brain.reasoning.food_port import FoodCatalog, FoodPort
from infrastructure.models.capabilities import (
    canonical_display_name,
    known_capabilities,
)
from infrastructure.models.catalog import BUILTIN_MODEL_CATALOG
from infrastructure.models.food_technology import stored_food_package
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.providers.profiles import BUILTIN_PROFILES
from infrastructure.models.storage_ports import ModelEvidencePort
from infrastructure.models.validation.provider_validation import (
    ProviderValidationRunner,
    discover_provider_models,
)
from infrastructure.models.validation.validation_models import (
    CheckResult,
    CheckStatus,
    ValidationSuite,
)


def configured_provider_ids(config: ModelExecutionConfig) -> list[str]:
    """只返回真正能参与验证的 Provider，不把默认占位配置算进去。"""
    configured: list[str] = []
    for provider_id, provider in config.providers.items():
        api_base = str(provider.get("api_base", "")).strip()
        auth_type = str(provider.get("auth_type", "bearer"))
        if provider_id == "ollama":
            if api_base:
                configured.append(provider_id)
            continue
        if provider.get("api_key"):
            configured.append(provider_id)
            continue
        if provider_id not in BUILTIN_PROFILES and auth_type == "none" and api_base:
            configured.append(provider_id)
    return configured


class ModelExecutionOverviewGenerator:
    def __init__(
        self,
        config: ModelExecutionConfig,
        *,
        evidence: ModelEvidencePort,
        food_store: FoodPort | None = None,
    ) -> None:
        self.config = config
        self.evidence = evidence
        self.food_store = food_store

    def _load_food_catalog(self) -> FoodCatalog:
        if self.food_store is None:
            raise RuntimeError("模型执行概览未注入粮食数据库仓储")
        return self.food_store.load()

    def snapshot(self) -> dict[str, Any]:
        return build_overview(
            self.config,
            list(self.evidence.list_model_evidence()),
            self._load_food_catalog(),
        )

    def regenerate(self) -> dict[str, Any]:
        evidence_before = {
            item.reference: item for item in self.evidence.list_model_evidence()
        }
        provider_evidence: dict[str, list[StoredModelEvidence]] = {}
        suites: list[ValidationSuite] = []
        provider_health: dict[str, str] = {}

        for provider_id in configured_provider_ids(self.config):
            runner = ProviderValidationRunner(self.config)
            health = runner.verify_provider(provider_id)
            provider_health[provider_id] = health.status.value
            results: list[CheckResult] = [health]
            if health.status is CheckStatus.PASSED:
                try:
                    models = discover_provider_models(provider_id, self.config)
                except Exception as exc:
                    results.append(
                        CheckResult(
                            check_id=f"provider.{provider_id}.discover_models",
                            status=CheckStatus.FAILED,
                            message=str(exc),
                            provider=provider_id,
                        )
                    )
                else:
                    model_by_id = {model.name: model for model in models}
                    if models:
                        model_suite = runner.verify_models(
                            provider_id, [model.name for model in models]
                        )
                        results.extend(model_suite.results)
                    else:
                        results.append(
                            CheckResult(
                                check_id=f"provider.{provider_id}.discover_models",
                                status=CheckStatus.WARNING,
                                message="Provider 当前未返回任何模型",
                                provider=provider_id,
                            )
                        )
                    current_evidence: list[StoredModelEvidence] = []
                    for result in results[1:]:
                        if not result.model:
                            continue
                        model_id = f"{provider_id}/{result.model}"
                        previous = evidence_before.get(model_id)
                        catalog_entry = BUILTIN_MODEL_CATALOG.get(model_id)
                        discovered_name = (
                            model_by_id[result.model].display_name
                            if result.model in model_by_id
                            else previous.display_name
                            if previous
                            else result.model
                        )
                        known = known_capabilities(result.model, discovered_name)
                        current_evidence.append(
                            StoredModelEvidence(
                                reference=model_id,
                                display_name=canonical_display_name(
                                    result.model, discovered_name
                                ),
                                capabilities=frozenset(
                                    catalog_entry.capabilities
                                    if catalog_entry
                                    else known
                                    if known
                                    else previous.capabilities
                                    if previous
                                    else ("text",)
                                ),
                                verified=result.status is CheckStatus.PASSED,
                                cost_grade=(
                                    catalog_entry.cost_tier
                                    if catalog_entry
                                    else previous.cost_grade
                                    if previous
                                    else 2
                                ),
                                latency_ms=result.duration_ms,
                                tool_test_passed=(
                                    previous.tool_test_passed if previous else False
                                ),
                                local=provider_id == "ollama",
                            )
                        )
                    provider_evidence[provider_id] = current_evidence
            suites.append(ValidationSuite(f"provider:{provider_id}", tuple(results)))

        for provider_id, evidence in provider_evidence.items():
            self.evidence.record_model_evidence(
                evidence,
                scope=f"overview:{provider_id}",
                trigger="overview",
            )
        report = build_overview(
            self.config,
            list(self.evidence.list_model_evidence()),
            self._load_food_catalog(),
            provider_health=provider_health,
        )
        report["suites"] = [suite.to_dict() for suite in suites]
        return report


def build_overview(
    config: ModelExecutionConfig,
    evidence: Sequence[StoredModelEvidence],
    catalog: FoodCatalog,
    *,
    provider_health: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    provider_ids = configured_provider_ids(config)
    health = dict(provider_health or {})
    providers = [
        {
            "id": provider_id,
            "api_base": str(config.providers.get(provider_id, {}).get("api_base", "")),
            "status": health.get(provider_id, "unknown"),
        }
        for provider_id in provider_ids
    ]
    model_rows = _group_models(evidence, provider_ids)
    foods = [
        {
            "key": key,
            "model": package.primary.model if package.primary else "",
            "status": project_food_health(
                stored_food_package(package),
                {item.reference: item for item in evidence},
            ).status,
        }
        for key, package in catalog.packages.items()
    ]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "configured_providers": len(provider_ids),
            "reachable_providers": sum(
                1 for item in providers if item["status"] == CheckStatus.PASSED.value
            ),
            "model_endpoints": sum(len(row["endpoints"]) for row in model_rows),
            "verified_model_endpoints": sum(
                1
                for row in model_rows
                for endpoint in row["endpoints"]
                if endpoint["verified"]
            ),
            "agent_verified_models": sum(item.tool_test_passed for item in evidence),
            "available_foods": sum(
                1 for item in foods if item["model"] and item["status"] != "failed"
            ),
            "total_foods": len(foods),
        },
        "providers": providers,
        "models": model_rows,
        "foods": foods,
    }


def render_provider_model_matrix(report: Mapping[str, Any], *, width: int) -> list[str]:
    providers = [
        str(item.get("id", ""))
        for item in report.get("providers", ())
        if isinstance(item, Mapping)
    ]
    models = [item for item in report.get("models", ()) if isinstance(item, Mapping)]
    if not providers:
        return ["尚无已配置 Provider。"]
    if not models:
        return ["尚无模型验证证据。"]
    if width < 96:
        compact_lines = [
            "Model                              Available Endpoints   Fastest Latency"
        ]
        compact_lines.append("─" * min(width, 60))
        for row in models:
            endpoints = [
                endpoint
                for endpoint in row.get("endpoints", ())
                if isinstance(endpoint, Mapping)
            ]
            verified = [item for item in endpoints if item.get("verified")]
            latencies = [
                float(item["latency_ms"])
                for item in verified
                if isinstance(item.get("latency_ms"), (int, float))
            ]
            fastest = f"{min(latencies):.0f}ms" if latencies else "—"
            name = str(row.get("model", ""))[:30]
            compact_lines.append(
                f"{name:<32}{len(verified):>2}/{len(endpoints):<7}{fastest:>8}"
            )
        return compact_lines

    model_width = 30
    provider_width = 16
    providers_per_page = max(1, (width - model_width) // provider_width)
    lines: list[str] = []
    for start in range(0, len(providers), providers_per_page):
        page = providers[start : start + providers_per_page]
        if len(providers) > providers_per_page:
            lines.append(f"Provider {start + 1}-{start + len(page)} / {len(providers)}")
        lines.append(
            f"{'模型':<{model_width}}"
            + "".join(
                f"{provider[: provider_width - 1]:<{provider_width}}"
                for provider in page
            )
        )
        lines.append("─" * min(width, model_width + provider_width * len(page)))
        for row in models:
            endpoint_by_provider = {
                str(item.get("provider", "")): item
                for item in row.get("endpoints", ())
                if isinstance(item, Mapping)
            }
            cells: list[str] = []
            for provider in page:
                endpoint = endpoint_by_provider.get(provider)
                if endpoint is None:
                    cell = "—"
                elif endpoint.get("verified"):
                    latency = endpoint.get("latency_ms")
                    cell = f"✅ {float(latency):.0f}ms" if latency is not None else "✅"
                else:
                    latency = endpoint.get("latency_ms")
                    cell = f"❌ {float(latency):.0f}ms" if latency is not None else "❌"
                cells.append(f"{cell:<{provider_width}}")
            lines.append(
                f"{str(row.get('model', ''))[: model_width - 1]:<{model_width}}"
                + "".join(cells)
            )
        if start + providers_per_page < len(providers):
            lines.append("")
    return lines


def _group_models(
    evidence: Sequence[StoredModelEvidence], provider_ids: Sequence[str]
) -> list[dict[str, Any]]:
    allowed = set(provider_ids)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        provider, model_name = (
            item.reference.split("/", 1)
            if "/" in item.reference
            else ("ollama", item.reference)
        )
        if provider not in allowed:
            continue
        display_name = item.display_name or model_name
        grouped.setdefault(display_name, []).append(
            {
                "provider": provider,
                "provider_model": model_name,
                "display_name": display_name,
                "verified": item.verified,
                "latency_ms": item.latency_ms,
                "tool_test_passed": item.tool_test_passed,
                "capabilities": sorted(item.capabilities),
            }
        )
    return [
        {
            "model": display_name,
            "endpoints": sorted(endpoints, key=lambda x: x["provider"]),
        }
        for display_name, endpoints in sorted(grouped.items())
    ]
