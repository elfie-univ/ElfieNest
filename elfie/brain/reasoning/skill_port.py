"""Brain-owned contract for immutable Agent Skills.

An Agent Skill is a procedural document loaded from a trusted catalog.  It is
not a Tool definition and it never executes an external capability itself.
"""

from __future__ import annotations

from typing import Annotated, Mapping, Optional, Protocol, Tuple

from pydantic import AfterValidator, Field, JsonValue, StringConstraints

from elfie.message_types import FrozenContractModel


def _validate_skill_name(value: str) -> str:
    if (
        not value
        or value.startswith("-")
        or value.endswith("-")
        or "--" in value
        or any(
            character != "-"
            and not ("0" <= character <= "9" or "a" <= character <= "z")
            for character in value
        )
    ):
        raise ValueError(
            "Skill name must use lowercase letters, numbers and single hyphens"
        )
    return value


def is_valid_skill_name(value: str) -> bool:
    """Return whether a directory name satisfies the Skill name contract."""
    if not isinstance(value, str) or len(value) < 1 or len(value) > 64:
        return False
    try:
        _validate_skill_name(value)
    except ValueError:
        return False
    return True


SkillName = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=64),
    AfterValidator(_validate_skill_name),
]
SkillDescription = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=1024, pattern=r".*\S.*"),
]
SkillInstructions = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=65536, pattern=r".*\S.*"),
]
SkillOptionalText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=1024, pattern=r".*\S.*"),
]
SkillCompatibility = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=500, pattern=r".*\S.*"),
]
SkillAllowedTools = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=2048, pattern=r".*\S.*"),
]

SKILL_LOADER_NAME = "load_skill"


class SkillMetadata(FrozenContractModel):
    """Progressively disclosed metadata advertised before loading a Skill."""

    name: SkillName
    description: SkillDescription


class SkillFrontmatter(FrozenContractModel):
    """Validated standard frontmatter kept out of the model-facing metadata."""

    name: SkillName
    description: SkillDescription
    license: Optional[SkillOptionalText] = None
    compatibility: Optional[SkillCompatibility] = None
    metadata: Mapping[str, str] = Field(default_factory=dict)
    allowed_tools: Optional[SkillAllowedTools] = Field(
        default=None,
        validation_alias="allowed-tools",
    )


class SkillDocument(SkillMetadata):
    """A validated Skill document after its instructions are loaded."""

    instructions: SkillInstructions


class SkillLoadCall(FrozenContractModel):
    """A model-requested load operation, kept distinct from executable Tools."""

    call_id: Annotated[
        str,
        StringConstraints(
            strict=True, min_length=1, max_length=8192, pattern=r".*\S.*"
        ),
    ]
    skill_name: SkillName
    arguments: Mapping[str, JsonValue] = Field(default_factory=dict)


class SkillCatalog(Protocol):
    """Read-only catalog of trusted bundled Skills."""

    def available_skills(self) -> Tuple[SkillMetadata, ...]:
        """Return metadata without loading procedural instructions."""
        ...

    def load(self, name: SkillName) -> Optional[SkillDocument]:
        """Load one approved document, or return ``None`` when unknown."""
        ...


class EmptySkillCatalog:
    """Explicit empty catalog used by isolated/headless compositions."""

    def available_skills(self) -> Tuple[SkillMetadata, ...]:
        return ()

    def load(self, name: SkillName) -> Optional[SkillDocument]:
        del name
        return None


__all__ = (
    "EmptySkillCatalog",
    "SkillCatalog",
    "SkillDescription",
    "SkillDocument",
    "SkillFrontmatter",
    "SkillInstructions",
    "SkillLoadCall",
    "SkillMetadata",
    "SkillName",
    "SKILL_LOADER_NAME",
    "is_valid_skill_name",
)
