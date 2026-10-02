"""Typed policy for the bounded biological-family generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Final

FAMILY_GENERATION_VERSION: Final = "family-generation.v1"


@dataclass(frozen=True)
class MarriageAgeConfig:
    """Marriage-age curve parameters inside the species' mature stage."""

    peak_fraction: float = 0.25
    stddev_fraction: float = 0.25
    never_married_probability: float = 0.10

    def validate(self) -> None:
        if not 0.0 <= self.peak_fraction <= 1.0:
            raise ValueError("family.marriage.peak_fraction 必须在 [0, 1] 内")
        if not isfinite(self.stddev_fraction) or self.stddev_fraction <= 0.0:
            raise ValueError("family.marriage.stddev_fraction 必须为正数")
        if not 0.0 <= self.never_married_probability <= 1.0:
            raise ValueError(
                "family.marriage.never_married_probability 必须在 [0, 1] 内"
            )


@dataclass(frozen=True)
class PartnerAgeGapConfig:
    """Allowed partner-age offsets and their relative weights."""

    offsets: tuple[int, ...] = (-2, -1, 0, 1, 2)
    weights: tuple[float, ...] = (1.0, 2.0, 4.0, 2.0, 1.0)

    def validate(self) -> None:
        if not self.offsets or len(self.offsets) != len(self.weights):
            raise ValueError("family.partner_age_gap 的 offsets/weights 长度必须一致")
        if len(set(self.offsets)) != len(self.offsets):
            raise ValueError("family.partner_age_gap.offsets 必须唯一")
        if any(not isfinite(weight) or weight < 0.0 for weight in self.weights):
            raise ValueError("family.partner_age_gap.weights 不能为负数")
        if sum(self.weights) <= 0.0:
            raise ValueError("family.partner_age_gap.weights 不能全为零")
        if tuple(sorted(self.offsets)) != self.offsets:
            raise ValueError("family.partner_age_gap.offsets 必须升序")


@dataclass(frozen=True)
class ChildrenConfig:
    """Lifetime child plan and post-marriage birth sampling parameters."""

    count_distribution: tuple[tuple[int, float], ...] = (
        (0, 0.03),
        (1, 0.05),
        (2, 0.50),
        (3, 0.42),
    )
    max_count: int = 3
    birth_lag_decay: float = 0.75
    sex_distribution: tuple[tuple[str, float], ...] = (
        ("male", 0.50),
        ("female", 0.50),
    )

    def validate(self) -> None:
        if self.max_count < 1:
            raise ValueError("family.children.max_count 必须为正整数")
        counts = [count for count, _ in self.count_distribution]
        if not counts or len(counts) != len(set(counts)):
            raise ValueError("family.children.count_distribution 的子女数必须唯一")
        if any(
            count < 0 or count > self.max_count or not isfinite(weight) or weight < 0.0
            for count, weight in self.count_distribution
        ):
            raise ValueError("family.children.count_distribution 的值无效")
        if sum(weight for _, weight in self.count_distribution) <= 0.0:
            raise ValueError("family.children.count_distribution 权重不能全为零")
        if not 0.0 < self.birth_lag_decay < 1.0:
            raise ValueError("family.children.birth_lag_decay 必须在 (0, 1) 内")
        genders = [gender for gender, _ in self.sex_distribution]
        if len(genders) != len(set(genders)) or not genders:
            raise ValueError("family.children.sex_distribution 的性别必须唯一")
        if set(genders) - {"male", "female"}:
            raise ValueError("family.children.sex_distribution 只能使用 male/female")
        if (
            any(
                not gender.strip() or not isfinite(weight) or weight < 0.0
                for gender, weight in self.sex_distribution
            )
            or sum(weight for _, weight in self.sex_distribution) <= 0.0
        ):
            raise ValueError("family.children.sex_distribution 的值无效")


@dataclass(frozen=True)
class LifespanConfig:
    """Conditioned lifespan sampler used when materializing family people."""

    early_cdf_power: int = 4
    late_survival_power: int = 2

    def validate(self) -> None:
        for value in (self.early_cdf_power, self.late_survival_power):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= 64
            ):
                raise ValueError("family.lifespan 的曲线指数必须是 1 到 64 的整数")


@dataclass(frozen=True)
class AncestorExpansionConfig:
    """Bound the optional ancestor projection separately from biology."""

    max_upward_generations: int = 1
    stop_at_elder: bool = True

    def validate(self) -> None:
        if not 0 <= self.max_upward_generations <= 1:
            raise ValueError(
                "family.ancestor_expansion.max_upward_generations 目前只能是 0 或 1"
            )


@dataclass(frozen=True)
class FamilyGenerationConfig:
    """All tunable inputs for the biological-family generation slice."""

    generation_version: str = FAMILY_GENERATION_VERSION
    marriage: MarriageAgeConfig = field(default_factory=MarriageAgeConfig)
    partner_age_gap: PartnerAgeGapConfig = field(default_factory=PartnerAgeGapConfig)
    children: ChildrenConfig = field(default_factory=ChildrenConfig)
    lifespan: LifespanConfig = field(default_factory=LifespanConfig)
    ancestor_expansion: AncestorExpansionConfig = field(
        default_factory=AncestorExpansionConfig
    )

    def validate(self) -> None:
        if self.generation_version != FAMILY_GENERATION_VERSION:
            raise ValueError("不支持的 family_generation_version")
        self.marriage.validate()
        self.partner_age_gap.validate()
        self.children.validate()
        self.lifespan.validate()
        self.ancestor_expansion.validate()
