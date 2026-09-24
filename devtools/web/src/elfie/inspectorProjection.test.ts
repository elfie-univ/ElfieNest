import { describe, expect, it } from "vitest";

import {
  projectAssertionDetail,
  projectEpisodeDetail,
  projectEvidenceDetail,
  projectNodeDetail,
  projectNodeSources,
  projectVisibleNodeProperties,
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
          event_kind: "genesis_personal_episode",
          content_text: "在车站离开迷雾镇。",
          metadata: { place_ids: ["mistyville_waystation"] },
        },
        {
          episode_id: "episode-text-hit",
          event_kind: "genesis_knowledge_episode",
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

  it("把 Episode 原文作为主内容，旧摘要不被当成标题", () => {
    const projected = projectEpisodeDetail({
      episode_id: "episode-1",
      summary_text: "关系说明",
      content_text: "这是一个较长的完整故事正文。",
      event_kind: "interaction",
      occurred_from: "2026-09-23T00:00:00Z",
    }, {
      assertions: [{ assertion_id: "friend", subject_id: "ari", object_node_id: "ena", predicate: "friend_of", evidence_ids: ["ev-1"], importance: .9, confidence: .9 }],
      evidence: [{ evidence_id: "ev-1", source_id: "episode-1", excerpt: "Ari 和 Ena 是朋友。" }],
      nodeById: nodes,
    });

    expect(projected.header.label).toBe("Episode");
    expect(projected.header.summary).toContain("完整故事正文");
    expect(projected.content).toContain("完整故事正文");
    expect(projected.connections.map((item) => item.kind)).toEqual(expect.arrayContaining(["episode", "relation"]));
    expect(projected.sources[0]!.kind).toBe("Evidence");
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
