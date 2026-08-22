"""Strict HTTP DTOs for member-visible Elfie resources."""

from __future__ import annotations

from typing import Dict, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, StrictStr


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class BigFiveResponse(_StrictModel):
    openness: Optional[float]
    conscientiousness: Optional[float]
    extraversion: Optional[float]
    agreeableness: Optional[float]
    neuroticism: Optional[float]


class ElfieAppearanceResponse(_StrictModel):
    species_id: StrictStr
    profile_version: StrictInt
    height_scale: StrictFloat
    build_scale: StrictFloat
    height_label: StrictStr
    build_label: StrictStr
    bone_scales: Dict[StrictStr, StrictFloat]
    blend_shapes: Dict[StrictStr, StrictFloat]
    material_parameters: Dict[StrictStr, Union[StrictStr, StrictFloat]]
    species_traits: Dict[StrictStr, StrictFloat]


class ElfieSpeciesPresentationResponse(_StrictModel):
    species_id: str
    canon_id: str
    display_name: str
    display_name_zh: str
    earth_shape_label: str
    status: Literal["published", "retired"]


class ElfieProfileResponse(_StrictModel):
    elfie_id: str
    name: str
    species_id: str
    species: Optional[ElfieSpeciesPresentationResponse]
    gender: Optional[str]
    birth_date: Optional[str]
    summary: Optional[str]
    adopted_at: str
    profile_status: Literal["ready", "empty", "unavailable"]
    big_five: Optional[BigFiveResponse]
    personality_tags: tuple[str, ...]
    portrait_url: str
    appearance: Optional[ElfieAppearanceResponse]


class ElfiePermissionsResponse(_StrictModel):
    can_view_profile: bool
    can_view_cognition: bool


class VisibleElfieResponse(_StrictModel):
    relationship: Literal["owned", "other"]
    permissions: ElfiePermissionsResponse
    profile: ElfieProfileResponse


class VisibleElfiesResponse(_StrictModel):
    items: tuple[VisibleElfieResponse, ...]


class TopicResponse(_StrictModel):
    id: str
    label: str
    category: str
    weight: float


class RecentFocusResponse(_StrictModel):
    topics: tuple[TopicResponse, ...]


class ExperienceResponse(_StrictModel):
    id: str
    occurred_at: str
    title: str
    changed: str
    importance: float
    people: tuple[str, ...]


class ImportantExperiencesResponse(_StrictModel):
    entries: tuple[ExperienceResponse, ...]


class GraphNodeResponse(_StrictModel):
    id: str
    label: str
    kind: str
    weight: float


class GraphEdgeResponse(_StrictModel):
    source: str
    target: str
    relation_key: str
    display_label: str
    weight: float


class RelationshipWorldResponse(_StrictModel):
    nodes: tuple[GraphNodeResponse, ...]
    edges: tuple[GraphEdgeResponse, ...]


class WorldRingResponse(_StrictModel):
    key: Literal["self", "family", "nest", "society", "outside"]
    nodes: tuple[GraphNodeResponse, ...]


class WorldUnderstandingResponse(_StrictModel):
    summary: str
    rings: tuple[WorldRingResponse, ...]


class KnowledgeBeliefsResponse(_StrictModel):
    nodes: tuple[GraphNodeResponse, ...]
    edges: tuple[GraphEdgeResponse, ...]


class PrivateCognitionResponse(_StrictModel):
    status: Literal["ready", "empty", "unavailable"]
    recent_focus: RecentFocusResponse
    important_experiences: ImportantExperiencesResponse
    relationship_world: RelationshipWorldResponse
    world_understanding: WorldUnderstandingResponse
    knowledge_beliefs: KnowledgeBeliefsResponse


class ElfieProfileDetailResponse(_StrictModel):
    relationship: Literal["owned", "other"]
    permissions: ElfiePermissionsResponse
    profile: ElfieProfileResponse
    private_cognition: Optional[PrivateCognitionResponse]


class ElfiePortraitUploadResponse(_StrictModel):
    portrait_url: StrictStr


class ElfiesErrorDetails(_StrictModel):
    pass


class ElfiesErrorItem(_StrictModel):
    code: str
    message: str
    details: ElfiesErrorDetails


class ElfiesErrorResponse(_StrictModel):
    error: ElfiesErrorItem


__all__ = (
    "ElfiePermissionsResponse",
    "ElfieAppearanceResponse",
    "ElfieProfileDetailResponse",
    "ElfieProfileResponse",
    "ElfiePortraitUploadResponse",
    "ElfieSpeciesPresentationResponse",
    "ElfiesErrorDetails",
    "ElfiesErrorItem",
    "ElfiesErrorResponse",
    "VisibleElfieResponse",
    "VisibleElfiesResponse",
)
