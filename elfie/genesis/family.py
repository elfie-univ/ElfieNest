"""Temporary family facts on one local-year timeline (the present is year zero)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable

from elfie.profile import SpeciesGenesisProfile

from .contracts import GenesisError
from .world import FAMILY_LIFE_STAGE, GenerationPolicy


@dataclass(frozen=True)
class FamilyPerson:
    person_id: str
    species_id: str
    gender: str
    birth_year: int
    death_year: int | None = None


@dataclass(frozen=True)
class FamilyUnion:
    union_id: str
    first: FamilyPerson
    second: FamilyPerson
    formed_year: int


@dataclass(frozen=True)
class FamilyGroup:
    union: FamilyUnion
    children: tuple[FamilyPerson, ...]


@dataclass(frozen=True)
class CoreFamily:
    protagonist: FamilyPerson
    origin: FamilyGroup
    own: FamilyGroup | None


@dataclass(frozen=True)
class AncestorFamily:
    """One parent's bounded origin family, including that parent as a child."""

    anchor: FamilyPerson
    group: FamilyGroup


@dataclass(frozen=True)
class PartnerOriginFamily:
    """One partner's bounded origin family, including that partner as a child."""

    anchor: FamilyPerson
    group: FamilyGroup


@dataclass(frozen=True)
class DescendantFamily:
    """One bounded descendant branch rooted at an existing family member."""

    anchor: FamilyPerson
    group: FamilyGroup


@dataclass(frozen=True)
class FamilyGraph:
    """The complete bounded family graph for one protagonist.

    ``core`` is the protagonist's one-degree family. ``ancestor_families``
    contains at most one upward generation and is independently gated by the
    parents' current elder-stage status. Descendant branches always evaluate
    each eligible sibling and child, expanding them to nieces/nephews and
    grandchildren. Collateral branches expand aunts/uncles to cousins only
    when an ancestor branch exists. Every branch is bounded to one additional
    union and never recursively expands the new partners. A married
    protagonist also receives the partner's parents and siblings as one
    terminal origin branch; that branch is not expanded further.
    """

    core: CoreFamily
    ancestor_families: tuple[AncestorFamily, ...] = ()
    sibling_families: tuple[DescendantFamily, ...] = ()
    child_families: tuple[DescendantFamily, ...] = ()
    aunt_uncle_families: tuple[DescendantFamily, ...] = ()
    partner_origin: PartnerOriginFamily | None = None


