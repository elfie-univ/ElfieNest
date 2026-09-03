"""Private, JSON-safe input envelope for an unfinished Genesis transaction."""

from __future__ import annotations

from dataclasses import fields
from typing import Any, Mapping

from elfie.profile.models import (
    AppearanceGenome,
    AppearanceMacro,
    AppearanceProportions,
    AppendageAppearance,
    BodyAppearance,
    CoatAppearance,
    FaceAppearance,
    FurAppearance,
    RegionAccent,
)

from .contracts import (
    BigFiveProfile,
    CandidateSignature,
    GenesisCandidate,
    GenesisPersonality,
)
from .serialization import _jsonable

ENVELOPE_FORMAT_VERSION = 1


class GenesisCompileEnvelopeError(ValueError):
    """The private recovery input is malformed or incomplete."""


class GenesisCompileEnvelope:
    """The only durable input retained while one Genesis transaction is open.

    The envelope is deleted after commit or abort.  It contains the accepted
    structured candidate, not the original questionnaire or an instruction
    prompt, and it is never loaded by a running Elfie.
    """

    def __init__(
        self,
        request,
        *,
        source_package_version: str,
        source_content_sha256: str,
        policy_version: str,
        compiler_version: str,
        format_version: int = ENVELOPE_FORMAT_VERSION,
    ) -> None:
        self.request = request
        self.source_package_version = source_package_version
        self.source_content_sha256 = source_content_sha256
        self.policy_version = policy_version
        self.compiler_version = compiler_version
        self.format_version = format_version

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "request": _jsonable(self.request),
            "source_package_version": self.source_package_version,
            "source_content_sha256": self.source_content_sha256,
            "policy_version": self.policy_version,
            "compiler_version": self.compiler_version,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> GenesisCompileEnvelope:
        if not isinstance(raw, Mapping):
            raise GenesisCompileEnvelopeError("GenesisCompileEnvelope 根节点必须是对象")
        expected = {
            "format_version",
            "request",
            "source_package_version",
            "source_content_sha256",
            "policy_version",
            "compiler_version",
        }
        if set(raw) != expected:
            raise GenesisCompileEnvelopeError(
                "GenesisCompileEnvelope 字段不完整或包含未知字段"
            )
        if raw["format_version"] != ENVELOPE_FORMAT_VERSION:
            raise GenesisCompileEnvelopeError("GenesisCompileEnvelope 版本不支持")
        for key in (
            "source_package_version",
            "source_content_sha256",
            "policy_version",
            "compiler_version",
        ):
            if not isinstance(raw[key], str) or not raw[key].strip():
                raise GenesisCompileEnvelopeError(f"{key} 必须是非空字符串")
        request = _request_from_dict(raw["request"])
        return cls(
            request,
            source_package_version=raw["source_package_version"],
            source_content_sha256=raw["source_content_sha256"],
            policy_version=raw["policy_version"],
            compiler_version=raw["compiler_version"],
        )


def _request_from_dict(raw: Any):
    from .compiler import GenesisCompileInput

    if not isinstance(raw, Mapping):
        raise GenesisCompileEnvelopeError("GenesisCompileEnvelope.request 必须是对象")
    field_names = {item.name for item in fields(GenesisCompileInput)}
    if set(raw) != field_names:
        raise GenesisCompileEnvelopeError(
            "GenesisCompileInput 字段不完整或包含未知字段"
        )
    candidate_raw = raw["candidate"]
    candidate = None if candidate_raw is None else _candidate_from_dict(candidate_raw)
    overrides = raw["big_five_overrides"]
    if overrides is not None:
        if not isinstance(overrides, Mapping):
            raise GenesisCompileEnvelopeError("big_five_overrides 必须是对象或 null")
        overrides = {str(key): float(value) for key, value in overrides.items()}
    return GenesisCompileInput(
        elfie_id=_text(raw, "elfie_id"),
        owner_reference=_text(raw, "owner_reference"),
        display_name=_text(raw, "display_name"),
        species_id=_text(raw, "species_id"),
        gender=_text(raw, "gender"),
        life_stage=_text(raw, "life_stage"),
        age_years_at_adoption=_positive_int(raw, "age_years_at_adoption"),
        appearance_seed=_int(raw, "appearance_seed"),
        height=_text(raw, "height"),
        build=_text(raw, "build"),
        face=_text(raw, "face"),
        signature=_text(raw, "signature"),
        candidate=candidate,
        personality_style=_text_or_empty(raw, "personality_style"),
        personality_description=_text_or_empty(raw, "personality_description"),
        big_five_overrides=overrides,
        original_name=_text_or_empty(raw, "original_name"),
        adoption_anchor_at=_text_or_empty(raw, "adoption_anchor_at"),
        reservation_id=_text_or_empty(raw, "reservation_id"),
        idempotency_key=_text_or_empty(raw, "idempotency_key"),
        arrival_base_id=_text(raw, "arrival_base_id"),
        invitation_accepted=_bool(raw, "invitation_accepted"),
        full_body_image_url=_text_or_empty(raw, "full_body_image_url"),
        headshot_image_url=_text_or_empty(raw, "headshot_image_url"),
    )


