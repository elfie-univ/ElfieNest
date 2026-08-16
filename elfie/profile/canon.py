"""Elfaria world facts and the configured narrative species cards."""

from __future__ import annotations

from dataclasses import dataclass

WORLD_CANON_VERSION = "elfaria-world.v0.1"
SPECIES_CANON_VERSION = "elfaria-species.v0.2"


@dataclass(frozen=True)
class WorldCanon:
    """Facts every participant in the initial Earth arrival should share."""

    world_id: str
    display_name: str
    known_region_id: str
    known_region_name: str
    civilization_relation_to_earth: str
    earth_arrival_statement: str
    earth_home_name: str
    earth_home_role: str
    knowledge_boundaries: tuple[str, ...]
    canon_version: str = WORLD_CANON_VERSION


@dataclass(frozen=True)
class SpeciesCanon:
    """Narrative identity and bounded common knowledge for one species.

    Names are intentionally absent. A candidate's name is generated during
    the invitation/reveal step by the configured narrative model, not stored
    as a species property.
    """

    canon_id: str
    display_name: str
    display_name_zh: str
    earth_shape_label: str
    technical_species_id: str
    sort_order: int
    common_sensory_biases: tuple[str, ...]
    common_knowledge: tuple[str, ...]
    earth_first_contact_cues: tuple[str, ...]
    canon_version: str = SPECIES_CANON_VERSION


ELFARIA_CANON = WorldCanon(
    world_id="elfaria",
    display_name="Elfaria",
    known_region_id="mistyville",
    known_region_name="迷雾镇（Mistyville）",
    civilization_relation_to_earth="跨世界交通、工业规模、计算和现代信息技术整体低于地球；这不代表文化、关系或判断力较低。",
    earth_arrival_statement="赴地计划由 Elfie 自愿参加；地球侧工程人员建造并稳定了传送阵和赴地设施。",
    earth_home_name="ElfieNest",
    earth_home_role="Elfie 在地球生活的基地和家，包含传送阵、自己的房间、活动空间和与地球家庭相处的连接点。",
    knowledge_boundaries=(
        "Elfaria 的未知区域、完整地图、政治和历史不能由模型自动补齐。",
        "没有亲历、可靠听闻或赴地资料确认的内容，应明确说不知道或只知道一部分。",
        "地球设备和现代生活需要通过真实接触逐步学习，外部模型不是 Elfaria 原生知识。",
    ),
)


def list_species_canons() -> tuple[SpeciesCanon, ...]:
    """Return configured cards in their stable catalog order."""

    from .species_registry import list_species_definitions  # noqa: PLC0415

    return tuple(
        definition.canon
        for definition in list_species_definitions(include_disabled=True)
    )


def get_species_canon(canon_id: str) -> SpeciesCanon:
    """Return one configured formal Elfaria species card."""

    for canon in list_species_canons():
        if canon.canon_id == canon_id:
            return canon
    raise ValueError(f"不支持的 Elfaria 物种 canon_id={canon_id!r}")


def get_species_canon_for_technical_id(species_id: str) -> SpeciesCanon:
    """Map an existing stable technical species ID to its narrative card."""

    for canon in list_species_canons():
        if canon.technical_species_id == species_id:
            return canon
    raise ValueError(f"没有为技术物种 species_id={species_id!r} 配置 Elfaria canon")


__all__ = (
    "ELFARIA_CANON",
    "SPECIES_CANON_VERSION",
    "WORLD_CANON_VERSION",
    "SpeciesCanon",
    "WorldCanon",
    "get_species_canon",
    "get_species_canon_for_technical_id",
    "list_species_canons",
)