class FamilyGenerator:
    """Generate unions and shared child sets without names, stories or storage."""

    def __init__(
        self,
        *,
        species_id: str,
        genesis: SpeciesGenesisProfile,
        policy: GenerationPolicy,
        seed_for: Callable[[str], int],
    ) -> None:
        self.species_id = species_id
        self.genesis = genesis
        self.policy = policy
        self.seed_for = seed_for
        try:
            mature_start, mature_end = genesis.stage_ranges[FAMILY_LIFE_STAGE]
        except (KeyError, ValueError) as error:
            raise GenesisError("物种必须声明 mature 生命阶段") from error
        if not 0 <= mature_start < mature_end <= genesis.terminal_age_years:
            raise GenesisError("mature 生命阶段边界无效")
        try:
            policy.family.validate()
        except ValueError as error:
            raise GenesisError(str(error)) from error

    def _mature_age_range(self) -> range:
        start, end = self.genesis.stage_ranges[FAMILY_LIFE_STAGE]
        return range(start, end)

    def _mature_bounds(self) -> tuple[int, int]:
        start, end = self.genesis.stage_ranges[FAMILY_LIFE_STAGE]
        return start, end

    def _marriage_weights(self, ages: tuple[int, ...]) -> tuple[float, ...]:
        mature_start, mature_end = self._mature_bounds()
        width = mature_end - mature_start
        marriage = self.policy.family.marriage
        peak = mature_start + (width - 1) * marriage.peak_fraction
        stddev = max(0.5, width * marriage.stddev_fraction)
        logs = tuple(-0.5 * ((age - peak) / stddev) ** 2 for age in ages)
        peak = max(logs)
        return tuple(math.exp(value - peak) for value in logs)

    def _alive(self, person: FamilyPerson, year: int) -> bool:
        return person.birth_year <= year and (
            person.death_year is None or year < person.death_year
        )

    def _check_person(self, person: FamilyPerson) -> None:
        if (
            not person.person_id
            or person.species_id != self.species_id
            or person.gender not in {"male", "female"}
            or person.birth_year > 0
            or (
                person.death_year is None
                and -person.birth_year >= self.genesis.terminal_age_years
            )
            or (
                person.death_year is not None
                and not 0
                < person.death_year - person.birth_year
                <= self.genesis.terminal_age_years
            )
        ):
            raise GenesisError("家庭人物身份或生命时间无效")

    def _fertile(self, person: FamilyPerson, year: int) -> bool:
        age = year - person.birth_year
        return (
            self._alive(person, year)
            and self.genesis.stage_ranges[FAMILY_LIFE_STAGE][0]
            <= age
            < self.genesis.stage_ranges[FAMILY_LIFE_STAGE][1]
        )

    def _can_expand_descendants(self, person: FamilyPerson) -> bool:
        """Require at least one legal mature-stage year before the present."""

        mature_start, mature_end = self._mature_bounds()
        first_mature_year = person.birth_year + mature_start
        last_mature_year = min(0, person.birth_year + mature_end - 1)
        if person.death_year is not None:
            last_mature_year = min(last_mature_year, person.death_year - 1)
        return first_mature_year <= last_mature_year

    def _generate_descendant_family(
        self,
        anchor: FamilyPerson,
        *,
        union_id: str,
        partner_id: str,
        child_id_prefix: str,
    ) -> DescendantFamily | None:
        """Generate one partner/child branch without expanding it further."""

        if not self._can_expand_descendants(anchor):
            return None
        union = self.generate_partner(
            anchor,
            union_id=union_id,
            partner_id=partner_id,
        )
        if union is None:
            return None
        return DescendantFamily(
            anchor,
            self.generate_children(union, child_id_prefix=child_id_prefix),
        )

    def _effective_fertility_years(self, union: FamilyUnion) -> int:
        """Return usable post-marriage years through the present (year zero)."""
        parent_end_years = tuple(
            parent.birth_year + self.genesis.stage_ranges[FAMILY_LIFE_STAGE][1] - 1
            for parent in (union.first, union.second)
        )
        if any(parent.death_year is not None for parent in (union.first, union.second)):
            parent_end_years = (
                *parent_end_years,
                *(
                    parent.death_year - 1
                    for parent in (union.first, union.second)
                    if parent.death_year is not None
                ),
            )
        latest_birth_year = min((*parent_end_years, 0))
        return max(0, latest_birth_year - union.formed_year)

    def _sample_child_lags(
        self, union: FamilyUnion, occupied: set[int], count: int
    ) -> tuple[int, ...]:
        """Sample distinct post-marriage birth lags before applying current time."""
        if count < 0:
            raise GenesisError("待生成的子女数不能为负数")
        available = [
            lag
            for lag in range(1, self.genesis.terminal_age_years + 1)
            if lag not in occupied
        ]
        if count > len(available):
            raise GenesisError("子女出生年份候选范围不足")
        decay = self.policy.family.children.birth_lag_decay
        rng = random.Random(self.seed_for(f"family-child-birth-lags:{union.union_id}"))
        selected: list[int] = []
        for _ in range(count):
            weights = tuple(decay ** (lag - 1) for lag in available)
            lag = rng.choices(available, weights=weights, k=1)[0]
            selected.append(lag)
            available.remove(lag)
        return tuple(selected)

    def _draw_child_count(self, union_id: str) -> int:
        distribution = self.policy.family.children.count_distribution
        total = sum(weight for _, weight in distribution)
        if total <= 0:
            raise GenesisError("子女数分布权重必须为正")
        draw = random.Random(self.seed_for(f"family-child-count:{union_id}")).random()
        for value, weight in distribution:
            draw -= weight / total
            if draw <= 0:
                return value
        return distribution[-1][0]

    def _draw_child_gender(self, union_id: str, year: int) -> str:
        genders, weights = zip(*self.policy.family.children.sex_distribution)
        return random.Random(
            self.seed_for(f"family-child-year:{union_id}:{year}:gender")
        ).choices(genders, weights=weights, k=1)[0]

    def _person(
        self, person_id: str, gender: str, birth_year: int, survival_year: int
    ) -> FamilyPerson:
        death_age = _sample_conditioned_death_age(
            elder_start_age=self.genesis.stage_ranges["elder"][0],
            median_age=self.genesis.median_age_years,
            terminal_age=self.genesis.terminal_age_years,
            minimum_survival_age=max(0, survival_year - birth_year),
            early_cdf_power=self.policy.family.lifespan.early_cdf_power,
            late_survival_power=self.policy.family.lifespan.late_survival_power,
            uniform=random.Random(self.seed_for(f"lifespan:{person_id}")).random(),
        )
        return FamilyPerson(
            person_id, self.species_id, gender, birth_year, birth_year + death_age
        )

    def _partner_birth_options(
        self,
        person: FamilyPerson,
        *,
        formed_year: int,
        partner_id: str,
        anchored_children: tuple[FamilyPerson, ...],
        required: bool,
    ) -> tuple[int, ...]:
        """Return partner birth years compatible with one fixed union year."""
        minimum, maximum_exclusive = self._mature_bounds()
        gap_config = self.policy.family.partner_age_gap
        births: list[int] = []
        for gap in gap_config.offsets:
            age = formed_year - person.birth_year + gap
            if not minimum <= age < maximum_exclusive:
                continue
            birth = formed_year - age
            if not required and -birth >= self.genesis.terminal_age_years:
                continue
            other = FamilyPerson(
                partner_id,
                self.species_id,
                "female" if person.gender == "male" else "male",
                birth,
            )
            survival = max(
                (min(0, child.birth_year) for child in anchored_children),
                default=formed_year,
            )
            if survival - birth < self.genesis.terminal_age_years and all(
                self._fertile(other, child.birth_year) for child in anchored_children
            ):
                births.append(birth)
        return tuple(births)

    def _generate_partner_at_formed_year(
        self,
        person: FamilyPerson,
        *,
        formed_year: int,
        union_id: str,
        partner_id: str,
        anchored_children: tuple[FamilyPerson, ...] = (),
        required: bool = True,
    ) -> FamilyUnion:
        """Generate only the partner while keeping an already chosen union year."""
        if formed_year > 0 or not self._alive(person, formed_year):
            raise GenesisError("固定的结婚年份无效")
        births = self._partner_birth_options(
            person,
            formed_year=formed_year,
            partner_id=partner_id,
            anchored_children=anchored_children,
            required=required,
        )
        if not births:
            raise GenesisError("固定的结婚年份没有合法伴侣")
        age_weights = self._marriage_weights(
            tuple(formed_year - birth for birth in births)
        )
        gap_weights = dict(
            zip(
                self.policy.family.partner_age_gap.offsets,
                self.policy.family.partner_age_gap.weights,
            )
        )
        partner_weights = tuple(
            age_weight * gap_weights[person.birth_year - birth]
            for birth, age_weight in zip(births, age_weights)
        )
        birth = random.Random(self.seed_for(f"family-partner:{union_id}:age")).choices(
            births, weights=partner_weights, k=1
        )[0]
        survival = max(
            (min(0, child.birth_year) for child in anchored_children),
            default=formed_year,
        )
        other = self._person(
            partner_id,
            "female" if person.gender == "male" else "male",
            birth,
            survival,
        )
        return FamilyUnion(union_id, person, other, formed_year)

    def generate_partner(
        self,
        person: FamilyPerson,
        *,
        union_id: str,
        partner_id: str,
        anchored_children: tuple[FamilyPerson, ...] = (),
        required: bool = False,
    ) -> FamilyUnion | None:
        """Draw marriage age once; known children condition that same age curve."""
        self._check_person(person)
        if not partner_id.strip() or partner_id == person.person_id:
            raise GenesisError("伴侣不能是本人")
        for child in anchored_children:
            self._check_person(child)
            if child.person_id in {person.person_id, partner_id} or not self._fertile(
                person, child.birth_year
            ):
                raise GenesisError("已有子女不满足亲子生育约束")
        required = required or bool(anchored_children)
        minimum, maximum_exclusive = self._mature_bounds()
        earliest = person.birth_year + minimum
        latest = min(0, person.birth_year + maximum_exclusive - 1)
        if person.death_year is not None:
            latest = min(latest, person.death_year - 1)
        if anchored_children:
            latest = min(latest, min(c.birth_year for c in anchored_children) - 1)
        time_rng = random.Random(self.seed_for(f"family-partner:{union_id}:time"))
        if not required:
            if (
                random.Random(
                    self.seed_for(f"family-partner:{union_id}:never-married")
                ).random()
                < self.policy.family.marriage.never_married_probability
            ):
                return None
            ages = tuple(self._mature_age_range())
            marriage_age = time_rng.choices(
                ages, weights=self._marriage_weights(ages), k=1
            )[0]
            formed = person.birth_year + marriage_age
            if formed > 0 or not self._alive(person, formed):
                return None
            earliest = latest = formed
        options = {
            year: self._partner_birth_options(
                person,
                formed_year=year,
                partner_id=partner_id,
                anchored_children=anchored_children,
                required=required,
            )
            for year in range(earliest, latest + 1)
        }
        options = {year: births for year, births in options.items() if births}
        if not options:
            if required:
                raise GenesisError("已有子女没有合法的双亲结伴时间")
            return None
        if required:
            years = tuple(options)
            formed = time_rng.choices(
                years,
                weights=self._marriage_weights(
                    tuple(year - person.birth_year for year in years)
                ),
                k=1,
            )[0]
        return self._generate_partner_at_formed_year(
            person,
            formed_year=formed,
            union_id=union_id,
            partner_id=partner_id,
            anchored_children=anchored_children,
            required=required,
        )

    def _parent_candidates(
        self,
        child: FamilyPerson,
        *,
        union_id: str,
        mother_id: str,
        father_id: str,
    ) -> dict[int, tuple[tuple[int, int, FamilyPerson], ...]]:
        """Build legal (marriage age, marriage year, father) candidates by child lag."""
        minimum_marriage_age, maximum_marriage_age_exclusive = self._mature_bounds()
        minimum_parent_age, maximum_parent_age_exclusive = self._mature_bounds()
        candidates: dict[int, tuple[tuple[int, int, FamilyPerson], ...]] = {}
        survival = min(0, child.birth_year)
        for lag in range(1, self.genesis.terminal_age_years + 1):
            formed = child.birth_year - lag
            viable: list[tuple[int, int, FamilyPerson]] = []
            for marriage_age in range(
                minimum_marriage_age, maximum_marriage_age_exclusive
            ):
                age_at_child = marriage_age + lag
                if not (
                    minimum_parent_age <= age_at_child < maximum_parent_age_exclusive
                ):
                    continue
                birth = formed - marriage_age
                if survival - birth >= self.genesis.terminal_age_years:
                    continue
                father = self._person(father_id, "male", birth, survival)
                if self._partner_birth_options(
                    father,
                    formed_year=formed,
                    partner_id=mother_id,
                    anchored_children=(child,),
                    required=True,
                ):
                    viable.append((marriage_age, formed, father))
            if viable:
                candidates[lag] = tuple(viable)
        if not candidates:
            raise GenesisError("已有孩子没有合法的父母结婚与生育组合")
        return candidates

    def _sample_parent_child_lag(
        self, union_id: str, candidates: tuple[int, ...]
    ) -> int:
        decay = self.policy.family.children.birth_lag_decay
        weights = tuple(decay ** (lag - 1) for lag in candidates)
        return random.Random(
            self.seed_for(f"family-parent-child-lag:{union_id}")
        ).choices(candidates, weights=weights, k=1)[0]

    def generate_parents(
        self,
        child: FamilyPerson,
        *,
        union_id: str = "parents",
        mother_id: str = "family-parent-1",
        father_id: str = "family-parent-2",
    ) -> FamilyUnion:
        """Reverse-generate only a child's parents and their fixed union year."""
        self._check_person(child)
        if (
            not mother_id.strip()
            or not father_id.strip()
            or len({mother_id, father_id, child.person_id}) != 3
        ):
            raise GenesisError("父母和孩子必须具有不同的有效身份")
        candidates = self._parent_candidates(
            child,
            union_id=union_id,
            mother_id=mother_id,
            father_id=father_id,
        )
        lag = self._sample_parent_child_lag(union_id, tuple(candidates))
        options = candidates[lag]
        marriage_ages = tuple(option[0] for option in options)
        marriage_age = random.Random(
            self.seed_for(f"family-parent:{union_id}:father-age")
        ).choices(
            marriage_ages,
            weights=self._marriage_weights(marriage_ages),
            k=1,
        )[0]
        _, formed, father = next(
            option for option in options if option[0] == marriage_age
        )
        parents = self._generate_partner_at_formed_year(
            father,
            formed_year=formed,
            union_id=union_id,
            partner_id=mother_id,
            anchored_children=(child,),
            required=True,
        )
        return FamilyUnion(union_id, parents.second, parents.first, formed)

    def generate_children(
        self,
        union: FamilyUnion,
        *,
        existing: tuple[FamilyPerson, ...] = (),
        child_id_prefix: str = "family-child",
    ) -> FamilyGroup:
        """Plan distinct birth lags, then materialize only births valid today."""
        for parent in (union.first, union.second):
            self._check_person(parent)
            if (
                union.formed_year > 0
                or union.formed_year - parent.birth_year
                < self.genesis.stage_ranges[FAMILY_LIFE_STAGE][0]
                or union.formed_year - parent.birth_year
                >= self.genesis.stage_ranges[FAMILY_LIFE_STAGE][1]
                or not self._alive(parent, union.formed_year)
            ):
                raise GenesisError("双亲结伴时间无效")
        allowed_age_gaps = {
            abs(offset) for offset in self.policy.family.partner_age_gap.offsets
        }
        if (
            union.first.person_id == union.second.person_id
            or union.first.gender == union.second.gender
            or abs(union.first.birth_year - union.second.birth_year)
            not in allowed_age_gaps
        ):
            raise GenesisError("双亲身份或性别组合不合法")
        ids = {c.person_id for c in existing}
        occupied = {c.birth_year for c in existing}
        if (
            len(ids) != len(existing)
            or len(occupied) != len(existing)
            or len(existing) > self.policy.family.children.max_count
            or ids & {union.first.person_id, union.second.person_id}
        ):
            raise GenesisError("已有子女集合、出生年份或人数不合法")
        for child in existing:
            self._check_person(child)
            if child.birth_year <= union.formed_year:
                raise GenesisError("已有子女必须出生在结婚之后")
        target = self._draw_child_count(union.union_id)
        count = min(
            self.policy.family.children.max_count,
            max(len(existing), target),
        )
        planned_lags = {child.birth_year - union.formed_year for child in existing}
        planned_lags.update(
            self._sample_child_lags(union, planned_lags, count - len(existing))
        )
        effective_years = self._effective_fertility_years(union)
        if any(
            child.birth_year - union.formed_year > effective_years
            or not self._fertile(parent, child.birth_year)
            for child in existing
            for parent in (union.first, union.second)
        ):
            raise GenesisError("已有子女超出当前有效生育年限")
        actual_lags = tuple(
            sorted(
                lag
                for lag in planned_lags
                if lag <= effective_years
                and all(
                    self._fertile(parent, union.formed_year + lag)
                    for parent in (union.first, union.second)
                )
            )
        )
        existing_by_lag = {
            child.birth_year - union.formed_year: child for child in existing
        }
        children = list(existing_by_lag.values())
        reserved_ids = ids | {union.first.person_id, union.second.person_id}
        index = 1
        for lag in actual_lags:
            if lag in existing_by_lag:
                continue
            year = union.formed_year + lag
            while f"{child_id_prefix}-{index}" in reserved_ids:
                index += 1
            person_id = f"{child_id_prefix}-{index}"
            gender = self._draw_child_gender(union.union_id, year)
            children.append(self._person(person_id, gender, year, year))
            ids.add(person_id)
            index += 1
        return FamilyGroup(union, tuple(sorted(children, key=lambda c: c.birth_year)))

    def generate_core_family(self, person: FamilyPerson) -> CoreFamily:
        """Compose just parents/siblings and the protagonist's partner/children."""
        parents = self.generate_parents(person)
        origin = self.generate_children(
            parents, existing=(person,), child_id_prefix="family-sibling"
        )
        partner = self.generate_partner(
            person, union_id="partner", partner_id="family-partner"
        )
        own = self.generate_children(partner) if partner is not None else None
        return CoreFamily(person, origin, own)

    def generate_family_graph(self, person: FamilyPerson) -> FamilyGraph:
        """Compose a role-bounded family graph from the shared core operations.

        Parents may add one ancestor generation, siblings may add
        nieces/nephews, children may add grandchildren, and aunts/uncles may
        add cousins. Upward expansion is skipped only after the protagonist
        has a partner and both parents are in the elder stage. The new
        partners and their families are terminal nodes; this is deliberately
        not an unrestricted recursive traversal.
        """

        core = self.generate_core_family(person)
        ancestor_families: list[AncestorFamily] = []
        if self.policy.family.ancestor_expansion.max_upward_generations >= 1:
            elder_start = self.genesis.stage_ranges["elder"][0]
            parents = (core.origin.union.first, core.origin.union.second)
            skip_ancestor_expansion = (
                self.policy.family.ancestor_expansion.stop_at_elder
                and core.own is not None
                and all(-parent.birth_year >= elder_start for parent in parents)
            )
            if not skip_ancestor_expansion:
                for parent_index, parent in enumerate(parents, start=1):
                    union = self.generate_parents(
                        parent,
                        union_id=parent.person_id,
                        mother_id=f"family-grandparent-{parent_index}-1",
                        father_id=f"family-grandparent-{parent_index}-2",
                    )
                    group = self.generate_children(
                        union,
                        existing=(parent,),
                        child_id_prefix=f"family-aunt-uncle-{parent_index}",
                    )
                    ancestor_families.append(AncestorFamily(parent, group))
        partner_origin: PartnerOriginFamily | None = None
        if core.own is not None:
            partner = (
                core.own.union.second
                if core.own.union.first.person_id == person.person_id
                else core.own.union.first
            )
            union = self.generate_parents(
                partner,
                union_id="family-partner-parents",
                mother_id="family-partner-parent-1",
                father_id="family-partner-parent-2",
            )
            group = self.generate_children(
                union,
                existing=(partner,),
                child_id_prefix="family-partner-sibling",
            )
            partner_origin = PartnerOriginFamily(partner, group)
        sibling_families: list[DescendantFamily] = []
        for index, sibling in enumerate(
            (
                child
                for child in core.origin.children
                if child.person_id != person.person_id
            ),
            start=1,
        ):
            branch = self._generate_descendant_family(
                sibling,
                union_id=f"{sibling.person_id}-union",
                partner_id=f"{sibling.person_id}-partner",
                child_id_prefix=f"family-niece-nephew-{index}",
            )
            if branch is not None:
                sibling_families.append(branch)

        child_families: list[DescendantFamily] = []
        if core.own is not None:
            for index, child in enumerate(core.own.children, start=1):
                branch = self._generate_descendant_family(
                    child,
                    union_id=f"{child.person_id}-union",
                    partner_id=f"{child.person_id}-partner",
                    child_id_prefix=f"family-grandchild-{index}",
                )
                if branch is not None:
                    child_families.append(branch)

        aunt_uncle_families: list[DescendantFamily] = []
        for parent_index, ancestor_branch in enumerate(ancestor_families, start=1):
            parent_id = ancestor_branch.anchor.person_id
            for index, relative in enumerate(
                (
                    child
                    for child in ancestor_branch.group.children
                    if child.person_id != parent_id
                ),
                start=1,
            ):
                relative_branch = self._generate_descendant_family(
                    relative,
                    union_id=f"{relative.person_id}-union",
                    partner_id=f"{relative.person_id}-partner",
                    child_id_prefix=f"family-cousin-{parent_index}-{index}",
                )
                if relative_branch is not None:
                    aunt_uncle_families.append(relative_branch)

        return FamilyGraph(
            core,
            tuple(ancestor_families),
            tuple(sibling_families),
            tuple(child_families),
            tuple(aunt_uncle_families),
            partner_origin,
        )


