"""Deterministic food generation from fresh, validated model evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from ai_runtime.food.models import FoodPackage, ModelAssignment

EVIDENCE_MAX_AGE = timedelta(hours=24)


@dataclass(frozen=True)
class ModelEvidence:
    model: str
    capabilities: frozenset[str]
    verified: bool
    display_name: str = ""
    cost_grade: int = 2
    latency_ms: Optional[float] = None
    tool_test_passed: bool = False
    local: bool = False
    observed_at: str = ""

    def is_fresh(self, now: Optional[datetime] = None) -> bool:
        if not self.verified or not self.observed_at:
            return False
        try:
            observed = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        current = now or datetime.now(timezone.utc)
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        return current - observed <= EVIDENCE_MAX_AGE


@dataclass(frozen=True)
class FoodChange:
    role: str
    old_model: Optional[str]
    new_model: Optional[str]


@dataclass(frozen=True)
class FoodUpdateProposal:
    package: FoodPackage
    changes: tuple[FoodChange, ...]
    warnings: tuple[str, ...] = ()

    @property
    def has_changes(self) -> bool:
        return any(item.old_model != item.new_model for item in self.changes)


class FoodPlanner:
    """Select only models already proven usable in the requested scope."""

    def __init__(self, advisor: object | None = None) -> None:
        self.advisor = advisor

    def propose_package(
        self,
        package: FoodPackage,
        evidence: Sequence[ModelEvidence],
        *,
        connection_ids: Sequence[str] = (),
        local_first: bool = False,
        allow_remote: bool = True,
    ) -> FoodUpdateProposal:
        scope = set(connection_ids)
        eligible = [
            item
            for item in evidence
            if item.is_fresh()
            and (not scope or item.model.split("/", 1)[0] in scope)
            and (allow_remote or item.local)
        ]
        eligible.sort(
            key=lambda item: (
                0 if local_first and item.local else 1,
                item.cost_grade,
                item.latency_ms if item.latency_ms is not None else float("inf"),
                item.model,
            )
        )
        warnings: list[str] = []
        primary = _choose(eligible, "text")
        reasoning = _choose(eligible, "reasoning")
        vision = _choose(eligible, "vision")
        tool = _choose(eligible, "tools", require_tool_test=True)
        fallback = tuple(
            ModelAssignment(item.model)
            for item in eligible
            if primary is not None and item.model != primary.model
        )[:2]
        if primary is None:
            warnings.append("没有符合范围且最近验证通过的主模型")
        if local_first and allow_remote and primary and not _is_local(primary, eligible):
            warnings.append("没有可用本地模型，候选保底粮依赖网络")
        proposed = replace(
            package,
            primary=primary,
            reasoning=reasoning,
            vision=vision,
            tool=tool,
            fallback=fallback,
            enabled=primary is not None,
        )
        changes = tuple(
            FoodChange(role, old, new)
            for role, old, new in (
                ("primary", _model(package.primary), _model(proposed.primary)),
                ("reasoning", _model(package.reasoning), _model(proposed.reasoning)),
                ("vision", _model(package.vision), _model(proposed.vision)),
                ("tool", _model(package.tool), _model(proposed.tool)),
                (
                    "fallback",
                    ",".join(item.model for item in package.fallback) or None,
                    ",".join(item.model for item in proposed.fallback) or None,
                ),
            )
        )
        return FoodUpdateProposal(proposed, changes, tuple(warnings))


def _choose(
    evidence: Sequence[ModelEvidence],
    capability: str,
    *,
    require_tool_test: bool = False,
) -> Optional[ModelAssignment]:
    for item in evidence:
        capabilities = item.capabilities or frozenset({"text"})
        if capability not in capabilities:
            continue
        if require_tool_test and not item.tool_test_passed:
            continue
        return ModelAssignment(item.model)
    return None


def _model(value: Optional[ModelAssignment]) -> Optional[str]:
    return value.model if value else None


def _is_local(
    assignment: ModelAssignment,
    evidence: Sequence[ModelEvidence],
) -> bool:
    return any(item.model == assignment.model and item.local for item in evidence)
