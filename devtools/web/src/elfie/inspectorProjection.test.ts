import { describe, expect, it } from "vitest";

import {
  projectAssertionDetail,
  episodeCardDisplayTitle,
  episodeEventKindLabel,
  episodeMaintenanceLabel,
  projectEpisodeDetail,
  projectEvidenceDetail,
  projectNodeDetail,
  projectNodeSources,
  projectVisibleNodeProperties,
  stripKnowledgeMemberHeaders,
  type InspectorNode,
} from "./inspectorProjection";

const nodes = new Map<string, InspectorNode>([
  ["ari", { id: "ari", label: "Ari", node_type: "elfie", description: "一只喜欢花园的精灵", properties: { species_name: "Saevi", species_id: "saevi", is_self: true, entity_type: "elfie", genesis_submission_id: "secret" }, importance: .9, confidence: .96 }],
  ["ena", { id: "ena", label: "Ena", node_type: "person", properties: { vocation_id: "gardener" }, importance: .6, confidence: .8 }],
]);

const relationInput = {
  nodeById: nodes,
  evidenceById: new Map([["ev-1", { evidence_id: "ev-1", excerpt: "Ari 和 Ena 从小一起玩。" }]]),
  relationKind: (record: Record<string, unknown>) => String(record.predicate ?? "relation"),
  relationLabel: (kind: string) => kind === "friend_of" ? "朋友" : kind,
  relationSentence: (source: string, target: string, kind: string) => kind === "friend_of" ? `${source} 和 ${target} 是朋友` : `${source} → ${target}`,
  nodeTypeLabel: (nodeType: string | undefined) => ({ elfie: "精灵", person: "人物" })[nodeType ?? ""] ?? nodeType ?? "未知类型",
};

