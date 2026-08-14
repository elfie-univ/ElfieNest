"""Immutable Elfaria world and species facts used by Elfie identity anchors.

The visual profile uses the technical ``fox``/``dog``/``cat`` identifiers that
the current body assets understand.  This module is the narrative canon layer:
it gives those technical profiles their Elfaria names without making the model
pretend that Earth animal names are formal species names.
"""

from __future__ import annotations

from dataclasses import dataclass

WORLD_CANON_VERSION = "elfaria-world.v0.1"
SPECIES_CANON_VERSION = "elfaria-species.v0.1"


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
    """Narrative identity and bounded common knowledge for one species."""

    canon_id: str
    display_name: str
    earth_shape_label: str
    technical_species_id: str
    visual_runtime_supported: bool
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


_SPECIES_CANON: dict[str, SpeciesCanon] = {
    "saevi": SpeciesCanon(
        canon_id="saevi",
        display_name="Saevi",
        earth_shape_label="fox-like",
        technical_species_id="fox",
        visual_runtime_supported=True,
        common_sensory_biases=("环境变化", "路径与空间边界", "气味和方向"),
        common_knowledge=("自然环境、道路、藏身处和小规模聚落生活", "家、路径、边界和返回"),
        earth_first_contact_cues=("先观察边缘、声音和可离开的路径", "再询问陌生设备的具体用途"),
    ),
    "tovren": SpeciesCanon(
        canon_id="tovren",
        display_name="Tovren",
        earth_shape_label="dog-like",
        technical_species_id="dog",
        visual_runtime_supported=True,
        common_sensory_biases=("声音方向", "脚步与呼唤", "群体节奏和协作信号"),
        common_knowledge=("公共活动、共同劳动、巡路和互相照应", "队伍行动和熟悉的声音线索"),
        earth_first_contact_cues=("先判断声音来源、距离和是否有同伴回应", "再理解通信设备的用途"),
    ),
    "myelle": SpeciesCanon(
        canon_id="myelle",
        display_name="Myelle",
        earth_shape_label="cat-like",
        technical_species_id="cat",
        visual_runtime_supported=True,
        common_sensory_biases=("细微声音", "距离和高低差", "平衡与安静移动"),
        common_knowledge=("安静角落、垂直空间、观察位置和低干扰生活", "距离和允许靠近的空间信号"),
        earth_first_contact_cues=("先观察边缘、反光、声音和运动轨迹", "接触并记忆后再把设备当作熟悉事物"),
    ),
}

_SPECIES_BY_TECHNICAL_ID = {
    profile.technical_species_id: profile for profile in _SPECIES_CANON.values()
}


def get_species_canon(canon_id: str) -> SpeciesCanon:
    """Return one formal Elfaria species card by its narrative ID."""
    try:
        return _SPECIES_CANON[canon_id]
    except KeyError as exc:
        raise ValueError(
            f"不支持的 Elfaria 物种 canon_id={canon_id!r}，可选: "
            + ", ".join(sorted(_SPECIES_CANON))
        ) from exc


def get_species_canon_for_technical_id(species_id: str) -> SpeciesCanon:
    """Map an existing visual/body species ID to its narrative species card."""
    try:
        return _SPECIES_BY_TECHNICAL_ID[species_id]
    except KeyError as exc:
        raise ValueError(
            f"没有为技术物种 species_id={species_id!r} 配置 Elfaria canon"
        ) from exc


__all__ = (
    "ELFARIA_CANON",
    "SPECIES_CANON_VERSION",
    "WORLD_CANON_VERSION",
    "SpeciesCanon",
    "WorldCanon",
    "get_species_canon",
    "get_species_canon_for_technical_id",
)