def _candidate_from_dict(raw: Any) -> GenesisCandidate:
    if not isinstance(raw, Mapping):
        raise GenesisCompileEnvelopeError("candidate 必须是对象")
    return GenesisCandidate(
        candidate_id=_text(raw, "candidate_id"),
        role=_text(raw, "role"),
        seed=_int(raw, "seed"),
        species_id=_text(raw, "species_id"),
        life_stage=_text(raw, "life_stage"),
        age_years=_positive_int(raw, "age_years"),
        gender=_text(raw, "gender"),
        appearance=_appearance_from_dict(raw["appearance"]),
        personality=_personality_from_dict(raw["personality"]),
        signature=_signature_from_dict(raw["signature"]),
    )


def _appearance_from_dict(raw: Any) -> AppearanceGenome:
    if not isinstance(raw, Mapping):
        raise GenesisCompileEnvelopeError("candidate.appearance 必须是对象")
    coat_raw = _mapping(raw["coat"], "coat")
    accents = coat_raw.get("region_accents", [])
    if not isinstance(accents, list):
        raise GenesisCompileEnvelopeError(
            "candidate.appearance.coat.region_accents 必须是数组"
        )
    coat_values = dict(coat_raw)
    coat_values["region_accents"] = tuple(
        _dataclass_from_dict(RegionAccent, item, "region accent") for item in accents
    )
    return AppearanceGenome(
        genome_version=_int(raw, "genome_version"),
        species_profile_version=_int(raw, "species_profile_version"),
        macro=_dataclass_from_dict(AppearanceMacro, raw["macro"], "macro"),
        proportions=_dataclass_from_dict(
            AppearanceProportions, raw["proportions"], "proportions"
        ),
        body_bias=_dataclass_from_dict(BodyAppearance, raw["body_bias"], "body_bias"),
        face=_dataclass_from_dict(FaceAppearance, raw["face"], "face"),
        appendages=_dataclass_from_dict(
            AppendageAppearance, raw["appendages"], "appendages"
        ),
        fur=_dataclass_from_dict(FurAppearance, raw["fur"], "fur"),
        coat=_dataclass_from_dict(CoatAppearance, coat_values, "coat"),
        species_traits={
            str(key): float(value)
            for key, value in _mapping(raw["species_traits"], "species_traits").items()
        },
    )


def _personality_from_dict(raw: Any) -> GenesisPersonality:
    value = _mapping(raw, "personality")
    return GenesisPersonality(
        core=_big_five_from_dict(value["core"]),
        candidate=_big_five_from_dict(value["candidate"]),
    )


def _big_five_from_dict(raw: Any) -> BigFiveProfile:
    value = _mapping(raw, "big five")
    latent = value.get("latent")
    scores = value.get("scores")
    labels = value.get("labels")
    if (
        not isinstance(latent, list)
        or not isinstance(scores, list)
        or not isinstance(labels, list)
    ):
        raise GenesisCompileEnvelopeError("BigFiveProfile 字段必须是数组")
    return BigFiveProfile(
        tuple(float(item) for item in latent),
        tuple(int(item) for item in scores),
        tuple(str(item) for item in labels),
    )


def _signature_from_dict(raw: Any) -> CandidateSignature:
    value = _mapping(raw, "signature")
    return CandidateSignature(
        personality=_float_tuple(value, "personality"),
        appearance=_float_tuple(value, "appearance"),
        visual_key=_string_tuple(value, "visual_key"),
    )


def _dataclass_from_dict(dataclass_type, raw: Any, label: str):
    value = _mapping(raw, label)
    allowed = {item.name for item in fields(dataclass_type)}
    if set(value) != allowed:
        raise GenesisCompileEnvelopeError(f"{label} 字段不完整或包含未知字段")
    return dataclass_type(**dict(value))


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenesisCompileEnvelopeError(f"{label} 必须是对象")
    return value


def _text(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise GenesisCompileEnvelopeError(f"{key} 必须是非空字符串")
    return item


def _text_or_empty(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise GenesisCompileEnvelopeError(f"{key} 必须是字符串")
    return item


def _int(value: Mapping[str, Any], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int):
        raise GenesisCompileEnvelopeError(f"{key} 必须是整数")
    return item


def _positive_int(value: Mapping[str, Any], key: str) -> int:
    item = _int(value, key)
    if item < 1:
        raise GenesisCompileEnvelopeError(f"{key} 必须是正整数")
    return item


def _bool(value: Mapping[str, Any], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise GenesisCompileEnvelopeError(f"{key} 必须是布尔值")
    return item


def _float_tuple(value: Mapping[str, Any], key: str) -> tuple[float, ...]:
    item = value.get(key)
    if not isinstance(item, list):
        raise GenesisCompileEnvelopeError(f"{key} 必须是数组")
    return tuple(float(entry) for entry in item)


def _string_tuple(value: Mapping[str, Any], key: str) -> tuple[str, ...]:
    item = value.get(key)
    if not isinstance(item, list) or any(not isinstance(entry, str) for entry in item):
        raise GenesisCompileEnvelopeError(f"{key} 必须是字符串数组")
    return tuple(item)


__all__ = (
    "ENVELOPE_FORMAT_VERSION",
    "GenesisCompileEnvelope",
    "GenesisCompileEnvelopeError",
)