def _sample_conditioned_death_age(
    *,
    elder_start_age: int,
    median_age: int,
    terminal_age: int,
    minimum_survival_age: int,
    early_cdf_power: int,
    late_survival_power: int,
    uniform: float,
) -> int:
    """Sample once, conditioned on survival through already-established facts."""
    if (
        not 0 <= elder_start_age < median_age < terminal_age
        or minimum_survival_age < 0
        or minimum_survival_age >= terminal_age
        or any(
            isinstance(power, bool)
            or not isinstance(power, int)
            or not 1 <= power <= 64
            for power in (early_cdf_power, late_survival_power)
        )
    ):
        raise GenesisError("条件寿命抽样的生命边界无效")
    if not 0.0 < uniform < 1.0:
        raise GenesisError("条件寿命抽样值必须位于 (0, 1)")
    if minimum_survival_age <= elder_start_age:
        lower_cdf = 0.0
    elif minimum_survival_age <= median_age:
        progress = (minimum_survival_age - elder_start_age) / (
            median_age - elder_start_age
        )
        lower_cdf = 0.5 * progress**early_cdf_power
    else:
        remaining = (terminal_age - minimum_survival_age) / (terminal_age - median_age)
        lower_cdf = 1.0 - 0.5 * remaining**late_survival_power
    sampled_cdf = lower_cdf + uniform * (1.0 - lower_cdf)
    if sampled_cdf <= 0.5:
        sampled_age = elder_start_age + (median_age - elder_start_age) * (
            2.0 * sampled_cdf
        ) ** (1.0 / early_cdf_power)
    else:
        sampled_age = terminal_age - (terminal_age - median_age) * (
            2.0 * (1.0 - sampled_cdf)
        ) ** (1.0 / late_survival_power)
    return min(
        terminal_age,
        max(elder_start_age + 1, minimum_survival_age + 1, math.ceil(sampled_age)),
    )
