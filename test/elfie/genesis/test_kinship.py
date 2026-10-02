"""Pair coverage and kinship names use factual graph paths."""

from dataclasses import dataclass

import pytest

from elfie.genesis.kinship import complete_group_relationships
from elfie.genesis.skeleton import SkeletonGroup, SkeletonPerson, SkeletonRelationship


@dataclass(frozen=True)
class Context:
    people: tuple
    relationships: tuple
    groups: tuple
    activities: tuple = ()
    life_segments: tuple = ()


def _family():
    info = {
        "self": ("male", 0),
        "father": ("male", -25),
        "mother": ("female", -24),
        "grandfather": ("male", -50),
        "grandmother": ("female", -48),
        "maternal_grandfather": ("male", -49),
        "maternal_grandmother": ("female", -47),
        "brother": ("male", 2),
        "brother_wife": ("female", 3),
        "older_brother": ("male", -2),
        "older_brother_wife": ("female", -1),
        "uncle": ("male", -23),
        "uncle_wife": ("female", -22),
        "elder_uncle": ("male", -27),
        "elder_uncle_wife": ("female", -26),
        "aunt": ("female", -21),
        "aunt_husband": ("male", -20),
        "maternal_uncle": ("male", -22),
        "maternal_uncle_wife": ("female", -21),
        "maternal_aunt": ("female", -23),
        "maternal_aunt_husband": ("male", -24),
        "cousin": ("female", 1),
        "maternal_cousin": ("male", -1),
        "wife": ("female", 1),
        "wife_father": ("male", -24),
        "wife_mother": ("female", -23),
        "son": ("male", 22),
        "daughter": ("female", 24),
        "grandson": ("male", 45),
        "granddaughter": ("female", 46),
        "nephew": ("male", 25),
    }
    people = tuple(
        SkeletonPerson(i, i, "saevi", g, age, "fixture") for i, (g, age) in info.items()
    )
    parents = {
        "father": ("grandfather", "grandmother"),
        "uncle": ("grandfather", "grandmother"),
        "elder_uncle": ("grandfather", "grandmother"),
        "aunt": ("grandfather", "grandmother"),
        "mother": ("maternal_grandfather", "maternal_grandmother"),
        "maternal_uncle": ("maternal_grandfather", "maternal_grandmother"),
        "maternal_aunt": ("maternal_grandfather", "maternal_grandmother"),
        "self": ("father", "mother"),
        "brother": ("father", "mother"),
        "older_brother": ("father", "mother"),
        "cousin": ("uncle", "uncle_wife"),
        "maternal_cousin": ("maternal_uncle", "maternal_uncle_wife"),
        "wife": ("wife_father", "wife_mother"),
        "son": ("self", "wife"),
        "daughter": ("self", "wife"),
        "grandson": ("son",),
        "granddaughter": ("daughter",),
        "nephew": ("brother", "brother_wife"),
    }
    edges = [
        SkeletonRelationship(p, c, "parent_of", "established", "fixture")
        for c, ps in parents.items()
        for p in ps
    ]
    couples = [
        ("father", "mother"),
        ("grandfather", "grandmother"),
        ("maternal_grandfather", "maternal_grandmother"),
        ("brother", "brother_wife"),
        ("older_brother", "older_brother_wife"),
        ("uncle", "uncle_wife"),
        ("elder_uncle", "elder_uncle_wife"),
        ("aunt", "aunt_husband"),
        ("maternal_uncle", "maternal_uncle_wife"),
        ("maternal_aunt", "maternal_aunt_husband"),
        ("self", "wife"),
        ("wife_father", "wife_mother"),
    ]
    edges.extend(
        SkeletonRelationship(a, b, "partner", "established", "fixture")
        for a, b in couples
    )
    return Context(
        people,
        tuple(edges),
        (SkeletonGroup("family", "family", "fixture", tuple(info), "fixture"),),
    )


