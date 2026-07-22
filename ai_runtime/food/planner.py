"""根据真实模型证据生成固定粮食的候选配方。

规划器允许接入大模型顾问，但顾问只能从已验证候选中推荐模型；最终选择、
能力校验、人工锁定字段和落盘始终由确定性代码控制。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from ai_runtime.food.models import (
    FIXED_FOOD_KINDS,
    ExecutionProfile,
    FoodRecipe,
    FoodValidationStatus,
    ReasoningProfile,
)
from ai_runtime.food.store import FoodCatalog, fingerprint_source


@dataclass(frozen=True)
class ModelEvidence:
    model: str
    capabilities: frozenset[str]
    verified: bool
    display_name: str = ""
    cost_grade: int = 2
    latency_ms: float | None = None
    tool_test_passed: bool = False
    local: bool = False

    def to_fingerprint_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "display_name": self.display_name,
            "capabilities": sorted(self.capabilities),
            "verified": self.verified,
            "cost_grade": self.cost_grade,
            "latency_ms": self.latency_ms,
            "tool_test_passed": self.tool_test_passed,
            "local": self.local,
        }


class FoodPlanningAdvisor(Protocol):
    """可由已验证大模型实现的脱敏规划顾问。"""

    def recommend(
        self,
        food_keys: Sequence[str],
        evidence: Sequence[ModelEvidence],
    ) -> Mapping[str, str]: ...


@dataclass(frozen=True)
class FoodChange:
    food_key: str
    change_type: str
    old_model: str | None
    new_model: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class FoodUpdateProposal:
    catalog: FoodCatalog
    changes: tuple[FoodChange, ...]
    warnings: tuple[str, ...] = ()
    generation_sources: tuple[str, ...] = ("rules",)
    advisor_error: str | None = None

    @property
    def has_changes(self) -> bool:
        return any(change.change_type != "unchanged" for change in self.changes)


class FoodPlanner:
    def __init__(self, advisor: FoodPlanningAdvisor | None = None) -> None:
        self.advisor = advisor
        self._advisor_status = "not_configured"
        self._advisor_error: str | None = None

    def propose(
        self,
        evidence: Sequence[ModelEvidence],
        current: FoodCatalog | None = None,
    ) -> FoodUpdateProposal:
        verified = tuple(item for item in evidence if item.verified)
        self._advisor_status = "not_configured"
        self._advisor_error = None
        recommendations = self._advisor_recommendations(verified)
        current_catalog = current or FoodCatalog()
        recipes: dict[str, FoodRecipe] = {}
        changes: list[FoodChange] = []
        proposal_warnings: list[str] = []

        for food_key, kind in FIXED_FOOD_KINDS.items():
            existing = current_catalog.recipes.get(food_key)
            selected = self._select_model(food_key, verified, recommendations)
            warnings: list[str] = []

            if existing and existing.source == "manual":
                recipe = existing
                warnings.append("该粮食为人工管理，自动更新未覆盖")
            elif existing and "primary.model" in existing.locked_fields:
                recipe = self._build_recipe(food_key, verified, selected, existing)
                recipe = FoodRecipe(
                    **{
                        **recipe.__dict__,
                        "primary": existing.primary,
                        "locked_fields": existing.locked_fields,
                    }
                )
                warnings.append("主模型已人工锁定，自动更新保留原值")
            else:
                recipe = self._build_recipe(food_key, verified, selected, existing)

            validation_warnings = validate_food_recipe(recipe, verified)
            if validation_warnings:
                warnings.extend(validation_warnings)
                recipe = FoodRecipe(
                    **{
                        **recipe.__dict__,
                        "validation_status": FoodValidationStatus.FAILED,
                    }
                )
            elif recipe.validation_status is FoodValidationStatus.UNVERIFIED:
                recipe = FoodRecipe(
                    **{
                        **recipe.__dict__,
                        "validation_status": FoodValidationStatus.PASSED,
                    }
                )
            recipes[food_key] = recipe
            old_model = existing.primary.model if existing else None
            new_model = recipe.primary.model or None
            change_type = (
                "added"
                if existing is None
                else "unchanged"
                if old_model == new_model and existing.to_dict() == recipe.to_dict()
                else "updated"
            )
            changes.append(
                FoodChange(
                    food_key=food_key,
                    change_type=change_type,
                    old_model=old_model,
                    new_model=new_model,
                    warnings=tuple(warnings),
                )
            )
            proposal_warnings.extend(
                f"{kind.display_name}: {item}" for item in warnings
            )

        source_data = {
            "models": [item.to_fingerprint_dict() for item in evidence],
            "fixed_foods": sorted(FIXED_FOOD_KINDS),
        }
        generation_sources = (
            ("model", "rules") if self._advisor_status == "used" else ("rules",)
        )
        generation_note = (
            "模型建议与规则校验共同生成"
            if self._advisor_status == "used"
            else "规划模型不可用，使用规则生成"
            if self._advisor_status == "failed"
            else "未配置规划模型，使用规则生成"
        )
        return FoodUpdateProposal(
            catalog=FoodCatalog(
                version=max(current_catalog.version + 1, 1),
                source_fingerprint=fingerprint_source(source_data),
                generation_sources=generation_sources,
                generation_note=generation_note,
                recipes=recipes,
            ),
            changes=tuple(changes),
            warnings=tuple(proposal_warnings),
            generation_sources=generation_sources,
            advisor_error=self._advisor_error,
        )

    def _advisor_recommendations(
        self, evidence: Sequence[ModelEvidence]
    ) -> Mapping[str, str]:
        if self.advisor is None or not evidence:
            return {}
        try:
            raw = self.advisor.recommend(tuple(FIXED_FOOD_KINDS), evidence)
            self._advisor_status = "used"
        except Exception as exc:
            self._advisor_status = "failed"
            self._advisor_error = str(exc)
            return {}
        allowed_models = {item.model for item in evidence}
        return {
            food_key: model
            for food_key, model in raw.items()
            if food_key in FIXED_FOOD_KINDS and model in allowed_models
        }

    def _select_model(
        self,
        food_key: str,
        evidence: Sequence[ModelEvidence],
        recommendations: Mapping[str, str],
    ) -> ModelEvidence | None:
        if food_key == "emergency":
            # 紧急粮是断网/云端全部不可用时的最后防线。
            # 只要有已验证本地模型，规则必须压过规划模型的云端推荐。
            local_candidates = [
                item
                for item in evidence
                if item.local and _meets_food_requirements(food_key, item)
            ]
            return min(local_candidates, key=_cheap_fast_score, default=None)

        recommended = recommendations.get(food_key)
        if recommended:
            selected = next(
                (item for item in evidence if item.model == recommended), None
            )
            if selected and _meets_food_requirements(food_key, selected):
                return selected

        candidates = [
            item for item in evidence if _meets_food_requirements(food_key, item)
        ]
        if not candidates:
            return None
        if food_key == "coarse":
            local = [item for item in candidates if item.local]
            return min(local or candidates, key=_cheap_fast_score)
        if food_key in {"focus", "premium"}:
            return max(candidates, key=lambda item: (item.cost_grade, -_latency(item)))
        return min(candidates, key=_balanced_score)

    def _build_recipe(
        self,
        food_key: str,
        evidence: Sequence[ModelEvidence],
        selected: ModelEvidence | None,
        existing: FoodRecipe | None,
    ) -> FoodRecipe:
        kind = FIXED_FOOD_KINDS[food_key]
        if selected is None:
            return FoodRecipe(
                key=food_key,
                display_name=kind.display_name,
                description=kind.description,
                primary=ExecutionProfile(model=""),
                validation_status=FoodValidationStatus.FAILED,
                source="auto",
                locked_fields=existing.locked_fields if existing else (),
            )

        reasoning = (
            ReasoningProfile.DEEP
            if food_key in {"focus", "premium"}
            else ReasoningProfile.LOW
            if food_key in {"coarse", "emergency"}
            else ReasoningProfile.BALANCED
        )
        tools = (
            ("web_search", "local_file", "code_sandbox") if food_key == "tool" else ()
        )
        fallbacks = _fallback_profiles(food_key, selected, evidence)
        deep_candidate = _deep_candidate(selected, evidence)
        return FoodRecipe(
            key=food_key,
            display_name=kind.display_name,
            description=kind.description,
            primary=ExecutionProfile(
                model=selected.model,
                reasoning_profile=reasoning,
                max_tokens=4000 if food_key in {"focus", "premium"} else 1500,
                temperature=0.2 if food_key in {"focus", "tool", "premium"} else 0.7,
                tools=tools,
                provider_options=_default_provider_options(selected.model, reasoning),
            ),
            deep=(
                ExecutionProfile(
                    model=deep_candidate.model,
                    reasoning_profile=ReasoningProfile.DEEP,
                    max_tokens=5000,
                    temperature=0.1,
                    tools=tools,
                    provider_options=_default_provider_options(
                        deep_candidate.model, ReasoningProfile.DEEP
                    ),
                )
                if deep_candidate and deep_candidate.model != selected.model
                else None
            ),
            verifier=ExecutionProfile(
                model=selected.model,
                reasoning_profile=ReasoningProfile.VERIFY,
                max_tokens=800,
                temperature=0.0,
                provider_options=_default_provider_options(
                    selected.model, ReasoningProfile.VERIFY
                ),
            ),
            technical_fallbacks=fallbacks,
            validation_status=FoodValidationStatus.UNVERIFIED,
            source="auto",
            locked_fields=existing.locked_fields if existing else (),
        )


def validate_food_recipe(
    recipe: FoodRecipe, evidence: Sequence[ModelEvidence]
) -> list[str]:
    if not recipe.primary.model:
        return ["粮食未配置主模型，请先自动更新粮食策略"]
    all_models = {item.model: item for item in evidence}
    selected = all_models.get(recipe.primary.model)
    if selected is None:
        return ["主模型尚无真实验证记录"]
    if not selected.verified:
        return ["主模型最近一次真实调用验证失败"]
    required = FIXED_FOOD_KINDS[recipe.key].required_capabilities
    missing = [
        capability for capability in required if not _supports(selected, capability)
    ]
    warnings = [f"主模型缺少能力: {', '.join(missing)}"] if missing else []
    if recipe.key == "emergency" and not selected.local:
        warnings.append("紧急粮主模型必须是已验证本地模型")
    for fallback in recipe.technical_fallbacks:
        fallback_evidence = all_models.get(fallback.model)
        if fallback_evidence is None:
            warnings.append(f"备用模型尚无真实验证记录: {fallback.model}")
        elif not fallback_evidence.verified:
            warnings.append(f"备用模型真实调用验证失败: {fallback.model}")
    return warnings


def _meets_food_requirements(food_key: str, model: ModelEvidence) -> bool:
    return all(
        _supports(model, capability)
        for capability in FIXED_FOOD_KINDS[food_key].required_capabilities
    )


def _supports(model: ModelEvidence, capability: str) -> bool:
    if capability == "tools":
        return model.tool_test_passed
    if capability == "reasoning" and _looks_reasoning_capable(model):
        return True
    return capability in model.capabilities


def _looks_reasoning_capable(model: ModelEvidence) -> bool:
    """仅对显式的推理模型家族名称应用确定性能力规则。"""
    name = f"{model.display_name} {model.model}".lower().replace("_", "-")
    markers = (
        "reasoner",
        "reasoning",
        "deepseek-r1",
        "glm-5",
        "glm-5.1",
        "glm-5.2",
        "kimi-k2",
        "minimax-m2",
        "qwen3",
        "o1",
        "o3",
    )
    return any(marker in name for marker in markers)


def _latency(model: ModelEvidence) -> float:
    return model.latency_ms if model.latency_ms is not None else 1_000_000.0


def _cheap_fast_score(model: ModelEvidence) -> tuple[int, float]:
    return model.cost_grade, _latency(model)


def _balanced_score(model: ModelEvidence) -> tuple[int, float]:
    return abs(model.cost_grade - 2), _latency(model)


def _deep_candidate(
    selected: ModelEvidence, evidence: Sequence[ModelEvidence]
) -> ModelEvidence | None:
    candidates = [
        item
        for item in evidence
        if "reasoning" in item.capabilities and item.model != selected.model
    ]
    return max(candidates, key=lambda item: item.cost_grade, default=None)


def _fallback_profiles(
    food_key: str,
    selected: ModelEvidence,
    evidence: Sequence[ModelEvidence],
) -> tuple[ExecutionProfile, ...]:
    candidates = [
        item
        for item in evidence
        if item.model != selected.model
        and item.local
        and _meets_food_requirements(food_key, item)
    ]
    if not candidates:
        return ()
    fallback = min(candidates, key=_cheap_fast_score)
    return (
        ExecutionProfile(
            model=fallback.model,
            reasoning_profile=ReasoningProfile.LOW,
            max_tokens=1200,
            provider_options=_default_provider_options(
                fallback.model, ReasoningProfile.LOW
            ),
        ),
    )


def _default_provider_options(
    model_ref: str, reasoning: ReasoningProfile
) -> dict[str, object]:
    """仅提供仓库已支持的安全默认值；云端差异留在配方中显式配置。"""
    provider = model_ref.split("/", 1)[0] if "/" in model_ref else "ollama"
    if provider == "ollama":
        return {
            "options": {
                "think": reasoning not in {ReasoningProfile.OFF, ReasoningProfile.LOW}
            }
        }
    return {}
