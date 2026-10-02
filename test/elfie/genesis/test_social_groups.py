"""Acceptance of identities, sourced groups and the final graph hand-off."""

from dataclasses import replace

import pytest

from infrastructure.persistence.configuration.species import load_species_catalog

from .test_contracts import _compilation


def test_case_has_unique_natural_names_and_own_life_stages():
    r = _compilation(stage="mature", age_years=8, seed=1)
    names = [p.display_name for p in r.plan.skeleton.people]
    assert len(names) == len(set(names))
    assert all(not any(c.isdigit() for c in name) for name in names)
    for seed in r.bundle.relationship_seeds:
        if seed.age_years_at_genesis is not None and seed.object_kind == "elfie":
            from elfie.genesis.compiler import stage_for_age

            assert seed.age_band_at_genesis == stage_for_age(
                seed.person_species_id,
                seed.age_years_at_genesis,
                load_species_catalog(),
            )


def test_groups_have_real_members_and_nonself_social_edges():
    r = _compilation(stage="mature", age_years=8, seed=1)
    s = r.plan.skeleton
    assert s.groups
    people = {p.person_id for p in s.people}
    assert all(set(g.member_ids) <= people and g.source_ref for g in s.groups)
    assert {g.kind for g in s.groups} >= {"family", "growth", "public"}
    assert any(
        e.subject_id != "self"
        and e.object_id != "self"
        and e.relation in {"acquaintance", "classmate", "colleague"}
        for e in s.relationships
    )
    assert len(
        {(e.subject_id, e.relation, e.object_id) for e in s.relationships}
    ) == len(s.relationships)


def test_activity_contacts_allow_zero_and_multiple_and_do_not_make_venue_home():
    counts = []
    for seed in (1, 7, 23):
        r = _compilation(stage="mature", age_years=8, seed=seed)
        for a in r.life_context.activities:
            if a.direction == "public" and a.status == "completed":
                counts.append(len(a.participant_ids))
        for person in r.bundle.relationship_seeds:
            if person.role == "activity_contact":
                assert person.person_gender in {"male", "female"}
                assert not person.home_place_id
    assert 0 in counts
    assert any(n > 1 for n in counts)


def test_completed_contact_edges_are_materialized_and_exported():
    r = _compilation(stage="mature", age_years=8, seed=1)
    assert r.bundle.person_relation_seeds
    assert r.bundle.group_seeds
    completed = {
        a.activity_id for a in r.life_context.activities if a.status == "completed"
    }
    for e in r.life_context.relationships:
        if e.source_ref in completed:
            assert e.status == "established"
    assert any(e.relation == "partner" for e in r.bundle.person_relation_seeds)
    assert any(
        e.subject_id != "self" and e.relation == "parent_of"
        for e in r.bundle.person_relation_seeds
    )


def test_partner_sibling_expansion_reuses_core_without_changing_family_graph(
    monkeypatch,
):
    from elfie.genesis.family import FamilyGenerator

    original = FamilyGenerator.generate_family_graph
    captured = []

    def capture(generator, person):
        graph = original(generator, person)
        captured.append(graph)
        return graph

    monkeypatch.setattr(FamilyGenerator, "generate_family_graph", capture)
    r = _compilation(stage="mature", age_years=8, seed=1)
    assert captured == [r.life_context.family_graph]
    assert r.life_context.partner_sibling_families
    assert any(p.role == "partner_sibling_partner" for p in r.bundle.relationship_seeds)


def test_unknown_group_member_is_rejected():
    r = _compilation(stage="mature", age_years=8, seed=1)
    s = r.plan.skeleton
    g = replace(s.groups[0], member_ids=(*s.groups[0].member_ids, "missing"))
    with pytest.raises(ValueError, match="群组"):
        replace(s, groups=(g,)).validate_skeleton()


def test_memory_preserves_groups_and_nonself_parent_links():
    from elfie.genesis import GenesisMemoryCommitter
    from elfie.genesis.serialization import safe_component
    from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

    result = _compilation(stage="mature", age_years=8, seed=1)
    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        receipt = GenesisMemoryCommitter().commit(result.bundle, storage)
        assert receipt.node_ids == result.bundle.manifest.output_ids
        nodes = storage.list_graph_nodes(limit=10000)
        assertions = storage.list_graph_assertions(limit=10000)
        assert sum(
            n.node_type == "group" and n.node_id.startswith("genesis:group:")
            for n in nodes
        ) == len(result.bundle.group_seeds)
        parent_edge = next(
            e
            for e in result.bundle.person_relation_seeds
            if e.relation == "parent_of"
            and e.subject_id != "self"
            and e.object_id != "self"
        )
        subject = "genesis:person:genesis-check:" + safe_component(
            parent_edge.subject_id
        )
        target = "genesis:person:genesis-check:" + safe_component(parent_edge.object_id)
        assert any(
            a.predicate == "parent_of"
            and a.subject_id == subject
            and a.object_node_id == target
            for a in assertions
        )
        assert any(
            a.predicate == "member_of"
            and str(a.object_node_id).startswith("genesis:group:")
            for a in assertions
        )


