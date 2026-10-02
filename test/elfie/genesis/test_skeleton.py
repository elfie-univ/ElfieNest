"""Acceptance of the stage-three hand-off, independently of story text."""

from dataclasses import replace

import pytest

from test.elfie.genesis.test_contracts import _compilation


def test_stage_three_has_graphs_and_does_not_claim_planned_visits() -> None:
    result = _compilation(stage="mature", age_years=8, seed=23)
    skeleton = result.plan.skeleton
    assert skeleton.family_graph is not None
    assert skeleton.people
    assert skeleton.places
    assert skeleton.place_links
    assert skeleton.knowledge_nodes
    assert skeleton.life_segments
    assert skeleton.activities
    assert skeleton.mobility.visited_place_ids == ()
    assert all(item.status != "completed" for item in skeleton.activities)
    skeleton.validate_skeleton()
    assert result.life_context.mobility.visited_place_ids


def test_family_graph_survives_hand_off_without_resampling() -> None:
    result = _compilation(stage="elder", age_years=11)
    assert result.plan.skeleton.family_graph == result.life_context.family_graph
    assert result.plan.skeleton.identity == result.life_context.identity


def test_learning_has_teacher_duration_and_no_unearned_qualification() -> None:
    result = _compilation(stage="adolescent", age_years=2)
    skeleton = result.plan.skeleton
    learning = [s for s in skeleton.life_segments if s.kind == "learning"]
    assert learning
    assert learning[0].participant_ids
    assert skeleton.vocation.vocation_id == ""
    assert all(s.kind != "work" for s in skeleton.life_segments)
    assert not any(
        e.theme_id == "apprenticeship-completion" for e in result.bundle.episode_seeds
    )


def test_activity_time_conflicts_are_rejected() -> None:
    result = _compilation(stage="mature", age_years=8)
    skeleton = result.plan.skeleton
    scheduled = [a for a in skeleton.activities if a.status == "scheduled"]
    assert scheduled
    activity = scheduled[0]
    duplicate = replace(activity, activity_id="conflict")
    with pytest.raises(ValueError, match="时间冲突"):
        replace(skeleton, activities=(activity, duplicate)).validate_skeleton()


def test_public_events_reference_specific_occurrences() -> None:
    result = _compilation(stage="mature", age_years=8, seed=23)
    activities = [a for a in result.plan.skeleton.activities if a.direction == "public"]
    assert activities
    assert all(a.event_instance_id for a in activities)
    assert len({a.activity_id for a in activities}) == len(activities)
    assert any(a.status == "excluded" and a.reason for a in activities)


def test_replay_and_fact_references_are_stable() -> None:
    first = _compilation(stage="mature", age_years=8)
    second = _compilation(stage="mature", age_years=8)
    assert first.plan.skeleton == second.plan.skeleton
    assert first.bundle == second.bundle
    ids = {a.activity_id for a in first.plan.skeleton.activities}
    assert any(e.source_ref in ids for e in first.bundle.episode_seeds)


def test_public_occurrence_date_is_shared_and_does_not_use_earth_anchor() -> None:
    first = _compilation("public-a", age_years=8, stage="mature", seed=7).plan.skeleton
    second = _compilation(
        "public-b", age_years=8, stage="mature", seed=23
    ).plan.skeleton

    def gathering_days(skeleton):
        return {
            a.event_instance_id: a.start_day + a.travel_days // 2 + 1
            for a in skeleton.activities
            if a.direction == "public"
            and a.event_instance_id.startswith("saevi_firstroot_gathering")
        }

    assert gathering_days(first) == gathering_days(second)
    assert any(
        d.object_id == "earth_contact_announcement" and d.outcome == "not_applicable"
        for d in first.decisions
    )


def test_complete_family_output_matches_the_frozen_generator(monkeypatch) -> None:
    from elfie.genesis.family import FamilyGenerator

    original = FamilyGenerator.generate_family_graph
    generated = []

    def capture(generator, person):
        graph = original(generator, person)
        generated.append(graph)
        return graph

    monkeypatch.setattr(FamilyGenerator, "generate_family_graph", capture)
    result = _compilation(stage="mature", age_years=8, seed=23)
    assert len(generated) == 1
    assert result.plan.skeleton.family_graph == generated[0]
    assert result.life_context.family_graph == generated[0]


def test_excluded_activities_produce_neither_memory_nor_contacts() -> None:
    result = _compilation(stage="mature", age_years=8)
    excluded = {
        a.activity_id for a in result.plan.skeleton.activities if a.status == "excluded"
    }
    assert not excluded.intersection(e.source_ref for e in result.bundle.episode_seeds)
    assert not excluded.intersection(
        r.source_ref for r in result.bundle.relationship_seeds
    )
