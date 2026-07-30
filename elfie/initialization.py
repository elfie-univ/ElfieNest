"""Stable profile and anatomy assembly for one Elfie facade."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import yaml

from elfie.body import BipedAnatomy, QuadrupedAnatomy
from elfie.body.native.anatomy.base import SomaticAnatomy
from elfie.profile import ElfieProfile, ElfieProfileRepository, create_visual_profile


def assemble_profile(
    *,
    config_dir: str | None,
    elfie_id: str | None,
    supplied: ElfieProfile | None,
) -> ElfieProfile:
    """Resolve one stable Profile and merge only explicit configuration sources."""
    if supplied is not None:
        supplied.validate()
        return supplied
    repository = ElfieProfileRepository(_profile_source(config_dir))
    if repository.exists():
        return repository.load()
    if config_dir is not None:
        raise FileNotFoundError(f"精灵最终档案不存在: {repository.path}")
    sections = _load_packaged_defaults(repository.config_dir)
    personality = sections["personality"]
    metadata = personality.get("metadata", {})
    appearance = metadata.get("appearance", {}) if isinstance(metadata, dict) else {}
    if not isinstance(appearance, dict):
        appearance = {}
    species_id = str(appearance.get("species", "fox"))
    if species_id not in ("dog", "fox"):
        species_id = "fox"
    stable_id = elfie_id or "elfie_default"
    seed = int.from_bytes(
        hashlib.sha256(stable_id.encode("utf-8")).digest()[:8],
        "big",
    )
    profile = create_visual_profile(
        elfie_id=stable_id,
        display_name=str(metadata.get("name") or stable_id),
        species_id=species_id,
        seed=seed,
        height_direction=str(appearance.get("height", "standard")),
        build_direction=str(appearance.get("build", "standard")),
    )
    return replace(
        profile,
        personality=personality,
        capabilities=sections["capabilities"],
        system_limits=sections["system_limits"],
    )


def assemble_anatomy(
    profile: ElfieProfile,
    legacy_anatomy_type: str | None,
) -> tuple[str, SomaticAnatomy]:
    """Resolve the configured morphology without executing any action policy."""
    morphology = legacy_anatomy_type or profile.embodiment.primary_morphology
    if morphology == "quadruped":
        return morphology, QuadrupedAnatomy()
    return morphology, BipedAnatomy()


def _profile_source(config_dir: str | None) -> Path:
    if config_dir is not None:
        return Path(config_dir) / "profile"
    return Path(__file__).resolve().parent / "profile" / "defaults"


def _load_packaged_defaults(defaults_dir: Path) -> dict[str, dict]:
    sections: dict[str, dict] = {}
    for field_name in ("personality", "capabilities", "system_limits"):
        path = defaults_dir / f"{field_name}.yaml"
        with path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"默认精灵配置必须是映射: {path}")
        sections[field_name] = dict(raw)
    return sections


__all__ = ("assemble_anatomy", "assemble_profile")
