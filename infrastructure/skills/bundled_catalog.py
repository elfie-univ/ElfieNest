"""Load standard ``SKILL.md`` documents from the immutable config bundle."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Tuple

import yaml
from pydantic import ValidationError

from elfie.brain.reasoning.skill_port import (
    SkillCatalog,
    SkillDocument,
    SkillFrontmatter,
    SkillMetadata,
    SkillName,
    is_valid_skill_name,
)
from infrastructure.persistence.configuration.documents import (
    resolve_bundled_config_root,
)

_MAX_SKILL_BYTES = 64 * 1024


class SkillCatalogError(RuntimeError):
    """A bundled Skill violates the standard document contract."""


class BundledSkillCatalog(SkillCatalog):
    """Read-only catalog for first-party ``config/brain/skills`` documents.

    The catalog deliberately scans only direct child directories and only
    reads their ``SKILL.md`` file.  It never executes scripts or accepts a
    user-controlled install path.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = resolve_bundled_config_root(root) / "brain" / "skills"

    def available_skills(self) -> Tuple[SkillMetadata, ...]:
        if not self._root.is_dir():
            return ()
        metadata: list[SkillMetadata] = []
        for directory in sorted(self._root.iterdir(), key=lambda item: item.name):
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            metadata.append(self._read(directory, include_instructions=False))
        return tuple(metadata)

    def load(self, name: SkillName) -> SkillDocument | None:
        if not isinstance(name, str) or not is_valid_skill_name(name):
            return None
        directory = self._root / name
        if not directory.is_dir() or directory.is_symlink():
            return None
        document = self._read(directory, include_instructions=True)
        if not isinstance(document, SkillDocument):
            raise SkillCatalogError(f"Skill instructions were not loaded: {directory}")
        return document

    def _read(
        self,
        directory: Path,
        *,
        include_instructions: bool,
    ) -> SkillMetadata | SkillDocument:
        if directory.is_symlink():
            raise SkillCatalogError(
                f"Skill directory must not be a symlink: {directory}"
            )
        path = directory / "SKILL.md"
        if not path.is_file() or path.is_symlink():
            raise SkillCatalogError(f"Skill is missing SKILL.md: {path}")
        try:
            if path.stat().st_size > _MAX_SKILL_BYTES:
                raise SkillCatalogError(
                    f"SKILL.md exceeds {_MAX_SKILL_BYTES} bytes: {path}"
                )
            content = path.read_text(encoding="utf-8")
        except OSError as error:
            raise SkillCatalogError(f"Unable to read bundled Skill: {path}") from error
        frontmatter, instructions = _split_document(content, path)
        try:
            parsed = SkillFrontmatter.model_validate(frontmatter)
        except ValidationError as error:
            raise SkillCatalogError(f"Invalid Skill frontmatter: {path}") from error
        metadata = SkillMetadata(name=parsed.name, description=parsed.description)
        if metadata.name != directory.name:
            raise SkillCatalogError(f"Skill name must match its directory: {path}")
        if not include_instructions:
            return metadata
        try:
            return SkillDocument(
                name=metadata.name,
                description=metadata.description,
                instructions=instructions,
            )
        except ValidationError as error:
            raise SkillCatalogError(f"Invalid Skill instructions: {path}") from error


def _split_document(content: str, path: Path) -> tuple[Mapping[str, object], str]:
    lines = content.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        raise SkillCatalogError(f"SKILL.md must start with YAML frontmatter: {path}")
    try:
        end = next(
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        )
    except StopIteration as error:
        raise SkillCatalogError(
            f"SKILL.md frontmatter is not closed: {path}"
        ) from error
    try:
        frontmatter = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as error:
        raise SkillCatalogError(
            f"Skill frontmatter is not valid YAML: {path}"
        ) from error
    if not isinstance(frontmatter, Mapping):
        raise SkillCatalogError(f"Skill frontmatter must be an object: {path}")
    instructions = "\n".join(lines[end + 1 :]).strip()
    return frontmatter, instructions


__all__ = ("BundledSkillCatalog", "SkillCatalogError")