describe("Inspector projection", () => {
  it("把 Node 属性按语义字段显示，并把技术元数据留在技术区", () => {
    const projected = projectVisibleNodeProperties(nodes.get("ari")!);

    expect(projected.fields.map((field) => field.label)).toEqual(expect.arrayContaining(["物种", "物种标识", "当前精灵"]));
    expect(projected.fields.some((field) => field.key === "genesis_submission_id")).toBe(false);
    expect(projected.fields.some((field) => field.key === "entity_type")).toBe(false);
    expect(projected.technical.some((field) => field.key === "genesis_submission_id")).toBe(true);
    expect(projected.technical.some((field) => field.key === "entity_type")).toBe(true);
  });

  it("按重要度排序关系，并保留同一对节点的多条关系", () => {
    const projected = projectNodeDetail(nodes.get("ari")!, {
      ...relationInput,
      assertions: [
        { assertion_id: "neighbor", subject_id: "ari", object_node_id: "ena", predicate: "neighbor_of", importance: .3, confidence: .98 },
        { assertion_id: "friend", subject_id: "ari", object_node_id: "ena", predicate: "friend_of", importance: .94, confidence: .97, evidence_ids: ["ev-1"] },
      ],
    });

    expect(projected.connections.map((item) => item.id)).toEqual(["friend", "neighbor"]);
    expect(projected.connections[0]!.detail).toContain("朋友");
    expect(projected.header.semanticType).toBe("精灵");
  });

  it("从地点元数据和 Episode 原文提供可反向打开的故事来源", () => {
    const sources = projectNodeSources(
      {
        id: "mistyville",
        label: "迷雾镇",
        node_type: "place",
        properties: { place_id: "mistyville", aliases: ["Mistyville"] },
      },
      [
        {
          episode_id: "episode-explicit-place",
          event_kind: "life_event",
          content_text: "在车站离开迷雾镇。",
          metadata: { place_ids: ["mistyville_waystation"] },
        },
        {
          episode_id: "episode-text-hit",
          event_kind: "learning",
          content_text: "迷雾镇有一座学习场所。",
          metadata: {},
        },
      ],
    );

    expect(sources.map((source) => source.id)).toEqual([
      "episode-explicit-place",
      "episode-text-hit",
    ]);
    expect(sources[0]!.label).toContain("明确提及");
    expect(sources[1]!.label).toContain("原文命中");
  });

  it("让 Assertion 只显示一次可读关系句，并把 qualifiers 收入技术详情", () => {
    const projected = projectAssertionDetail({
      assertion_id: "friend",
      subject_id: "ari",
      object_node_id: "ena",
      predicate: "friend_of",
      qualifiers: { context: "childhood" },
      evidence_ids: ["ev-1"],
      importance: .94,
      confidence: .97,
    }, relationInput);

    expect(projected.sentence).toBe("Ari 和 Ena 是朋友");
    expect(projected.technical.some((field) => field.key === "qualifiers")).toBe(true);
    expect(projected.sources[0]!.excerpt).toContain("从小一起玩");
  });

  it("优先用摘要作只读标题，正文、类型和整理进度仍完整保留", () => {
    const projected = projectEpisodeDetail({
      episode_id: "episode-1",
      summary_text: "和朋友重新约定分工",
      content_text: "这是一个较长的完整故事正文。",
      event_kind: "conversation",
      occurred_from: "2026-09-23T00:00:00Z",
      occurrence_precision: "range",
      source_refs: [{ source_kind: "conversation", source_id: "chat-1", source_version: "v2" }],
      maintenance: { state: "completed", attempts: 2, updated_at: "2026-09-23T00:00:00Z" },
    }, {
      assertions: [{ assertion_id: "friend", subject_id: "ari", object_node_id: "ena", predicate: "friend_of", evidence_ids: ["ev-1"], importance: .9, confidence: .9 }],
      evidence: [{ evidence_id: "ev-1", source_id: "episode-1", excerpt: "Ari 和 Ena 是朋友。" }],
      nodeById: nodes,
    });

    expect(episodeCardDisplayTitle({ summary_text: "  摘要标题  ", content_text: "正文" })).toBe("摘要标题");
    expect(episodeCardDisplayTitle({ summary_text: " ", content_text: "正文" })).toBe("正文");
    expect(stripKnowledgeMemberHeaders("[B-05 | known | high | documented]\n居民主要在地表生活。\n\n[B-05-02 | known | high | documented]\n深处入口需要许可。"))
      .toBe("居民主要在地表生活。\n\n深处入口需要许可。");
    expect(episodeCardDisplayTitle({ content_text: "[B-05 | known | high | documented]\n居民主要在地表生活。深处入口需要许可。" }))
      .toBe("居民主要在地表生活。");
    expect(episodeCardDisplayTitle({ content_text: "正文".repeat(100) })).toBe(`${"正文".repeat(89)}正…`);
    expect(episodeCardDisplayTitle({ episode_id: "empty", summary_text: "", content_text: "" })).toBe("");
    expect(episodeEventKindLabel("conversation")).toBe("对话交流");
    expect(episodeMaintenanceLabel({ maintenance: { state: "completed" } })).toBe("已整理");
    expect(episodeMaintenanceLabel({})).toBe("进度未记录");
    expect(projected.header.label).toBe("和朋友重新约定分工");
    expect(projected.header.summary).toBe("");
    expect(projected.content).toContain("完整故事正文");
    expect(projected.fields.map((field) => field.label)).toEqual(expect.arrayContaining(["经历类型", "整理进度", "来源", "发生时间"]));
    expect(projected.connections.map((item) => item.kind)).toEqual(expect.arrayContaining(["attribute", "relation"]));
    expect(projected.sources[0]!.kind).toBe("Evidence");
  });

  it("摘要为空时，详情中的摘要槽位保持为空且正文独立保留", () => {
    const projected = projectEpisodeDetail({
      episode_id: "episode-without-summary",
      summary_text: null,
      content_text: "这段经历只有正文，没有生成标题。",
    }, { assertions: [], evidence: [], nodeById: nodes });

    expect(projected.header.label).toBe("这段经历只有正文，没有生成标题。");
    expect(projected.header.summary).toBe("");
    expect(projected.content).toBe("这段经历只有正文，没有生成标题。");
  });

  it("把 Genesis 知识主题桶和选择信息提升到 Episode 语义字段", () => {
    const projected = projectEpisodeDetail({
      episode_id: "knowledge-episode",
      content_text: "完整的知识原文。",
      event_kind: "learning",
      metadata: {
        knowledge_id: "B-03-02",
        topic_bucket: "B-03",
        topic_member_ids: ["B-03-01", "B-03-02", "B-03-03"],
        topic_member_index: 1,
        topic_member_count: 3,
        mastery: "full",
        eligibility: ["居住在森林区域"],
        acquired_via: "source_eligibility",
        acquired_stage: "young_adult",
        acquired_age_years: 4,
        recall_eligible: true,
        initial_confidence: 0.92,
      },
    }, { assertions: [], evidence: [], nodeById: nodes });

    const fields = new Map(projected.fields.map((field) => [field.key, field.value]));
    expect(fields.get("topic_bucket")).toBe("B-03");
    expect(fields.get("topic_member_position")).toBe("2 / 3");
    expect(fields.get("topic_member_ids")).toContain("B-03-01");
    expect(fields.get("mastery")).toBe("full");
    expect(fields.get("eligibility")).toBe("居住在森林区域");
    expect(fields.get("acquired_age_years")).toBe("4");
  });

  it("把 Evidence 首屏定位到摘录和支持 Assertion", () => {
    const projected = projectEvidenceDetail(
      { evidence_id: "ev-1", source_id: "episode-1", excerpt: "Ari 和 Ena 是朋友。", modality: "text" },
      [{ assertion_id: "friend", predicate: "friend_of", evidence_ids: ["ev-1"], importance: .94, confidence: .97 }],
      new Map([["episode-1", { episode_id: "episode-1", summary_text: "关系说明" }]]),
    );

    expect(projected.excerpt).toContain("Ari 和 Ena");
    expect(projected.connections.map((item) => item.label)).toContain("支持 Assertion");
  });
});