@pytest.mark.parametrize(
    "target,label",
    [
        ("father", "父亲"),
        ("mother", "母亲"),
        ("grandfather", "爷爷"),
        ("grandmother", "奶奶"),
        ("maternal_grandfather", "外公"),
        ("maternal_grandmother", "外婆"),
        ("brother", "弟弟"),
        ("brother_wife", "弟媳"),
        ("older_brother_wife", "嫂子"),
        ("uncle", "叔叔"),
        ("uncle_wife", "婶婶"),
        ("elder_uncle", "伯伯"),
        ("elder_uncle_wife", "伯母"),
        ("aunt", "姑姑"),
        ("aunt_husband", "姑父"),
        ("maternal_uncle", "舅舅"),
        ("maternal_uncle_wife", "舅妈"),
        ("maternal_aunt", "姨妈"),
        ("maternal_aunt_husband", "姨父"),
        ("cousin", "堂妹"),
        ("maternal_cousin", "表哥"),
        ("wife_father", "岳父"),
        ("wife_mother", "岳母"),
        ("grandson", "孙子"),
        ("granddaughter", "外孙女"),
        ("nephew", "侄子"),
    ],
)
def test_specific_kinship_names(target, label):
    context = complete_group_relationships(_family())
    edge = next(
        e
        for e in context.relationships
        if e.subject_id == "self" and e.object_id == target
    )
    assert edge.label == label
    assert edge.relationship_path[0] == "self"
    assert edge.relationship_path[-1] == target


def test_every_ordered_pair_has_label_and_path_and_is_idempotent():
    context = complete_group_relationships(_family())
    assert len(context.relationships) == len(context.people) * (len(context.people) - 1)
    assert all(
        e.label and e.relationship_path and e.source_ref for e in context.relationships
    )
    assert complete_group_relationships(context) == context


def test_spouses_of_siblings_are_affinity_not_biological_siblings():
    context = complete_group_relationships(_family())
    edge = next(
        e
        for e in context.relationships
        if e.subject_id == "brother_wife" and e.object_id == "older_brother_wife"
    )
    assert edge.label == "丈夫的哥哥的妻子"
    assert edge.relationship_path == (
        "brother_wife",
        "brother",
        "father",
        "older_brother",
        "older_brother_wife",
    )


def test_social_group_covers_pairs_without_inventing_friendship():
    people = tuple(
        SkeletonPerson(i, i, "saevi", "male", 0, "meeting") for i in ("a", "b", "c")
    )
    group = SkeletonGroup("meeting", "public", "meeting", ("a", "b", "c"), "meeting")
    context = complete_group_relationships(Context(people, (), (group,)))
    assert len(context.relationships) == 6
    assert all(
        e.relation == "acquaintance" and e.status == "contact_slot"
        for e in context.relationships
    )


def test_disconnected_family_members_are_rejected():
    people = tuple(
        SkeletonPerson(i, i, "saevi", "male", 0, "fixture") for i in ("a", "b", "c")
    )
    group = SkeletonGroup("family", "family", "fixture", ("a", "b", "c"), "fixture")
    with pytest.raises(ValueError, match="关系路径"):
        complete_group_relationships(Context(people, (), (group,)))


def test_learning_mentor_inverse_is_student_not_classmate():
    people = tuple(
        SkeletonPerson(i, i, "saevi", "male", 0, "learning")
        for i in ("student", "teacher", "peer")
    )
    group = SkeletonGroup(
        "learning", "learning", "learning", tuple(p.person_id for p in people), "lesson"
    )
    edge = SkeletonRelationship(
        "student", "teacher", "teacher", "contact_slot", "lesson"
    )
    context = complete_group_relationships(Context(people, (edge,), (group,)))
    lookup = {(e.subject_id, e.object_id): e for e in context.relationships}
    assert lookup[("teacher", "student")].label == "学生"
    assert lookup[("peer", "teacher")].label == "老师"
    assert lookup[("student", "peer")].label == "同学"
    assert all(e.status == "contact_slot" for e in context.relationships)


@pytest.mark.parametrize(
    "relation,inverse,label",
    [
        ("friend", "friend", "朋友"),
        ("neighbor", "neighbor", "邻居"),
        ("colleague", "colleague", "同事"),
        ("classmate", "classmate", "同学"),
        ("teacher", "student", "学生"),
    ],
)
def test_social_inverse_preserves_specific_role_even_without_group(
    relation, inverse, label
):
    people = tuple(
        SkeletonPerson(i, i, "saevi", "male", 0, "fixture") for i in ("self", "other")
    )
    context = Context(
        people,
        (SkeletonRelationship("self", "other", relation, "established", "fixture"),),
        (),
    )
    result = complete_group_relationships(context)
    edge = next(
        e
        for e in result.relationships
        if e.subject_id == "other" and e.object_id == "self"
    )
    assert edge.relation == inverse
    assert edge.label == label
    assert complete_group_relationships(result) == result
