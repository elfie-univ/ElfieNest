"""Canonical serialization shared by the Genesis compiler and committer.

There is deliberately one calculation for the semantic digest and durable
output inventory.  The compiler declares what it is handing off and the
Memory committer verifies that declaration before opening its source-first
unit of work.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, cast

from .contracts import GenesisBundle

# The Memory node is a technical completion receipt, not a resident-visible
# manifest and never a source from which a life can be reconstructed.
GENESIS_RECEIPT_PREFIX = "genesis:receipt:"
SELF_NODE_PREFIX = "genesis:self:"
SELF_MODEL_PREFIX = "genesis:self-model:"
KNOWLEDGE_NODE_PREFIX = "genesis:knowledge:"
PLACE_NODE_PREFIX = "genesis:place:"
PERSON_NODE_PREFIX = "genesis:person:"
EPISODE_NODE_PREFIX = "genesis:episode:"
EVENT_NODE_PREFIX = "genesis:event:"


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
        "places": [_jsonable(item) for item in bundle.place_seeds],
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
    output: list[str] = [
        f"{SELF_NODE_PREFIX}{safe_elfie}",
        f"{SELF_MODEL_PREFIX}{safe_elfie}",
    ]
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

    output.extend(
        f"{KNOWLEDGE_NODE_PREFIX}{safe_elfie}:{safe_component(seed.seed_id)}"
        for seed in bundle.knowledge_seeds
    )
    for episode in bundle.episode_seeds:
        safe_seed = safe_component(episode.seed_id)
        output.extend(
            (
                f"{EPISODE_NODE_PREFIX}{safe_elfie}:{safe_seed}",
                f"{EVENT_NODE_PREFIX}{safe_elfie}:{safe_seed}",
            )
        )
    output.append(f"{GENESIS_RECEIPT_PREFIX}{elfie_id}")
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
    "GENESIS_RECEIPT_PREFIX",
    "KNOWLEDGE_NODE_PREFIX",
    "PERSON_NODE_PREFIX",
    "PLACE_NODE_PREFIX",
    "SELF_MODEL_PREFIX",
    "SELF_NODE_PREFIX",
    "genesis_content_hash",
    "output_ids_hash",
    "planned_genesis_output_ids",
    "safe_component",
)
