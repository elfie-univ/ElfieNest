"""Deterministic, in-memory Memory projections over the shared graph contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Sequence

from elfie.brain.memory.memory_records import (
    AssertionInput,
    MemoryInspectionSnapshot,
    NodeInput,
    RecallAssertion,
    RecallNode,
)
from elfie.brain.memory.ontology import MemoryOntologySnapshot


@dataclass(frozen=True)
class MemoryGraphSlice:
    """A read-only selection of existing graph identities and assertions."""

    slice_id: str
    node_ids: tuple[str, ...] = ()
    assertion_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryConsolidationSlices:
    """The six ontology-derived slices plus the final cross-group pass.

    These are transient projections, not persisted Memory objects. `write_nodes`
    and `write_assertions` are the unique source-grounded records from which the
    slices were derived; the normal Consolidation Unit of Work remains their
    only write path.
    """

    type_slices: tuple[MemoryGraphSlice, ...]
    self_model: MemoryGraphSlice
    cross_group_assertion_ids: tuple[str, ...]
    attribute_assertion_ids: tuple[str, ...]
    external_assertion_ids: tuple[str, ...]
    write_nodes: tuple[NodeInput, ...]
    write_assertions: tuple[AssertionInput, ...]


def project_memory_slices(
    nodes: Sequence[NodeInput],
    assertions: Sequence[AssertionInput],
    ontology: MemoryOntologySnapshot,
    *,
    self_node_id: str | None = None,
    self_model_graph: MemoryInspectionSnapshot | None = None,
) -> MemoryConsolidationSlices:
    """Classify one validated consolidation projection without creating Nodes.

    The five primary slices select Nodes by their registered primary group and
    keep every sourced, registered Node-to-Node assertion within that slice.
    The self-model slice is edge-first and non-recursive. Cross-group edges are
    retained in a final independent pass. Literal attributes and assertions
    whose existing endpoint is outside this candidate projection are preserved
    for the storage adapter's full endpoint validation.
    """

    nodes_by_id: dict[str, NodeInput] = {}
    group_by_node_id: dict[str, str] = {}
    nodes_by_group: dict[str, list[NodeInput]] = {
        group.group_id: [] for group in ontology.type_groups
    }
    for node in nodes:
        group_id = ontology.group_for_node_type(node.node_type)
        previous = nodes_by_id.get(node.node_id)
        if previous is not None:
            if previous != node:
                raise ValueError(
                    f"conflicting consolidation Nodes share ID {node.node_id!r}"
                )
            continue
        nodes_by_id[node.node_id] = node
        group_by_node_id[node.node_id] = group_id
        nodes_by_group[group_id].append(node)

    normalized_assertions, assertion_refs = _deduplicate_assertions(
        assertions, ontology
    )
    type_slices: list[MemoryGraphSlice] = []
    for group in ontology.type_groups:
        group_nodes = nodes_by_group[group.group_id]
        group_ids = {node.node_id for node in group_nodes}
        group_assertions = tuple(
            ref
            for assertion, ref in zip(normalized_assertions, assertion_refs)
            if assertion.object_node_id is not None
            and assertion.subject_id in group_ids
            and assertion.object_node_id in group_ids
            and _is_sourced_registered(assertion, nodes_by_id, ontology)
        )
        type_slices.append(
            MemoryGraphSlice(
                slice_id=group.group_id,
                node_ids=tuple(node.node_id for node in group_nodes),
                assertion_ids=group_assertions,
            )
        )

    self_nodes_by_id = dict(nodes_by_id)
    self_projection_assertions = list(normalized_assertions)
    self_projection_refs = list(assertion_refs)
    if self_model_graph is not None:
        for recalled_node in self_model_graph.nodes:
            self_nodes_by_id.setdefault(
                recalled_node.node_id, _node_input_from_recall(recalled_node)
            )
        recalled_assertions = tuple(
            converted
            for recalled in self_model_graph.assertions
            if (converted := _assertion_input_from_recall(recalled)) is not None
        )
        if recalled_assertions:
            deduplicated_self_assertions, deduplicated_self_refs = (
                _deduplicate_assertions(
                    (*self_projection_assertions, *recalled_assertions), ontology
                )
            )
            self_projection_assertions = list(deduplicated_self_assertions)
            self_projection_refs = list(deduplicated_self_refs)

    anchor_id = self_node_id
    if anchor_id is None:
        anchor_id = next(
            (
                node.node_id
                for node in self_nodes_by_id.values()
                if node.node_type == "elfie" and node.properties.get("is_self") is True
            ),
            None,
        )
    self_node_ids: set[str] = set()
    selected_self_assertion_refs: set[str] = set()
    if anchor_id is not None:
        anchor = self_nodes_by_id.get(anchor_id)
        if anchor is not None and anchor.node_type == "elfie":
            self_node_ids.add(anchor_id)
            stance_predicates = set(ontology.self_stance_predicates)
            for assertion, ref in zip(self_projection_assertions, self_projection_refs):
                if (
                    assertion.subject_id == anchor_id
                    and assertion.object_node_id in self_nodes_by_id
                    and ontology.resolve_predicate(assertion.predicate)
                    in stance_predicates
                    and _is_sourced_registered(assertion, self_nodes_by_id, ontology)
                ):
                    self_node_ids.add(assertion.object_node_id or "")
                    selected_self_assertion_refs.add(ref)
            # Stance edges select the neighborhood once; this second pass adds
            # its registered internal relations without growing it recursively.
            for assertion, ref in zip(self_projection_assertions, self_projection_refs):
                if (
                    assertion.object_node_id is not None
                    and assertion.subject_id in self_node_ids
                    and assertion.object_node_id in self_node_ids
                    and _is_sourced_registered(assertion, self_nodes_by_id, ontology)
                ):
                    selected_self_assertion_refs.add(ref)

    selected_ids = set(nodes_by_id)
    cross_group_refs = tuple(
        ref
        for assertion, ref in zip(normalized_assertions, assertion_refs)
        if assertion.object_node_id is not None
        and assertion.subject_id in selected_ids
        and assertion.object_node_id in selected_ids
        and group_by_node_id[assertion.subject_id]
        != group_by_node_id[assertion.object_node_id]
        and _is_sourced_registered(assertion, nodes_by_id, ontology)
    )
    attribute_refs = tuple(
        ref
        for assertion, ref in zip(normalized_assertions, assertion_refs)
        if assertion.object_node_id is None
        and assertion.subject_id in nodes_by_id
        and _is_sourced_registered(assertion, nodes_by_id, ontology)
    )
    external_refs = tuple(
        ref
        for assertion, ref in zip(normalized_assertions, assertion_refs)
        if assertion.object_node_id is not None
        and (
            assertion.subject_id not in nodes_by_id
            or assertion.object_node_id not in nodes_by_id
        )
    )

    return MemoryConsolidationSlices(
        type_slices=tuple(type_slices),
        self_model=MemoryGraphSlice(
            slice_id="self_model",
            node_ids=tuple(
                node.node_id
                for node in self_nodes_by_id.values()
                if node.node_id in self_node_ids
            ),
            assertion_ids=tuple(
                ref
                for ref in self_projection_refs
                if ref in selected_self_assertion_refs
            ),
        ),
        cross_group_assertion_ids=cross_group_refs,
        attribute_assertion_ids=attribute_refs,
        external_assertion_ids=external_refs,
        write_nodes=tuple(nodes_by_id.values()),
        write_assertions=tuple(normalized_assertions),
    )


def _deduplicate_assertions(
    assertions: Sequence[AssertionInput], ontology: MemoryOntologySnapshot
) -> tuple[tuple[AssertionInput, ...], tuple[str, ...]]:
    normalized: list[AssertionInput] = []
    refs: list[str] = []
    index_by_key: dict[str, int] = {}
    for assertion in assertions:
        canonical = ontology.resolve_predicate(assertion.predicate)
        candidate = (
            assertion
            if assertion.predicate == canonical
            else replace(assertion, predicate=canonical)
        )
        key = _assertion_fact_key(candidate)
        existing_index = index_by_key.get(key)
        ref = (
            candidate.assertion_id
            or f"pending:{hashlib.sha256(key.encode()).hexdigest()[:24]}"
        )
        if existing_index is None:
            index_by_key[key] = len(normalized)
            normalized.append(candidate)
            refs.append(ref)
            continue
        existing = normalized[existing_index]
        if (
            existing.assertion_id is not None
            and candidate.assertion_id is not None
            and existing.assertion_id != candidate.assertion_id
        ):
            # SQLite's assertion identity is the canonical fact, not a caller
            # supplied alternate ID; preserve the conflict for adapter checks.
            index_by_key[key + f"|id:{candidate.assertion_id}"] = len(normalized)
            normalized.append(candidate)
            refs.append(ref)
            continue
        merged_evidence = tuple(
            dict.fromkeys((*existing.evidence_ids, *candidate.evidence_ids))
        )
        normalized[existing_index] = replace(
            existing,
            assertion_id=existing.assertion_id or candidate.assertion_id,
            evidence_ids=merged_evidence,
        )
    return tuple(normalized), tuple(refs)


def _assertion_fact_key(assertion: AssertionInput) -> str:
    payload = {
        "subject": assertion.subject_id,
        "predicate": assertion.predicate,
        "object_node": assertion.object_node_id,
        "object_literal": assertion.object_literal,
        "object_literal_type": assertion.object_literal_type,
        "object_unit": assertion.object_unit,
        "polarity": assertion.polarity,
        "epistemic_status": assertion.epistemic_status,
        "viewpoint": assertion.viewpoint,
        "context": assertion.context,
        "valid_from": assertion.valid_from,
        "valid_to": assertion.valid_to,
    }
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _node_input_from_recall(node: RecallNode) -> NodeInput:
    return NodeInput(
        node_id=node.node_id,
        node_type=node.node_type,
        canonical_label=node.label,
        description=node.description,
        properties=node.properties,
    )


def _assertion_input_from_recall(assertion: RecallAssertion) -> AssertionInput | None:
    if assertion.object_node_id is None and assertion.object_literal is None:
        return None
    qualifiers = assertion.qualifiers

    def text_value(name: str) -> str | None:
        value = qualifiers.get(name)
        return value if isinstance(value, str) else None

    polarity = text_value("polarity") or "positive"
    epistemic_status = text_value("epistemic_status") or "known"
    if polarity not in {"positive", "negative"}:
        return None
    if epistemic_status not in {"known", "believed", "uncertain", "reported"}:
        return None
    return AssertionInput(
        subject_id=assertion.subject_id,
        predicate=assertion.predicate,
        object_node_id=assertion.object_node_id,
        object_literal=(
            assertion.object_literal if assertion.object_node_id is None else None
        ),
        object_unit=text_value("object_unit"),
        polarity=polarity,  # type: ignore[arg-type]
        epistemic_status=epistemic_status,  # type: ignore[arg-type]
        viewpoint=text_value("viewpoint"),
        context=text_value("context"),
        valid_from=text_value("valid_from"),
        valid_to=text_value("valid_to"),
        confidence=assertion.confidence,
        initial_confidence=assertion.confidence,
        evidence_ids=assertion.evidence_ids,
        assertion_id=assertion.assertion_id,
        importance=assertion.importance,
        initial_importance=assertion.importance,
        half_life_days=assertion.half_life_days,
        object_literal_type=text_value("object_literal_type"),
    )


def _is_sourced_registered(
    assertion: AssertionInput,
    nodes_by_id: dict[str, NodeInput],
    ontology: MemoryOntologySnapshot,
) -> bool:
    subject = nodes_by_id.get(assertion.subject_id)
    if subject is None or not assertion.evidence_ids:
        return False
    spec = ontology.predicate_spec(assertion.predicate)
    if assertion.object_node_id is None:
        if not spec.object_literal:
            return False
        object_type = None
        object_is_literal = True
    else:
        object = nodes_by_id.get(assertion.object_node_id)
        if object is None:
            return False
        object_type = object.node_type
        object_is_literal = False
    qualifiers = tuple(
        name
        for name, value in (
            ("context", assertion.context),
            ("viewpoint", assertion.viewpoint),
            ("valid_from", assertion.valid_from),
            ("valid_to", assertion.valid_to),
            ("object_unit", assertion.object_unit),
            ("object_literal_type", assertion.object_literal_type),
            ("polarity", assertion.polarity),
            ("epistemic_status", assertion.epistemic_status),
            ("confidence", assertion.confidence),
            ("importance", assertion.importance),
        )
        if value is not None
    )
    ontology.validate_assertion(
        predicate=assertion.predicate,
        subject_type=subject.node_type,
        object_type=object_type,
        object_is_literal=object_is_literal,
        qualifiers=qualifiers,
        has_source=True,
    )
    return True


__all__ = (
    "MemoryConsolidationSlices",
    "MemoryGraphSlice",
    "project_memory_slices",
)
