"""Resolve pairwise relationships from parent and partner facts, never role guesses."""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from typing import TYPE_CHECKING

from .skeleton import SkeletonRelationship

if TYPE_CHECKING:
    from .compiler import LifeContext
    from .skeleton import SkeletonPerson


def _older(subject: SkeletonPerson, other: SkeletonPerson) -> bool | None:
    if subject.birth_age_year is None or other.birth_age_year is None:
        return None
    if subject.birth_age_year == other.birth_age_year:
        return None
    return other.birth_age_year < subject.birth_age_year


def _sibling_name(subject: SkeletonPerson, other: SkeletonPerson) -> str:
    older = _older(subject, other)
    if other.gender == "male":
        return "哥哥" if older is True else "弟弟" if older is False else "兄弟"
    if other.gender == "female":
        return "姐姐" if older is True else "妹妹" if older is False else "姐妹"
    return "兄弟姐妹"


def _biological_label(path: tuple[str, ...], steps: str, people: dict) -> str:
    target = people[path[-1]]
    male = target.gender == "male"
    female = target.gender == "female"
    if steps == "U":
        return "父亲" if male else "母亲" if female else "父母"
    if steps == "D":
        return "儿子" if male else "女儿" if female else "子女"
    if steps == "UU":
        paternal = people[path[1]].gender == "male"
        maternal = people[path[1]].gender == "female"
        if paternal:
            return "爷爷" if male else "奶奶" if female else "祖父母"
        if maternal:
            return "外公" if male else "外婆" if female else "外祖父母"
    if steps == "UD":
        return _sibling_name(people[path[0]], target)
    if steps == "UUD":
        parent = people[path[1]]
        if parent.gender == "male":
            if male:
                older = _older(parent, target)
                return "伯伯" if older is True else "叔叔" if older is False else "伯叔"
            if female:
                return "姑姑"
        if parent.gender == "female":
            return "舅舅" if male else "姨妈" if female else "舅姨"
    if steps == "UDD" and people[path[-2]].gender in {"male", "female"}:
        prefix = "侄" if people[path[-2]].gender == "male" else "外甥"
        return prefix + ("子" if male and prefix == "侄" else "女" if female else "")
    if steps == "DD" and people[path[1]].gender in {"male", "female"}:
        prefix = "孙" if people[path[1]].gender == "male" else "外孙"
        return prefix + ("子" if male else "女" if female else "辈")
    if steps == "UUDD" and all(
        people[ident].gender in {"male", "female"} for ident in (path[1], path[-2])
    ):
        # Only father's brother's children are paternal cousins (堂亲).
        prefix = (
            "堂"
            if people[path[1]].gender == people[path[-2]].gender == "male"
            else "表"
        )
        sibling = _sibling_name(people[path[0]], target)
        return prefix + {"哥哥": "哥", "姐姐": "姐", "弟弟": "弟", "妹妹": "妹"}.get(
            sibling, sibling
        )
    labels = []
    for step, ident in zip(steps, path[1:]):
        p = people[ident]
        labels.append(
            (
                "父亲"
                if p.gender == "male"
                else "母亲"
                if p.gender == "female"
                else "父母"
            )
            if step == "U"
            else (
                "儿子"
                if p.gender == "male"
                else "女儿"
                if p.gender == "female"
                else "子女"
            )
        )
    return "的".join(labels)


def _spouse_label(label: str, gender: str) -> str:
    if gender == "female":
        return {
            "哥哥": "嫂子",
            "弟弟": "弟媳",
            "伯伯": "伯母",
            "叔叔": "婶婶",
            "舅舅": "舅妈",
            "儿子": "儿媳",
        }.get(label, label + "的妻子")
    if gender == "male":
        return {
            "姐姐": "姐夫",
            "妹妹": "妹夫",
            "姑姑": "姑父",
            "姨妈": "姨父",
            "女儿": "女婿",
        }.get(label, label + "的丈夫")
    return label + "的配偶"


