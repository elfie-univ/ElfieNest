"""Replay real Genesis samples into build/ without writing any Elfie workspace."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from elfie.genesis import GenesisCompileInput, GenesisCompiler
from elfie.genesis.compiler import stage_for_age
from elfie.genesis.skeleton_graph import FAMILY_ROLES
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.configuration.world import load_genesis_source_package


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/genesis-skeleton"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = load_genesis_source_package()
    catalog = load_and_configure_species_catalog()
    compiler = GenesisCompiler(source, catalog=catalog)
    cases = [("saevi", a) for a in (2, 3, 5, 8, 10, 11)] + [
        ("tovren", a) for a in (2, 3, 6, 8, 14, 16)
    ]
    cases.append(("saevi", 8))  # Additional natural travel case, input seed 1.
    results = []
    summary = []
    report = [
        "# 实际生成的第三步骨架样本",
        "",
        "使用当前生产 GenesisCompiler，写入 build/，没有创建或修改真实精灵。",
        "时间使用年龄年＋本地日的生成投影，不声称精确生日。公共事件无当前本地年锚点时，单次绝对日期事件记录不可定位。",
        "当前正式候选入口支持 Saevi、Tovren、Myelle；本报告选取前两个物种，幼年期0–1岁不绕过赴地年龄限制生成。",
        "当前配置：本地年196天，学习/工作年度预算98天，照护49天，普通活动参与抽样0.5。效果需要人工审查。",
        "",
        "## 样本总览",
        "",
        "|物种|年龄|阶段|亲属|总人物节点|安排活动|排除活动|第四步实际访问地点|职业|",
        "|---|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    details = []
    for index, (species, age) in enumerate(cases):
        stage = stage_for_age(species, age, catalog)
        seed = 1 if index == len(cases) - 1 else (7, 23)[index % 2]
        request = GenesisCompileInput(
            elfie_id=f"skeleton-{species}-{age}",
            owner_reference="sample-owner",
            display_name="样本主角",
            original_name="样本主角",
            species_id=species,
            gender="female" if index % 2 else "male",
            life_stage=stage,
            age_years_at_adoption=age,
            appearance_seed=seed,
            height="standard",
            build="standard",
            face="soft",
            signature="warm",
            adoption_anchor_at="2026-10-02T00:00:00+00:00",
            reservation_id=f"sample:{species}:{age}",
            idempotency_key=f"sample:{species}:{age}",
        )
        try:
            generated = compiler.compile(request)
        except (ValueError, RuntimeError) as error:
            summary.append({"species": species, "age": age, "blocked": str(error)})
            report.append(f"|{species}|{age}|{stage}|—|—|—|—|—|阻塞：{error}|")
            continue
        skeleton = generated.plan.skeleton
        skeleton.validate_skeleton()
        final = generated.life_context
        states = Counter(a.status for a in skeleton.activities)
        family_ids = {
            "self",
            *(
                r.person_id
                for r in generated.bundle.relationship_seeds
                if r.role in FAMILY_ROLES
            ),
        }
        pair_ids = {(e.subject_id, e.object_id) for e in final.relationships if e.label}
        row = {
            "species": species,
            "age": age,
            "stage": stage,
            "seed": seed,
            "family_relatives": len(family_ids) - 1,
            "people": len(skeleton.people),
            "activities": dict(states),
            "visited": len(final.mobility.visited_place_ids),
            "vocation": final.vocation.vocation_id,
            "groups": len(final.groups),
            "important_friends_expanded": len(final.important_friend_families),
            "important_friend_family_members": sum(
                r.source == "important_friend_family"
                for r in generated.bundle.relationship_seeds
            ),
            "missing_group_pairs": sum(
                (a, b) not in pair_ids
                for g in final.groups
                for a in g.member_ids
                for b in g.member_ids
                if a != b
            ),
            "nonself_edges": sum(
                e.subject_id != "self" and e.object_id != "self"
                for e in final.relationships
            ),
            "public_contact_counts": dict(
                Counter(
                    len(a.participant_ids)
                    for a in final.activities
                    if a.direction == "public" and a.status == "completed"
                )
            ),
        }
        summary.append(row)
        results.append(
            {
                "input": asdict(request),
                "skeleton": asdict(skeleton),
                "resolved_context": asdict(final),
                "person_relation_seeds": [
                    asdict(e) for e in generated.bundle.person_relation_seeds
                ],
                "group_seeds": [asdict(g) for g in generated.bundle.group_seeds],
                "relationship_seeds": [
                    asdict(r) for r in generated.bundle.relationship_seeds
                ],
                "episodes": [asdict(e) for e in generated.bundle.episode_seeds],
                "knowledge": [asdict(k) for k in generated.plan.knowledge_entries],
            }
        )
        report.append(
            f"|{species}|{age}|{stage}|{row['family_relatives']}|{row['people']}|{states['scheduled']}|{states['excluded']}|{row['visited']}|{row['vocation'] or '尚无职业'}|"
        )
        details += [
            "",
            f"## {species} · {age}岁 · 输入种子{seed}",
            "",
            f"出生区域：{skeleton.origin.birth_region_id}；出生公共地点：{skeleton.origin.birth_settlement_id}。",
            "",
            "### 家庭分支（保留冻结算法输出）",
            "",
            "```text",
        ]
        graph = skeleton.family_graph
        groups = [graph.core.origin] + ([graph.core.own] if graph.core.own else [])
        groups += (
            [b.group for b in graph.ancestor_families]
            + [b.group for b in graph.sibling_families]
            + [b.group for b in graph.child_families]
            + [b.group for b in graph.aunt_uncle_families]
            + [b.group for b in skeleton.partner_sibling_families]
        )
        if graph.partner_origin:
            groups.append(graph.partner_origin.group)
        for group in groups:
            union = group.union
            details.append(
                f"{union.union_id}: {union.first.person_id} + {union.second.person_id}；距今{-union.formed_year}年结婚"
            )
            details.extend(
                f"  └─ {c.person_id}，出生距今{-c.birth_year}年" for c in group.children
            )
        details += [
            "```",
            "",
            "### 人物与主角关系",
            "",
            "|人物ID|名字|当前年龄投影|性别|与主角关系|",
            "|---|---|---:|---|---|",
        ]
        roles = {}
        for edge in skeleton.relationships:
            if edge.subject_id == "self":
                roles.setdefault(edge.object_id, []).append(edge.label or edge.relation)
        details.extend(
            f"|{p.person_id}|{p.display_name}|{age - p.birth_age_year if p.birth_age_year is not None else '未知'}|{p.gender}|{', '.join(roles.get(p.person_id, [])) or ('主角' if p.person_id == 'self' else '图中关系')}|"
            for p in skeleton.people
        )
        details += [
            "",
            "### 实际成立的群组",
            "",
            "|群组|类型|成员ID|来源|",
            "|---|---|---|---|",
        ]
        details.extend(
            f"|{g.group_id}|{g.kind}|{', '.join(g.member_ids)}|{g.source_ref}|"
            for g in final.groups
        )
        details += [
            "",
            "### 实际成立的人物间关系",
            "",
            "|人物A|关系|人物B|来源|",
            "|---|---|---|---|",
        ]
        details.extend(
            f"|{e.subject_id}|{e.label} [{e.relation}]|{e.object_id}|{e.source_ref}|"
            for e in final.relationships
            if e.subject_id != "self" and e.object_id != "self"
        )
        details += [
            "",
            "### 生活区间",
            "",
            "|类型|年龄区间（右端不含）|地点|相关人物|年度占用|",
            "|---|---|---|---|---:|",
        ]
        details.extend(
            f"|{s.kind}|{s.start_age_year}–{s.end_age_year}|{s.place_id}|{', '.join(s.participant_ids) or '—'}|{s.days_per_year}天|"
            for s in skeleton.life_segments
        )
        details += [
            "",
            "### 活动与排除结果",
            "",
            "|方向|活动|年龄/本地日|地点|人物|状态/原因|",
            "|---|---|---|---|---|---|",
        ]
        details.extend(
            f"|{a.direction}|{a.purpose} [{a.activity_id}]|{a.age_year}岁 / {a.start_day + 1}–{a.start_day + a.duration_days}|{', '.join(a.place_ids)}|{', '.join(a.participant_ids) or '—'}|{a.status}{': ' + a.reason if a.reason else ''}|"
            for a in skeleton.activities
        )
        details += [
            "",
            "### 地点与知识交接",
            "",
            f"公共和私人地点节点：{len(skeleton.places)}；空间关系：{len(skeleton.place_relations)}；登记路线：{len(skeleton.routes)}。",
            f"骨架知识候选：{len(skeleton.knowledge_nodes)}；第四步实际取得知识：{len(generated.plan.knowledge_entries)}。",
            f"第三步已访问集合：{list(skeleton.mobility.visited_place_ids)}；第四步实际访问：{list(final.mobility.visited_place_ids)}。",
            "",
            "|个人地点|用途|第三步状态|来源|",
            "|---|---|---|---|",
        ]
        details.extend(
            f"|{p.place_id}|{p.purpose}|{p.status}|{p.source_ref}|"
            for p in skeleton.place_links
        )
        details += ["", "其他生成决定：", ""]
        details.extend(
            f"- {d.direction}/{d.object_id}：{d.reason}" for d in skeleton.decisions
        )
    report += details
    (args.output / "samples.json").write_text(
        json.dumps(
            {
                "source_hash": source.manifest.content_sha256,
                "summary": summary,
                "samples": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (args.output / "samples.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
