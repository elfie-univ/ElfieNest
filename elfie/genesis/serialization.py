"""Canonical serialization shared by the Genesis compiler and committer.

There is deliberately one calculation for the semantic digest and durable
output inventory.  The compiler declares what it is handing off and the
Memory committer verifies that declaration before opening its source-first
unit of work.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, cast

from .contracts import GenesisBundle, KnowledgeSeed

SELF_NODE_PREFIX = "genesis:self:"
KNOWLEDGE_NODE_PREFIX = "genesis:knowledge:"
PLACE_NODE_PREFIX = "genesis:place:"
PERSON_NODE_PREFIX = "genesis:person:"
EPISODE_NODE_PREFIX = "genesis:episode:"
EVENT_NODE_PREFIX = "genesis:event:"
ENTITY_NODE_PREFIX = "genesis:entity:"


def knowledge_groups(bundle: GenesisBundle) -> tuple[tuple[KnowledgeSeed, ...], ...]:
    """Group admitted facts without mixing acquisition boundaries or truncating members."""
    buckets: dict[tuple[str, int | None, str, bool], list[KnowledgeSeed]] = {}
    for seed in bundle.knowledge_seeds:
        key = (
            seed.topic,
            seed.acquired_age_years,
            seed.acquired_stage,
            seed.recall_eligible,
        )
        buckets.setdefault(key, []).append(seed)
    groups: list[tuple[KnowledgeSeed, ...]] = []
    for members in buckets.values():
        current: list[KnowledgeSeed] = []
        size = 0
        for seed in members:
            # Keep the authored member whole when deciding the group boundary.
            length = len(knowledge_member_text(seed)) + 2
            if current and size + length > bundle.knowledge_episode_max_chars:
                groups.append(tuple(current))
                current, size = [], 0
            current.append(seed)
            size += length
        if current:
            groups.append(tuple(current))
    return tuple(groups)


def knowledge_member_text(seed: KnowledgeSeed) -> str:
    """Return the authored source text for a knowledge member.

    Provenance, certainty, and mastery are durable metadata on the Episode and
    its ``knowledge_members`` entries.  They are not part of the readable
    source body, so the serializer must not frame them into ``content_text``.
    """

    return seed.content


def knowledge_summary_text(content: str, max_chars: int = 120) -> str:
    """Create a bounded synopsis from the authored first sentence.

    Genesis does not invent a new fact for a display title.  It derives the
    synopsis from the source body, while retaining the complete body as the
    Episode content.  The helper is deterministic so retries produce the same
    semantic output without a model call or a second source of truth.
    """

    normalized = " ".join(content.split())
    if not normalized:
        return ""
    match = re.search(r"[。！？.!?]", normalized)
    synopsis = normalized[: match.end()] if match else normalized
    characters = list(synopsis)
    if len(characters) <= max_chars:
        return synopsis
    return "".join(characters[: max_chars - 1]) + "…"


def knowledge_group_id(safe_elfie: str, members: tuple[KnowledgeSeed, ...]) -> str:
    return f"{EPISODE_NODE_PREFIX}{safe_elfie}:knowledge:{safe_component(members[0].topic)}:{safe_component(members[0].seed_id)}"


def safe_component(value: str) -> str:
    """Turn an external identifier into a stable identifier component."""

    return "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in value
    )


def genesis_content_hash(bundle: GenesisBundle) -> str:
    """Hash every semantic hand-off value, excluding commit-time metadata."""

    payload = {
        "profile": _jsonable(bundle.profile_draft.profile.to_dict()),
        "selfhood": _jsonable(bundle.selfhood_state),
        "self_model": _jsonable(bundle.self_model_seed),
        "knowledge": [_jsonable(item) for item in bundle.knowledge_seeds],
        "episodes": [_jsonable(item) for item in bundle.episode_seeds],
        "relationships": [_jsonable(item) for item in bundle.relationship_seeds],
        "person_relations": [_jsonable(item) for item in bundle.person_relation_seeds],
        "groups": [_jsonable(item) for item in bundle.group_seeds],
        "places": [_jsonable(item) for item in bundle.place_seeds],
        "place_relations": [_jsonable(item) for item in bundle.place_relation_seeds],
        "knowledge_episode_max_chars": bundle.knowledge_episode_max_chars,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def planned_genesis_output_ids(bundle: GenesisBundle) -> tuple[str, ...]:
    """Return the core durable IDs emitted by one typed Genesis submission."""

    profile = bundle.profile_draft.profile
    elfie_id = profile.identity.elfie_id
    safe_elfie = safe_component(elfie_id)
    output: list[str] = [f"{SELF_NODE_PREFIX}{safe_elfie}"]
    output.extend(
        f"{PLACE_NODE_PREFIX}{safe_elfie}:{safe_component(place.place_id)}"
        for place in bundle.place_seeds
    )

    seen_targets: set[str] = set()
    for relationship in bundle.relationship_seeds:
        target = relationship.object_id or relationship.person_id
        if target in seen_targets:
            continue
        seen_targets.add(target)
        output.append(f"{PERSON_NODE_PREFIX}{safe_elfie}:{safe_component(target)}")

    # Full knowledge groups and their authored, source-backed graph skeleton
    # are published together; later consolidation may enrich those identities.
    output.extend(
        knowledge_group_id(safe_elfie, group) for group in knowledge_groups(bundle)
    )
    output.extend(
        f"{ENTITY_NODE_PREFIX}{safe_elfie}:{safe_component(node_id)}"
        for node_id in dict.fromkeys(
            node.node_id for seed in bundle.knowledge_seeds for node in seed.graph_nodes
        )
    )
    for episode in bundle.episode_seeds:
        safe_seed = safe_component(episode.seed_id)
        output.append(f"{EPISODE_NODE_PREFIX}{safe_elfie}:{safe_seed}")
    output.extend(
        f"genesis:group:{safe_elfie}:{safe_component(g.group_id)}"
        for g in bundle.group_seeds
    )
    return tuple(output)


def output_ids_hash(output_ids: Iterable[str]) -> str:
    """Hash the declared durable output inventory in one stable form.

    The inventory is an integrity boundary, not a source from which a life can
    be regenerated.  Sorting makes the receipt independent of SQLite query
    order while preserving the exact identifier values.
    """

    values = tuple(str(value) for value in output_ids)
    encoded = json.dumps(
        sorted(values),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _jsonable(model_dump(mode="json"))
    if is_dataclass(value):
        return _jsonable(asdict(cast(Any, value)))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return str(value)


__all__ = (
    "EVENT_NODE_PREFIX",
    "EPISODE_NODE_PREFIX",
    "KNOWLEDGE_NODE_PREFIX",
    "PERSON_NODE_PREFIX",
    "PLACE_NODE_PREFIX",
    "SELF_NODE_PREFIX",
    "genesis_content_hash",
    "output_ids_hash",
    "planned_genesis_output_ids",
    "safe_component",
)