class _Resolver:
    def __init__(self, context: LifeContext):
        self.people = {p.person_id: p for p in context.people}
        self.parents = {ident: set() for ident in self.people}
        self.partners = {ident: set() for ident in self.people}
        self.adjacency = {ident: set() for ident in self.people}
        for edge in context.relationships:
            a, b = edge.subject_id, edge.object_id
            if edge.relation == "parent_of":
                self.parents[b].add(a)
                self.adjacency[a].add((b, "D"))
                self.adjacency[b].add((a, "U"))
            elif edge.relation == "partner":
                self.partners[a].add(b)
                self.partners[b].add(a)
                self.adjacency[a].add((b, "S"))
                self.adjacency[b].add((a, "S"))

    def ancestors(self, ident: str) -> dict[str, tuple[str, ...]]:
        result = {ident: (ident,)}
        pending = deque([ident])
        while pending:
            node = pending.popleft()
            for parent in sorted(self.parents[node]):
                if parent not in result and len(result[node]) < 8:
                    result[parent] = (*result[node], parent)
                    pending.append(parent)
        return result

    def biological(self, a: str, b: str):
        left, right = self.ancestors(a), self.ancestors(b)
        common = left.keys() & right.keys()
        if not common:
            return None
        ancestor = min(
            common, key=lambda ident: (len(left[ident]) + len(right[ident]), ident)
        )
        up, down = left[ancestor], right[ancestor]
        path = (*up, *reversed(down[:-1]))
        steps = "U" * (len(up) - 1) + "D" * (len(down) - 1)
        return _biological_label(path, steps, self.people), path

    def resolve(self, a: str, b: str):
        if b in self.partners[a]:
            gender = self.people[b].gender
            return (
                "丈夫"
                if gender == "male"
                else "妻子"
                if gender == "female"
                else "配偶",
                (a, b),
            )
        candidates = []
        for left in (a, *sorted(self.partners[a])):
            for right in (b, *sorted(self.partners[b])):
                result = self.biological(left, right)
                if result is None or left == right:
                    continue
                label, path = result
                if left != a:
                    spouse_gender = self.people[left].gender
                    prefix = (
                        "丈夫"
                        if spouse_gender == "male"
                        else "妻子"
                        if spouse_gender == "female"
                        else "配偶"
                    )
                    label = {
                        ("妻子", "父亲"): "岳父",
                        ("妻子", "母亲"): "岳母",
                        ("丈夫", "父亲"): "公公",
                        ("丈夫", "母亲"): "婆婆",
                    }.get((prefix, label), prefix + "的" + label)
                    path = (a, *path)
                if right != b:
                    label = _spouse_label(label, self.people[b].gender)
                    path = (*path, b)
                if len(set(path)) == len(path):
                    candidates.append(
                        (len(path), int(left != a) + int(right != b), label, path)
                    )
        if candidates:
            _, _, label, path = min(candidates)
            return label, path
        # A longer affinity chain is rendered literally. It does not manufacture
        # siblings by traversing a co-parent's unrelated family.
        pending = deque([(a, (a,), ())])
        while pending:
            node, path, terms = pending.popleft()
            for adjacent, step in sorted(self.adjacency[node]):
                if adjacent in path:
                    continue
                p = self.people[adjacent]
                term = (
                    _biological_label((node, adjacent), step, self.people)
                    if step != "S"
                    else (
                        "丈夫"
                        if p.gender == "male"
                        else "妻子"
                        if p.gender == "female"
                        else "配偶"
                    )
                )
                next_path, next_terms = (*path, adjacent), (*terms, term)
                if adjacent == b:
                    return "的".join(next_terms), next_path
                if len(next_path) < 10:
                    pending.append((adjacent, next_path, next_terms))
        return None


_SOCIAL_LABELS = {
    "friend": "朋友",
    "neighbor": "邻居",
    "teacher": "老师",
    "student": "学生",
    "classmate": "同学",
    "colleague": "同事",
    "acquaintance": "共同活动认识的人",
    "activity_contact": "共同活动认识的人",
}