def test_old_protagonist_does_not_keep_overage_teacher_alive():
    result = _compilation(species_id="dog", stage="elder", age_years=18, seed=1)
    teacher = next(r for r in result.bundle.relationship_seeds if r.role == "teacher")
    assert teacher.life_status == "deceased"
    assert teacher.age_years_at_genesis is None
    assert teacher.death_event_age_years is not None
    for activity in result.life_context.activities:
        if (
            activity.status == "completed"
            and teacher.person_id in activity.participant_ids
        ):
            assert activity.age_year < teacher.death_event_age_years


def test_social_people_only_use_species_with_loaded_life_parameters():
    result = _compilation(species_id="dog", stage="adolescent", age_years=3, seed=23)
    catalog = load_species_catalog()
    for person in result.bundle.relationship_seeds:
        if person.object_kind == "elfie":
            assert person.person_species_id in catalog.supported_species


def test_groups_require_three_distinct_people_but_keep_pair_relationships():
    result = _compilation(stage="mature", age_years=8, seed=1)
    assert all(len(set(g.member_ids)) >= 3 for g in result.plan.skeleton.groups)
    assert all(len(set(g.member_ids)) >= 3 for g in result.life_context.groups)
    assert all(len(set(g.member_ids)) >= 3 for g in result.bundle.group_seeds)
    # A mentor/student pair remains a relationship without needing a Group.
    teacher = next(r for r in result.bundle.relationship_seeds if r.role == "teacher")
    assert any(
        e.subject_id == "self"
        and e.object_id == teacher.person_id
        and e.relation == "teacher"
        for e in result.bundle.person_relation_seeds
    )
    assert not any(
        g.group_id == "group:learning:apprenticeship" for g in result.bundle.group_seeds
    )


def test_every_group_pair_has_a_named_sourced_relationship():
    r = _compilation(stage="mature", age_years=8, seed=1)
    for context in (r.plan.skeleton, r.life_context):
        named = {
            (e.subject_id, e.object_id)
            for e in context.relationships
            if e.label and e.source_ref and len(e.relationship_path) >= 2
        }
        for group in context.groups:
            assert all(
                (a, b) in named
                for a in group.member_ids
                for b in group.member_ids
                if a != b
            )


def test_important_friends_get_bounded_heard_families_without_changing_self_family():
    r = _compilation(stage="mature", age_years=8, seed=1)
    cores = r.life_context.important_friend_families
    assert 1 <= len(cores) <= 2
    records = {p.person_id: p for p in r.bundle.relationship_seeds}
    friends = [
        p for p in records.values() if p.role == "friend" and p.life_status == "alive"
    ]
    chosen = sorted(friends, key=lambda p: (-p.importance, p.person_id))[:2]
    assert [c.protagonist.person_id for c in cores] == [p.person_id for p in chosen]
    for core in cores:
        anchor = core.protagonist.person_id
        assert anchor in records
        members = [core.origin.union.first, core.origin.union.second]
        assert len(members) == 2
        for p in members:
            record = records[p.person_id]
            assert record.familiarity == "heard"
            assert not record.episode_ids
            assert anchor in record.related_person_ids
        assert not any(p.person_id == "self" for p in core.origin.children)
    assert r.plan.skeleton.family_graph == r.life_context.family_graph


def test_friend_family_future_lifespan_is_not_a_current_death():
    r = _compilation(stage="mature", age_years=8, seed=1)
    records = {p.person_id: p for p in r.bundle.relationship_seeds}
    people = {p.person_id: p for p in r.life_context.people}
    living = 0
    for core in r.life_context.important_friend_families:
        families = [core.origin] + ([core.own] if core.own else [])
        for family in families:
            for person in (family.union.first, family.union.second, *family.children):
                if person.person_id == core.protagonist.person_id:
                    continue
                record = records[person.person_id]
                deceased = person.death_year is not None and person.death_year <= 0
                assert (record.life_status == "deceased") == deceased
                if not deceased:
                    living += 1
                    assert record.age_years_at_genesis == -person.birth_year
                    assert people[person.person_id].death_age_year is None
    assert living > 0


def test_final_bundle_rejects_a_missing_group_pair():
    from elfie.genesis.contracts import GenesisValidationError

    r = _compilation(stage="mature", age_years=8, seed=1)
    group = r.bundle.group_seeds[0]
    a, b = group.member_ids[:2]
    broken = replace(
        r.bundle,
        person_relation_seeds=tuple(
            e
            for e in r.bundle.person_relation_seeds
            if (e.subject_id, e.object_id) != (a, b)
        ),
    )
    with pytest.raises(GenesisValidationError, match="两两关系"):
        broken.validate()
