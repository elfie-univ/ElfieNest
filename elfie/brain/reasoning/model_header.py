"""Deterministic four-block online Elfie model header."""

from __future__ import annotations

from typing import Annotated, Mapping

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from elfie.brain.selfhood.contracts import SelfhoodPromptProjection
from elfie.message_types import FrozenContractModel

_HeaderText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=16_384, pattern=r".*\S.*"),
]
_RESERVED_LABELS = (
    "[APPLICATION_FRAME]",
    "[IDENTITY_CORE]",
    "[ADAPTIVE_SELF]",
    "[OPERATING_CONTRACT]",
    "[TURN_PROTOCOL]",
    "[CURRENT_BRAIN_STATE]",
)


class ReasoningConstitution(FrozenContractModel):
    """Release-owned shared application frame and operating contract."""

    version: int = Field(strict=True, ge=1)
    application_frame_text: _HeaderText
    operating_contract_text: _HeaderText
    max_prefix_bytes: int = Field(strict=True, ge=256)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ReasoningConstitution:
        if not isinstance(raw, Mapping):
            raise ValueError("ReasoningConstitution must be a mapping")
        try:
            return cls.model_validate(dict(raw))
        except Exception as error:  # noqa: BLE001 - config boundary
            raise ValueError("invalid ReasoningConstitution") from error

    @model_validator(mode="after")
    def validate_content(self) -> ReasoningConstitution:
        for value in (self.application_frame_text, self.operating_contract_text):
            if any(label in value for label in _RESERVED_LABELS):
                raise PydanticCustomError(
                    "reasoning_constitution_reserved_label",
                    "ReasoningConstitution text cannot contain header labels",
                )
            if any(ord(char) < 32 and char not in "\n\t" for char in value):
                raise PydanticCustomError(
                    "reasoning_constitution_control_character",
                    "ReasoningConstitution text cannot contain control characters",
                )
        return self


class ModelHeaderAssembler:
    """Assemble and validate the exact fixed prefix plus dynamic sections."""

    def __init__(self, constitution: ReasoningConstitution) -> None:
        self._constitution = constitution

    @property
    def version(self) -> int:
        """Return the release constitution revision captured by a Turn."""

        return self._constitution.version

    def fixed_prefix(self, projection: SelfhoodPromptProjection) -> str:
        if projection.revision == 0:
            raise ValueError("Selfhood projection is unavailable")
        sections = (
            ("[APPLICATION_FRAME]", self._constitution.application_frame_text),
            ("[IDENTITY_CORE]", projection.identity_core_text),
            ("[ADAPTIVE_SELF]", projection.adaptive_self_text),
            ("[OPERATING_CONTRACT]", self._constitution.operating_contract_text),
        )
        prefix = "\n\n".join(f"{label}\n{text.strip()}" for label, text in sections)
        self._validate_prefix(prefix)
        return prefix

    def system_prompt(
        self,
        projection: SelfhoodPromptProjection,
        *,
        turn_protocol: str,
        current_brain_state: str,
    ) -> str:
        prefix = self.fixed_prefix(projection)
        protocol = _clean_dynamic("[TURN_PROTOCOL]", turn_protocol)
        brain_state = _clean_dynamic("[CURRENT_BRAIN_STATE]", current_brain_state)
        prompt = f"{prefix}\n\n{protocol}\n\n{brain_state}"
        if not prompt.startswith("[APPLICATION_FRAME]\n"):
            raise ValueError("fixed model header must be the first system content")
        for label in _RESERVED_LABELS:
            if prompt.count(label) != 1:
                raise ValueError("fixed header labels must occur exactly once")
        return prompt

    def _validate_prefix(self, prefix: str) -> None:
        if not prefix.startswith("[APPLICATION_FRAME]\n"):
            raise ValueError("fixed model header must start with APPLICATION_FRAME")
        if prefix.count("[APPLICATION_FRAME]") != 1:
            raise ValueError("APPLICATION_FRAME must occur exactly once")
        if prefix.count("[IDENTITY_CORE]") != 1:
            raise ValueError("IDENTITY_CORE must occur exactly once")
        if prefix.count("[ADAPTIVE_SELF]") != 1:
            raise ValueError("ADAPTIVE_SELF must occur exactly once")
        if prefix.count("[OPERATING_CONTRACT]") != 1:
            raise ValueError("OPERATING_CONTRACT must occur exactly once")
        if "[TURN_PROTOCOL]" in prefix:
            raise ValueError("fixed prefix cannot contain TURN_PROTOCOL")
        if len(prefix.encode("utf-8")) > self._constitution.max_prefix_bytes:
            raise ValueError("fixed model header exceeds configured byte limit")


def _clean_dynamic(label: str, text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{label} content is required")
    if any(reserved in text for reserved in _RESERVED_LABELS):
        raise ValueError(f"{label} content cannot contain fixed header labels")
    return f"{label}\n{text.strip()}"


__all__ = ("ModelHeaderAssembler", "ReasoningConstitution")