def complete_group_relationships(context: LifeContext) -> LifeContext:
    """Annotate factual edges and cover every ordered pair in each real group."""
    resolver = _Resolver(context)
    inverse_roles = {
        "friend": "friend",
        "neighbor": "neighbor",
        "colleague": "colleague",
        "classmate": "classmate",
        "teacher": "student",
        "student": "teacher",
    }
    original = list(context.relationships)
    existing = {(e.subject_id, e.object_id, e.relation) for e in original}
    specific_labels = {}
    for edge in context.relationships:
        inverse = inverse_roles.get(edge.relation)
        if inverse is None:
            continue
        specific_labels[(edge.subject_id, edge.object_id)] = _SOCIAL_LABELS[
            edge.relation
        ]
        specific_labels[(edge.object_id, edge.subject_id)] = _SOCIAL_LABELS[inverse]
        key = (edge.object_id, edge.subject_id, inverse)
        if key not in existing:
            original.append(
                replace(
                    edge,
                    subject_id=edge.object_id,
                    object_id=edge.subject_id,
                    relation=inverse,
                    label=_SOCIAL_LABELS[inverse],
                    relationship_path=(edge.object_id, edge.subject_id),
                )
            )
            existing.add(key)
    teacher_pairs = {}
    for group in context.groups:
        if group.kind != "learning":
            continue
        teachers = {
            e.object_id
            for e in context.relationships
            if e.relation == "teacher"
            and e.subject_id in group.member_ids
            and e.object_id in group.member_ids
        }
        for teacher in teachers:
            for member in group.member_ids:
                if member != teacher:
                    teacher_pairs[(member, teacher)] = "teacher"
                    teacher_pairs[(teacher, member)] = "student"
    edges = []
    for edge in original:
        teacher_relation = teacher_pairs.get((edge.subject_id, edge.object_id))
        if teacher_relation and edge.relation in {
            "teacher",
            "student",
            "classmate",
            "acquaintance",
        }:
            edge = replace(edge, relation=teacher_relation)
        result = resolver.resolve(edge.subject_id, edge.object_id)
        label = (
            result[0]
            if result
            else specific_labels.get((edge.subject_id, edge.object_id))
            if edge.relation in {"acquaintance", "activity_contact"}
            and (edge.subject_id, edge.object_id) in specific_labels
            else _SOCIAL_LABELS.get(edge.relation, edge.label or edge.relation)
        )
        path = (
            result[1]
            if result
            else edge.relationship_path or (edge.subject_id, edge.object_id)
        )
        edges.append(replace(edge, label=label, relationship_path=path))
    covered = {(e.subject_id, e.object_id) for e in edges}
    activities = {a.activity_id: a for a in context.activities}
    segments = {s.segment_id: s for s in context.life_segments}
    for group in context.groups:
        if len(set(group.member_ids)) < 3:
            continue
        for a in group.member_ids:
            for b in group.member_ids:
                if a == b or (a, b) in covered:
                    continue
                result = resolver.resolve(a, b) if group.kind == "family" else None
                if group.kind == "family" and result is None:
                    raise ValueError(
                        f"家庭群组缺少血缘或配偶关系路径: {group.group_id}: {a} -> {b}"
                    )
                relation = "kinship"
                status = "established"
                if result:
                    label, path = result
                else:
                    relation = (
                        "classmate"
                        if group.kind == "learning"
                        else "colleague"
                        if group.kind == "work"
                        else "acquaintance"
                    )
                    # Existing teacher edges identify the mentor; inverse edges
                    # and mentor-to-peer edges keep teacher/student semantics.
                    teacher_ids = {
                        e.object_id
                        for e in edges
                        if e.relation == "teacher" and e.subject_id in group.member_ids
                    }
                    if group.kind == "learning" and b in teacher_ids:
                        relation = "teacher"
                    elif group.kind == "learning" and a in teacher_ids:
                        relation = "student"
                    label, path = _SOCIAL_LABELS[relation], (a, b)
                    activity = activities.get(group.source_ref)
                    if activity is not None and activity.status != "completed":
                        status = "contact_slot"
                    elif activity is None:
                        completed = any(
                            a.status == "completed" and group.source_ref in a.depends_on
                            for a in context.activities
                        )
                        if group.source_ref not in segments or not completed:
                            status = "contact_slot"
                edges.append(
                    SkeletonRelationship(
                        a,
                        b,
                        relation,
                        status,
                        group.source_ref,
                        label=label,
                        relationship_path=path,
                    )
                )
                covered.add((a, b))
    return replace(context, relationships=tuple(edges))
