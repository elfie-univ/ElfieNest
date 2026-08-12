"""Pure Food generation and health rules owned by the Food feature."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Sequence

from .port_models import (
    StoredFoodChange,
    StoredFoodHealth,
    StoredFoodPackage,
    StoredFoodProposal,
    StoredModelEvidence,
)

EVIDENCE_MAX_AGE = timedelta(hours=24)


def is_model_evidence_fresh(
    evidence: StoredModelEvidence,
    now: datetime | None = None,
) -> bool:
    """Return whether validation evidence is verified and at most 24 hours old."""
    if not evidence.verified or not evidence.observed_at:
        return False
    try:
        observed = datetime.fromisoformat(evidence.observed_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    current = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return current - observed <= EVIDENCE_MAX_AGE


class FoodPlanner:
    """Choose only models already proven usable in the requested scope."""

    def propose_package(
        self,
        package: StoredFoodPackage,
        evidence: Sequence[StoredModelEvidence],
        *,
        connection_ids: Sequence[str] = (),
        local_first: bool = False,
        allow_remote: bool = True,
    ) -> StoredFoodProposal:
        scope = set(connection_ids)
        eligible = [
            item
            for item in evidence
            if is_model_evidence_fresh(item)
            and (not scope or item.reference.split("/", 1)[0] in scope)
            and (allow_remote or item.local)
        ]
        eligible.sort(
            key=lambda item: (
                0 if local_first and item.local else 1,
                item.cost_grade,
                item.latency_ms if item.latency_ms is not None else float("inf"),
                item.reference,
            )
        )
        warnings: list[str] = []
        primary = _choose(eligible, "text")
        reasoning = _choose(eligible, "reasoning")
        vision = _choose(eligible, "vision")
        tool = _choose(eligible, "tools", require_tool_test=True)
        fallback = next(
            (
                item.reference
                for item in eligible
                if primary is not None and item.reference != primary
            ),
            None,
        )
        if primary is None:
            warnings.append("没有符合范围且最近验证通过的主模型")
        if (
            local_first
            and allow_remote
            and primary
            and not _is_local(primary, eligible)
        ):
            warnings.append("没有可用本地模型，候选保底粮依赖网络")
        proposed = replace(
            package,
            primary_model=primary,
            reasoning_model=reasoning,
            vision_model=vision,
            tool_model=tool,
            fallback_model=fallback,
            enabled=primary is not None,
        )
        changes = tuple(
            StoredFoodChange(role, old, new)
            for role, old, new in (
                ("primary", package.primary_model, proposed.primary_model),
                ("reasoning", package.reasoning_model, proposed.reasoning_model),
                ("vision", package.vision_model, proposed.vision_model),
                ("tool", package.tool_model, proposed.tool_model),
                ("fallback", package.fallback_model, proposed.fallback_model),
            )
        )
        return StoredFoodProposal(proposed, changes, tuple(warnings))


def project_food_health(
    package: StoredFoodPackage,
    evidence: dict[str, StoredModelEvidence],
) -> StoredFoodHealth:
    """Project Food health without mutating persistent facts."""
    if package.archived:
        return StoredFoodHealth("archived", _locality(package, evidence), None)
    if not package.enabled:
        return StoredFoodHealth("disabled", _locality(package, evidence), None)
    if package.primary_model is None:
        return StoredFoodHealth("unconfigured", _locality(package, evidence), None)
    referenced = [evidence.get(item) for item in package.model_references]
    primary = evidence.get(package.primary_model)
    latest = max(
        (item.observed_at for item in referenced if item and item.observed_at),
        default=None,
    )
    if primary is None or not is_model_evidence_fresh(primary):
        fallback_evidence = (
            evidence.get(package.fallback_model)
            if package.fallback_model is not None
            else None
        )
        fallback_works = fallback_evidence is not None and is_model_evidence_fresh(
            fallback_evidence
        )
        return StoredFoodHealth(
            "degraded" if fallback_works else "unavailable",
            _locality(package, evidence),
            latest,
        )
    optional_failed = any(
        item is None or not is_model_evidence_fresh(item) for item in referenced[1:]
    )
    return StoredFoodHealth(
        "degraded" if optional_failed else "healthy",
        _locality(package, evidence),
        latest,
    )


def _choose(
    evidence: Sequence[StoredModelEvidence],
    capability: str,
    *,
    require_tool_test: bool = False,
) -> str | None:
    for item in evidence:
        capabilities = item.capabilities or frozenset({"text"})
        if capability not in capabilities:
            continue
        if require_tool_test and not item.tool_test_passed:
            continue
        return item.reference
    return None


def _is_local(reference: str, evidence: Sequence[StoredModelEvidence]) -> bool:
    return any(item.reference == reference and item.local for item in evidence)


def _locality(
    package: StoredFoodPackage,
    evidence: dict[str, StoredModelEvidence],
) -> str:
    values = {
        item.local
        for reference in package.model_references
        if (item := evidence.get(reference)) is not None
    }
    if not values:
        return "unknown"
    if values == {True}:
        return "local"
    if values == {False}:
        return "remote"
    return "mixed"


__all__ = (
    "EVIDENCE_MAX_AGE",
    "FoodPlanner",
    "is_model_evidence_fresh",
    "project_food_health",
)
