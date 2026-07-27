"""Runtime overview report and Provider × Model matrix."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.planner import ModelEvidence
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore
from ai_runtime.models.capabilities import (
    canonical_display_name,
    known_capabilities,
)
from ai_runtime.models.catalog import BUILTIN_MODEL_CATALOG
from ai_runtime.providers.profiles import BUILTIN_PROFILES
from ai_runtime.storage.data_home import get_validation_dir
from ai_runtime.validation.models import CheckResult, CheckStatus, ValidationSuite
from ai_runtime.validation.providers import (
    ProviderValidationRunner,
    discover_provider_models,
)


def configured_provider_ids(config: LLMRuntimeConfig) -> list[str]:
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


class RuntimeOverviewStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or get_validation_dir()
        self.current_path = self.directory / "runtime-overview-current.json"

    def load_current(self) -> dict[str, Any] | None:
        return self._read(self.current_path)

    def save(self, report: Mapping[str, Any]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        history_path = self.directory / f"runtime-overview-{stamp}.json"
        payload = json.dumps(dict(report), ensure_ascii=False, indent=2)
        self._atomic_write(history_path, payload)
        self._atomic_write(self.current_path, payload)
        return history_path

    def history(self) -> list[Path]:
        if not self.directory.exists():
            return []
        return sorted(
            (
                path
                for path in self.directory.glob("runtime-overview-*.json")
                if path.name != self.current_path.name
            ),
            reverse=True,
        )

    def load_path(self, path: Path) -> dict[str, Any] | None:
        return self._read(path)

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _atomic_write(path: Path, payload: str) -> None:
        temp_path = path.with_name(f".{path.name}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(path)


class RuntimeOverviewGenerator:
    def __init__(
        self,
        config: LLMRuntimeConfig,
        *,
        evidence_store: ModelEvidenceStore | None = None,
        food_store: FoodCatalogStore | None = None,
    ) -> None:
        self.config = config
        self.evidence_store = evidence_store or ModelEvidenceStore()
        self.food_store = food_store or FoodCatalogStore()

    def snapshot(self) -> dict[str, Any]:
        return build_overview(
            self.config,
            list(self.evidence_store.load().values()),
            self.food_store.load(),
        )

    def regenerate(self) -> dict[str, Any]:
        evidence_before = self.evidence_store.load()
        provider_evidence: dict[str, list[ModelEvidence]] = {}
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
                    current_evidence: list[ModelEvidence] = []
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
                            ModelEvidence(
                                model=model_id,
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
            self.evidence_store.replace_provider(provider_id, evidence)
        report = build_overview(
            self.config,
            list(self.evidence_store.load().values()),
            self.food_store.load(),
            provider_health=provider_health,
        )
        report["suites"] = [suite.to_dict() for suite in suites]
        return report


def build_overview(
    config: LLMRuntimeConfig,
    evidence: Sequence[ModelEvidence],
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
            "model": recipe.primary.model,
            "status": recipe.validation_status.value,
        }
        for key, recipe in catalog.recipes.items()
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
        "food_generation_sources": list(catalog.generation_sources),
        "food_generation_note": catalog.generation_note,
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
        lines = ["Model                              Available Endpoints   Fastest Latency"]
        lines.append("─" * min(width, 60))
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
            lines.append(
                f"{name:<32}{len(verified):>2}/{len(endpoints):<7}{fastest:>8}"
            )
        return lines

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
            endpoints = {
                str(item.get("provider", "")): item
                for item in row.get("endpoints", ())
                if isinstance(item, Mapping)
            }
            cells = []
            for provider in page:
                endpoint = endpoints.get(provider)
                if endpoint is None:
                    cell = "—"
                elif endpoint.get("verified"):
                    latency = endpoint.get("latency_ms")
                    cell = f"✓ {float(latency):.0f}ms" if latency is not None else "✓"
                else:
                    latency = endpoint.get("latency_ms")
                    cell = f"✗ {float(latency):.0f}ms" if latency is not None else "✗"
                cells.append(f"{cell:<{provider_width}}")
            lines.append(
                f"{str(row.get('model', ''))[: model_width - 1]:<{model_width}}"
                + "".join(cells)
            )
        if start + providers_per_page < len(providers):
            lines.append("")
    return lines


def _group_models(
    evidence: Sequence[ModelEvidence], provider_ids: Sequence[str]
) -> list[dict[str, Any]]:
    allowed = set(provider_ids)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        provider, model_name = (
            item.model.split("/", 1) if "/" in item.model else ("ollama", item.model)
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
