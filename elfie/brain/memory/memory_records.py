"""Persistence-neutral records used by the durable Memory contract.

The Brain owns these semantic records.  SQL rows, table names and serialized
payloads stay inside the Infrastructure adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Mapping, Optional, Tuple

from .node_types import JsonValue

_RECALL_LIMIT_MAX = {
    "lexical_limit": 200,
    "seed_limit": 64,
    "hop_limit": 4,
    "neighbors_per_node": 64,
    "node_limit": 400,
    "assertion_limit": 800,
    "episode_limit": 80,
    "evidence_limit": 240,
    "character_limit": 100_000,
}


@dataclass(frozen=True)
class SourceReference:
    """A bounded source reference carried by a closed Episode."""

    source_id: str
    source_kind: str = "event"
    locator: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id must not be blank")
        if not self.source_kind.strip():
            raise ValueError("source_kind must not be blank")


@dataclass(frozen=True)
class MediaReference:
    """A media pointer; raw bytes never enter Memory records."""

    media_id: str
    uri: str
    mime_type: str
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None

    def __post_init__(self) -> None:
        if (
            not self.media_id.strip()
            or not self.uri.strip()
            or not self.mime_type.strip()
        ):
            raise ValueError("media_id, uri and mime_type must not be blank")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")


@dataclass(frozen=True)
class ClosedEpisode:
    """One complete, already-closed experience accepted by Memory."""

    episode_id: str
    idempotency_key: str
    occurred_from: str
    content_text: str
    occurred_to: Optional[str] = None
    summary_text: Optional[str] = None
    event_kind: str = "interaction"
    source_refs: Tuple[SourceReference, ...] = ()
    media_refs: Tuple[MediaReference, ...] = ()
    source_event_ids: Tuple[str, ...] = ()
    importance: float = 0.5
    detail_level: str = "full"
    emotion: Optional[str] = None
    emotion_intensity: Optional[float] = None
    stimulus: Optional[str] = None
    sensory: Tuple[Tuple[str, str], ...] = ()
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.episode_id.strip():
            raise ValueError("episode_id must not be blank")
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key must not be blank")
        _timestamp_key(self.occurred_from)
        if not self.content_text.strip():
            raise ValueError("content_text must not be blank")
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError("importance must be between 0 and 1")
        if self.occurred_to is not None and _timestamp_key(
            self.occurred_to
        ) < _timestamp_key(self.occurred_from):
            raise ValueError("occurred_to must not precede occurred_from")
        if self.detail_level not in {"full", "compressed", "digest", "incomplete"}:
            raise ValueError("unsupported Episode detail_level")
        if (
            self.emotion_intensity is not None
            and not 0.0 <= self.emotion_intensity <= 1.0
        ):
            # Legacy callers pass percentages; the compatibility encoder does
            # not construct ClosedEpisode with that value.  Typed callers must
            # use the normalized [0, 1] contract.
            raise ValueError("emotion_intensity must be between 0 and 1")
        if any(not value.strip() for value in self.source_event_ids):
            raise ValueError("source_event_ids must not contain blank IDs")


@dataclass(frozen=True)
class EpisodeReceipt:
    """Result of an idempotent Episode write."""

    episode_id: str
    idempotency_key: str
    status: Literal["committed", "duplicate"]
    content_sha256: str


@dataclass(frozen=True)
class NodeInput:
    """Canonical graph node proposed by consolidation or a seed."""

    node_id: str
    node_type: str
    canonical_label: str
    description: Optional[str] = None
    scope: str = "elfie"
    status: str = "active"
    confidence: float = 0.5
    properties: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.node_id.strip() or not self.node_type.strip():
            raise ValueError("node_id and node_type must not be blank")
        if not self.canonical_label.strip():
            raise ValueError("canonical_label must not be blank")
        if not self.scope.strip():
            raise ValueError("scope must not be blank")
        if self.status not in {"active", "candidate", "unresolved", "forgotten"}:
            raise ValueError("unsupported node status")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class AliasInput:
    """One sourced alternate name for a canonical node."""

    node_id: str
    alias: str
    scope: str = "elfie"
    evidence_id: Optional[str] = None
    confidence: float = 0.5

    def __post_init__(self) -> None:
        if not self.node_id.strip() or not self.alias.strip() or not self.scope.strip():
            raise ValueError("node_id, alias and scope must not be blank")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class DescriptionInput:
    """One distinct sourced description of a node."""

    node_id: str
    text: str
    language: str = "und"
    kind: str = "description"
    evidence_id: Optional[str] = None
    confidence: float = 0.5

    def __post_init__(self) -> None:
        if not self.node_id.strip() or not self.text.strip():
            raise ValueError("node_id and description text must not be blank")
        if not self.language.strip() or not self.kind.strip():
            raise ValueError("description language and kind must not be blank")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class MentionInput:
    """A semantic mention in an Episode, including unresolved mentions."""

    episode_id: str
    surface_text: str
    node_id: Optional[str] = None
    resolution_state: Literal["resolved", "ambiguous", "unresolved"] = "unresolved"
    role: Optional[str] = None
    span_start: Optional[int] = None
    span_end: Optional[int] = None
    confidence: float = 0.5

    def __post_init__(self) -> None:
        if not self.episode_id.strip() or not self.surface_text.strip():
            raise ValueError("episode_id and surface_text must not be blank")
        if self.node_id is not None and not self.node_id.strip():
            raise ValueError("node_id must not be blank when supplied")
        if self.resolution_state == "resolved" and self.node_id is None:
            raise ValueError("resolved mentions require a node_id")
        if self.span_start is not None and self.span_start < 0:
            raise ValueError("span_start must not be negative")
        if self.span_end is not None and self.span_end < 0:
            raise ValueError("span_end must not be negative")
        if (
            self.span_start is not None
            and self.span_end is not None
            and self.span_end < self.span_start
        ):
            raise ValueError("span_end must not precede span_start")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class AssertionInput:
    """A qualified directed claim, never an unqualified bare edge."""

    subject_id: str
    predicate: str
    object_node_id: Optional[str] = None
    object_literal: Optional[JsonValue] = None
    object_unit: Optional[str] = None
    polarity: Literal["positive", "negative"] = "positive"
    epistemic_status: Literal["known", "believed", "uncertain", "reported"] = "known"
    viewpoint: Optional[str] = None
    context: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    confidence: float = 0.5
    support_score: float = 0.5
    conflict_group: Optional[str] = None
    evidence_ids: Tuple[str, ...] = ()
    assertion_id: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.object_node_id is None) == (self.object_literal is None):
            raise ValueError("an assertion must have exactly one object form")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not 0.0 <= self.support_score <= 1.0:
            raise ValueError("support_score must be between 0 and 1")
        if not self.subject_id.strip() or not self.predicate.strip():
            raise ValueError("subject_id and predicate must not be blank")
        if self.object_node_id is not None and not self.object_node_id.strip():
            raise ValueError("object_node_id must not be blank")
        if self.object_unit is not None and not self.object_unit.strip():
            raise ValueError("object_unit must not be blank")
        if self.valid_from is not None:
            _timestamp_key(self.valid_from)
        if self.valid_to is not None:
            _timestamp_key(self.valid_to)
        if self.valid_from is not None and self.valid_to is not None:
            if _timestamp_key(self.valid_to) < _timestamp_key(self.valid_from):
                raise ValueError("valid_to must not precede valid_from")


@dataclass(frozen=True)
class EvidenceInput:
    """A source locator that grounds a graph assertion."""

    evidence_id: str
    source_type: Literal["episode", "seed", "legacy"]
    source_id: str
    excerpt: Optional[str] = None
    media_locator: Optional[str] = None
    modality: str = "text"
    span_start: Optional[int] = None
    span_end: Optional[int] = None
    speaker: Optional[str] = None
    viewpoint: Optional[str] = None
    captured_at: Optional[str] = None
    extraction_run_id: Optional[str] = None
    source_sha256: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or not self.source_id.strip():
            raise ValueError("evidence_id and source_id must not be blank")
        if not self.modality.strip():
            raise ValueError("evidence modality must not be blank")
        if self.excerpt is not None and not self.excerpt.strip():
            raise ValueError("evidence excerpt must not be blank when supplied")
        if self.span_start is not None and self.span_start < 0:
            raise ValueError("span_start must not be negative")
        if self.span_end is not None and self.span_end < 0:
            raise ValueError("span_end must not be negative")
        if (
            self.span_start is not None
            and self.span_end is not None
            and self.span_end < self.span_start
        ):
            raise ValueError("span_end must not precede span_start")


@dataclass(frozen=True)
class AssertionEvidenceInput:
    """Many-to-many evidence stance for one assertion."""

    assertion_id: str
    evidence_id: str
    stance: Literal["supports", "contradicts", "context"] = "supports"

    def __post_init__(self) -> None:
        if not self.assertion_id.strip() or not self.evidence_id.strip():
            raise ValueError("assertion_id and evidence_id must not be blank")
        if self.stance not in {"supports", "contradicts", "context"}:
            raise ValueError("unsupported evidence stance")


@dataclass(frozen=True)
class ConsolidationProjection:
    """Validated projection of one Episode into the personal graph."""

    episode_id: str
    nodes: Tuple[NodeInput, ...] = ()
    aliases: Tuple[AliasInput, ...] = ()
    descriptions: Tuple[DescriptionInput, ...] = ()
    mentions: Tuple[MentionInput, ...] = ()
    assertions: Tuple[AssertionInput, ...] = ()
    evidence: Tuple[EvidenceInput, ...] = ()
    assertion_evidence: Tuple[AssertionEvidenceInput, ...] = ()
    extraction_run_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.episode_id.strip():
            raise ValueError("episode_id must not be blank")


@dataclass(frozen=True)
class ConsolidationRequest:
    """Bounded request for one background consolidation batch."""

    max_episodes: int = 8
    worker_id: str = "memory-consolidator"

    def __post_init__(self) -> None:
        if self.max_episodes < 1:
            raise ValueError("max_episodes must be at least one")
        if not self.worker_id.strip():
            raise ValueError("worker_id must not be blank")


@dataclass(frozen=True)
class ConsolidationReceipt:
    """Result of a projection commit."""

    episode_id: str
    status: Literal["consolidated", "duplicate", "failed"]
    nodes_created: int = 0
    assertions_created: int = 0
    evidence_created: int = 0
    mentions_truncated: bool = False
    error: Optional[str] = None


@dataclass(frozen=True)
class ConsolidationBatchReceipt:
    """Bounded outcome of one consolidation worker pass."""

    worker_id: str
    requested: int
    consolidated_episode_ids: Tuple[str, ...] = ()
    failed_episode_ids: Tuple[str, ...] = ()
    nodes_created: int = 0
    assertions_created: int = 0
    evidence_created: int = 0
    errors: Mapping[str, str] = field(default_factory=dict)

    @property
    def status(self) -> Literal["completed", "partial", "failed", "empty"]:
        if self.consolidated_episode_ids and self.failed_episode_ids:
            return "partial"
        if self.failed_episode_ids and not self.consolidated_episode_ids:
            return "failed"
        if self.consolidated_episode_ids:
            return "completed"
        return "empty"


@dataclass(frozen=True)
class RecallRequest:
    """Bounded semantic query accepted by the Memory Port."""

    text: str = ""
    seed_node_ids: Tuple[str, ...] = ()
    node_types: Tuple[str, ...] = ()
    relation_types: Tuple[str, ...] = ()
    occurred_from: Optional[str] = None
    occurred_to: Optional[str] = None
    mode: Literal["basic", "local", "basic_local"] = "basic_local"
    lexical_limit: int = 20
    seed_limit: int = 8
    hop_limit: int = 2
    neighbors_per_node: int = 12
    node_limit: int = 40
    assertion_limit: int = 80
    episode_limit: int = 8
    evidence_limit: int = 24
    character_limit: int = 12000

    def __post_init__(self) -> None:
        for name in (
            "lexical_limit",
            "seed_limit",
            "hop_limit",
            "neighbors_per_node",
            "node_limit",
            "assertion_limit",
            "episode_limit",
            "evidence_limit",
            "character_limit",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")
            if getattr(self, name) > _RECALL_LIMIT_MAX[name]:
                raise ValueError(
                    f"{name} exceeds the safe maximum {_RECALL_LIMIT_MAX[name]}"
                )
        if self.mode not in {"basic", "local", "basic_local"}:
            raise ValueError("unsupported recall mode")
        if self.occurred_from is not None and self.occurred_to is not None:
            if _timestamp_key(self.occurred_to) < _timestamp_key(self.occurred_from):
                raise ValueError("occurred_to must not precede occurred_from")


@dataclass(frozen=True)
class RecallNode:
    node_id: str
    node_type: str
    label: str
    description: Optional[str]
    relevance: float


@dataclass(frozen=True)
class RecallAssertion:
    assertion_id: str
    subject_id: str
    predicate: str
    object_node_id: Optional[str]
    object_literal: Optional[JsonValue]
    qualifiers: Mapping[str, JsonValue]
    status: str
    evidence_ids: Tuple[str, ...]
    relevance: float


@dataclass(frozen=True)
class RecallPath:
    node_ids: Tuple[str, ...]
    assertion_ids: Tuple[str, ...]
    hop_count: int


@dataclass(frozen=True)
class RecallEpisode:
    episode_id: str
    occurred_from: str
    occurred_to: Optional[str]
    excerpt: str
    detail_level: str
    relevance: float


@dataclass(frozen=True)
class RecallEvidence:
    evidence_id: str
    source_id: str
    excerpt: Optional[str]
    media_locator: Optional[str]
    stance: str


@dataclass(frozen=True)
class RecallConflict:
    assertion_ids: Tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class RecallLimits:
    requested: Mapping[str, int]
    returned: Mapping[str, int]
    truncated: bool = False


@dataclass(frozen=True)
class RecallBundle:
    """Stable, bounded payload consumed by the upper reasoning layer."""

    focus_nodes: Tuple[RecallNode, ...] = ()
    assertions: Tuple[RecallAssertion, ...] = ()
    paths: Tuple[RecallPath, ...] = ()
    episodes: Tuple[RecallEpisode, ...] = ()
    evidence: Tuple[RecallEvidence, ...] = ()
    conflicts: Tuple[RecallConflict, ...] = ()
    limits: RecallLimits = field(
        default_factory=lambda: RecallLimits(requested={}, returned={})
    )


__all__ = [
    "AliasInput",
    "AssertionEvidenceInput",
    "AssertionInput",
    "ClosedEpisode",
    "ConsolidationProjection",
    "ConsolidationBatchReceipt",
    "ConsolidationRequest",
    "ConsolidationReceipt",
    "DescriptionInput",
    "EpisodeReceipt",
    "EvidenceInput",
    "MediaReference",
    "MentionInput",
    "NodeInput",
    "RecallAssertion",
    "RecallBundle",
    "RecallConflict",
    "RecallEpisode",
    "RecallEvidence",
    "RecallLimits",
    "RecallNode",
    "RecallPath",
    "RecallRequest",
    "SourceReference",
]


def _timestamp_key(value: str) -> str:
    """Normalize comparable ISO timestamps without rejecting legacy values."""
    text = value.strip()
    if not text:
        raise ValueError("timestamp must not be blank")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        # Legacy fixtures occasionally use date-only values.  Keep lexical
        # ordering for those rather than making migration impossible.
        return text
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.isoformat()
