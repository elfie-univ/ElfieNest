import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { MEMORY_DEBUG_GRAPH_CONTROL_TYPE, MemoryDebugLegend, MemoryDebugWorkspacePage, episodeCardTooltip, episodeTraceSourcePoint, filterMemoryDebugEpisodes, formatEpisodeTime, graphLinkArrowLength, graphLinkColor, graphLinkWidth, graphNavigationActive, graphNodeValue, isMemoryDebugSearchMode, isMemoryDebugSemanticNodeType, projectMemoryDebugGraph, recallGraphNodeHitIds, recallGraphProjectionFilters, relationDisplayLabel, relationSentence, selectMemoryNodeGroup, selectMemoryNodeTypes, splitRecallFocusNodes, toggleEpisodeSelection } from "./MemoryDebugWorkspacePage";

const graphOntology = {
  revision: "memory.ontology.v1+registry:0",
  type_groups: [
    { group_id: "social_relations", label: "社会关系", color: "#ff8f6b", order: 1 },
    { group_id: "entities", label: "实体", color: "#7db277", order: 2 },
    { group_id: "space_geography", label: "空间地理", color: "#5bb9ff", order: 3 },
    { group_id: "events", label: "事件", color: "#ffc857", order: 4 },
    { group_id: "general_knowledge", label: "通用知识", color: "#42d6a4", order: 5 },
  ],
  node_types: [
    { node_type: "elfie", label: "精灵", group_id: "social_relations", color: "#ff8f6b", status: "active", count: 4 },
    { node_type: "person", label: "人物", group_id: "social_relations", color: "#b892ff", status: "active", count: 1 },
    { node_type: "group", label: "群体/家庭", group_id: "social_relations", color: "#d5a85f", status: "active", count: 1 },
    { node_type: "object", label: "物体", group_id: "entities", color: "#7db277", status: "active", count: 0 },
    { node_type: "place", label: "地点", group_id: "space_geography", color: "#5bb9ff", status: "active", count: 49 },
    { node_type: "event", label: "事件", group_id: "events", color: "#ffc857", status: "active", count: 0 },
    { node_type: "concept", label: "概念", group_id: "general_knowledge", color: "#42d6a4", status: "active", count: 0 },
    { node_type: "claim", label: "命题", group_id: "general_knowledge", color: "#42d6a4", status: "active", count: 0 },
    { node_type: "candidate_pattern", label: "候选模式", group_id: "general_knowledge", color: "#42d6a4", status: "candidate", count: 1 },
  ],
  predicates: ["friend_of", "located_in", "supports", "prefers", "implies", "parent_of", "child_of", "kin_of", "owned_by", "owner_of"]
    .map((predicate) => ({ predicate, label: predicate === "friend_of" ? "朋友" : predicate, symmetric: predicate === "friend_of" || predicate === "kin_of", inverse: predicate === "parent_of" ? "child_of" : predicate === "child_of" ? "parent_of" : null, status: "active", count: 0 })),
  predicate_aliases: { friend: "friend_of", owner: "owned_by" },
};

function graphReport(data: { nodes: Array<Record<string, unknown>>; assertions: Array<Record<string, unknown>>; evidence: Array<Record<string, unknown>> }): Parameters<typeof projectMemoryDebugGraph>[0] {
  return { ontology: graphOntology, data } as unknown as Parameters<typeof projectMemoryDebugGraph>[0];
}

describe("记忆调试工作台", () => {
  it("要求相机只在按住拖动时旋转，并使用更稳定的 Orbit 控制", () => {
    expect(MEMORY_DEBUG_GRAPH_CONTROL_TYPE).toBe("orbit");
    expect(graphNavigationActive("mouse", 0)).toBe(false);
    expect(graphNavigationActive("mouse", 1)).toBe(true);
    expect(graphNavigationActive("touch", 0)).toBe(true);
  });

  it("展示真实审计页的三个操作入口", () => {
    const markup = renderToStaticMarkup(<MemoryDebugWorkspacePage />);

    expect(markup).toContain("搜索 Node、Assertion、Episode");
    expect(markup).toContain('class="memory-debug-topbar-left"');
    expect(markup).toContain('class="memory-debug-search-group"');
    expect(markup).toContain('class="memory-debug-operation-actions"');
    expect(markup).toContain('class="memory-debug-top-actions"');
    expect(markup).not.toContain("memory-debug-search-clear");
    expect(markup).toContain("筛选");
    expect(markup).not.toContain("memory-debug-search-mode-actions");
    expect(markup).toContain('aria-label="添加 Episode"');
    expect(markup).toContain(">添加</span>");
    expect(markup).toContain('aria-label="手动触发 Consolidation"');
    expect(markup).toContain(">手动整理</span>");
    expect(markup).toContain("anticon-thunderbolt");
    expect(markup).toContain("允许拖拽节点");
    expect(markup).toContain("适配当前图谱");
    expect(markup).not.toContain("名称或描述");
    expect(markup).not.toContain("来源包含");
    expect(markup).not.toContain("memory-debug-brand");
    expect(markup).not.toContain("memory-debug-tabs");
  });

  it("可以从聊天 Trace 打开当前精灵的 Recall 解释链，而不是重新发起检索", () => {
    const markup = renderToStaticMarkup(<MemoryDebugWorkspacePage
      embedded
      elfieId="elfie-current"
      initialRecall={{
        source: "baseline",
        recall_id: "recall-turn-1",
        query: "用户近况",
        returned_ids: { nodes: ["node-1"], assertions: [], episodes: [], evidence: [] },
        selection: { candidate_boundary: "scored_candidates_only", candidates: [], summaries: [] },
      }}
      onClose={() => undefined}
    />);

    expect(markup).toContain("一次 Recall 的解释链");
    expect(markup).toContain('value="用户近况"');
    expect(markup).not.toContain("当前搜索");
    expect(markup).not.toContain("按相关性排序的搜索结果");
    expect(markup).not.toContain("搜索内容");
    expect(markup).not.toContain("再次执行真实检索");
    expect(markup).toContain("Recall 返回摘要");
    expect(markup).toContain('class="memory-debug-search-mode-toggle"');
    expect(markup).toContain('aria-pressed="false" title="只显示本次搜索结果">仅看搜索结果</button>');
    expect(markup).toContain("recall-turn-1");
    expect(markup).toContain("关闭记忆图谱浮窗");
  });

  it("只有左侧检索面板打开时才处于搜索模式", () => {
    expect(isMemoryDebugSearchMode("recall", true)).toBe(true);
    expect(isMemoryDebugSearchMode("recall", false)).toBe(false);
    expect(isMemoryDebugSearchMode("add", true)).toBe(false);
  });

  it("检索默认保留完整图谱，只有明确切换时才投影命中子图", () => {
    const nodeIds = new Set(["hit-node"]);
    const assertionIds = new Set(["hit-edge"]);

    expect(recallGraphProjectionFilters(true, false, nodeIds, assertionIds)).toEqual({});
    expect(recallGraphProjectionFilters(true, true, nodeIds, assertionIds)).toEqual({
      includeNodeIds: nodeIds,
      includeAssertionIds: assertionIds,
    });
    expect(recallGraphProjectionFilters(false, true, nodeIds, assertionIds)).toEqual({});
  });

  it("按回执相关度分开展示命中、零分和未评分节点", () => {
    const groups = splitRecallFocusNodes([
      { id: "context-zero", label: "零分关联项", relevance: 0 },
      { id: "ranked-low", label: "较低命中", relevance: .2 },
      { id: "context-unscored", label: "未评分关联项" },
      { id: "ranked-high", label: "较高命中", relevance: .8 },
    ]);

    expect(groups.ranked.map((node) => node.id)).toEqual(["ranked-high", "ranked-low"]);
    expect(groups.zeroScore.map((node) => node.id)).toEqual(["context-zero"]);
    expect(groups.unscored.map((node) => node.id)).toEqual(["context-unscored"]);
    expect(recallGraphNodeHitIds(new Set(["ranked-high", "context-zero", "context-unscored"]), groups))
      .toEqual(new Set(["ranked-high", "context-unscored"]));
    expect(splitRecallFocusNodes([{ id: "unscored", label: "没有分数的 Recall 返回项" }]))
      .toMatchObject({ ranked: [], zeroScore: [], unscored: [{ id: "unscored" }] });
  });

  it("检索模式下时间带只显示命中的 Episode，不随全图/子图切换扩成全库", () => {
    const episodes = [
      { episode_id: "later", occurred_at: "2026-09-03" },
      { episode_id: "miss", occurred_at: "2026-09-01" },
      { episode_id: "earlier", occurred_at: "2026-09-02" },
    ];

    expect(filterMemoryDebugEpisodes(episodes, "all", new Set(["later", "earlier"]))
      .map((episode) => episode.episode_id)).toEqual(["earlier", "later"]);
    expect(filterMemoryDebugEpisodes(episodes, "all")
      .map((episode) => episode.episode_id)).toEqual(["miss", "earlier", "later"]);
    expect(filterMemoryDebugEpisodes([
      { episode_id: "unknown-time", temporal_label: "before_arrival" },
      { episode_id: "later", occurred_from: "2026-09-03" },
      { episode_id: "earlier", occurred_from: "2026-09-02" },
    ], "all").map((episode) => episode.episode_id)).toEqual(["earlier", "later", "unknown-time"]);
  });

  it("把 Episode 的发生时间转换为可读的时间线标签", () => {
    expect(formatEpisodeTime({ occurred_from: "2026-09-18T14:32:00Z" })).toMatch(/^2026-09-18/);
    expect(formatEpisodeTime({ temporal_label: "抵达前" })).toBe("抵达前（具体时间未记录）");
    expect(formatEpisodeTime({})).toBe("时间未记录");
  });

  it("Episode 悬停提示只显示独立摘要和完整正文", () => {
    const tooltip = episodeCardTooltip({
      episode_id: "episode-card",
      summary_text: "  ",
      content_text: "第一段完整正文。第二段完整正文。",
      event_kind: "conversation",
      attribution: "observed",
      occurrence_precision: "range",
      source_refs: [{ source_kind: "conversation", source_id: "chat-7" }],
      maintenance: { state: "completed", attempts: 1 },
      lifecycle: "archived",
    });

    expect(tooltip).toBe("标题：（空）\n正文：第一段完整正文。第二段完整正文。");
    expect(episodeCardTooltip({ summary_text: "和朋友重新约定分工", content_text: "故事正文" }))
      .toBe("标题：和朋友重新约定分工\n正文：故事正文");
  });

  it("从实际 Episode 卡片边界计算 Evidence 追踪线起点", () => {
    expect(episodeTraceSourcePoint(
      { left: 120, top: 84, width: 180, height: 62 },
      { left: 20, top: 10, width: 1000, height: 800 },
    )).toEqual({ x: 190, y: 136 });
  });

  it("再次点击当前 Episode 时清除选择", () => {
    expect(toggleEpisodeSelection("arrival-nest", "arrival-nest")).toBe("");
    expect(toggleEpisodeSelection("", "arrival-nest")).toBe("arrival-nest");
    expect(toggleEpisodeSelection("arrival-nest", "neighborhood")).toBe("neighborhood");
  });

  it("把有方向的 Assertion 显示成可读关系语义", () => {
    const report = graphReport({ nodes: [], assertions: [], evidence: [] });
    expect(relationDisplayLabel("friend", report)).toBe("朋友");
    expect(relationSentence("Ari", "Ena", "friend", undefined, undefined, report)).toBe("Ari 和 Ena 是朋友");
    expect(relationSentence("Ari", "Kio", "kin_of", undefined, undefined, report)).toBe("Ari 和 Kio 是家人（具体关系未知）");
    expect(relationSentence("Ari", "Ena", "parent_of", undefined, undefined, report)).toBe("Ari 是 Ena 的父母");
    expect(relationSentence("精灵", "主人", "owner", "elfie", "person", report)).toBe("主人 是 精灵 的主人");

    const graph = projectMemoryDebugGraph(graphReport({
        nodes: [
          { id: "ari", node_type: "elfie", label: "Ari" },
          { id: "ena", node_type: "elfie", label: "Ena" },
        ],
        assertions: [{ assertion_id: "friend-1", subject_id: "ari", object_node_id: "ena", predicate: "friend", evidence_ids: ["evidence-friend"] }],
        evidence: [{ evidence_id: "evidence-friend" }],
      }));
    expect(graph.edges[0]).toMatchObject({ label: "朋友", predicate: "friend_of", symmetric: true });
  });

  it("不把历史 Genesis 提交回执投影成记忆图节点", () => {
    const report = graphReport({
        nodes: [
          { id: "genesis:receipt:elfie-a", node_type: "genesis_commit_receipt", label: "初始化回执" },
          { id: "person-a", node_type: "person", label: "家人" },
        ],
        assertions: [],
        evidence: [],
      });
    expect(isMemoryDebugSemanticNodeType("genesis_commit_receipt", report)).toBe(false);
    const graph = projectMemoryDebugGraph(report);

    expect(graph.nodes.map((node) => node.id)).toEqual(["person-a"]);
  });

  it("把高亮上下文之外的 Assertion 箭头和连线一起降为不可见灰态", () => {
    expect(graphLinkArrowLength(true, "", "unrelated", "assertion", false, false)).toBe(0);
    expect(graphLinkColor(true, "", "unrelated", "assertion", false, false)).toBe("rgba(107, 133, 151, 0.16)");
    expect(graphLinkArrowLength(true, "", "affected", "assertion", false, true)).toBe(4);
    expect(graphLinkArrowLength(true, "selected", "selected", "assertion", false, false)).toBe(4);
  });

  it("只用重要度决定节点大小和关系线宽", () => {
    expect(graphNodeValue(.8)).toBe(graphNodeValue(.8));
    expect(graphNodeValue(.8)).toBeGreaterThan(graphNodeValue(.2));
    expect(graphLinkWidth(.8)).toBeGreaterThan(graphLinkWidth(.2));
    expect(graphLinkWidth(undefined)).toBe(graphLinkWidth(.5));

    const graph = projectMemoryDebugGraph(graphReport({
        nodes: [{ id: "a", node_type: "person", label: "甲" }, { id: "b", node_type: "person", label: "乙" }],
        assertions: [{ assertion_id: "relation-1", subject_id: "a", object_node_id: "b", predicate: "friend_of", importance: .82, evidence_ids: ["ev-1"] }],
        evidence: [{ evidence_id: "ev-1" }],
      }));

    expect(graph.edges[0]).toMatchObject({ importance: .82 });
  });

  it("图例展示实际存在的叶节点类型及其类型色，不把类型组当成节点类型", () => {
    const markup = renderToStaticMarkup(<MemoryDebugLegend layoutLocked ontology={graphOntology} />);

    expect(markup).not.toContain('class="memory-debug-3d-hint"');
    expect(markup).toContain('memory-debug-legend-hint');
    expect(markup).toContain('<span class="episode-key">Episode</span>');
    expect(markup).toContain("精灵");
    expect(markup).toContain("人物");
    expect(markup).toContain("群体/家庭");
    expect(markup).toContain("地点");
    expect(markup).toContain('style="color:#ff8f6b"');
    expect(markup).not.toContain("社会关系");
    expect(markup).not.toContain("通用知识");
    expect(markup).not.toContain("事件");
    expect(markup).not.toContain("概念");
    expect(markup).not.toContain("候选模式");
    expect(markup).not.toContain("自我模型");
    expect(markup).toContain("点大小=重要度 · 关系线宽=重要度");
  });

  it("使用独立 CSS 命名空间，不污染 legacy memory-audit selectors", () => {
    const markup = renderToStaticMarkup(<MemoryDebugWorkspacePage />);

    expect(markup).toContain('class="memory-debug-page"');
    expect(markup).not.toContain("memory-audit-page");
  });

  it("把 literal Assertion 映射为可点击的字面值端点，并保留 Evidence 关联", () => {
    const report = graphReport({
        nodes: [{ id: "elfie", node_type: "elfie", label: "艾菲" }],
        assertions: [{
          assertion_id: "assertion-literal",
          subject_id: "elfie",
          object_literal: "喜欢散步",
          predicate: "prefers",
          evidence_ids: ["evidence-literal"],
        }],
        evidence: [{ evidence_id: "evidence-literal" }],
      });

    const graph = projectMemoryDebugGraph(report);

    expect(graph.nodes).toContainEqual({ id: "literal:assertion-literal", kind: "literal", label: "喜欢散步" });
    expect(graph.edges).toContainEqual(expect.objectContaining({
      id: "assertion-literal",
      source: "elfie",
      target: "literal:assertion-literal",
      evidenceIds: ["evidence-literal"],
    }));
    expect(graph.nodes.some((node) => node.id === "evidence-literal")).toBe(false);
  });

  it("按真实 ID 排序图投影，保证分页合并后的布局稳定", () => {
    const report = graphReport({
        nodes: [
          { id: "node-z", node_type: "concept", label: "Z" },
          { id: "node-a", node_type: "concept", label: "A" },
        ],
        assertions: [],
        evidence: [],
      });

    const projected = projectMemoryDebugGraph(report);
    expect(projected.nodes.map((node) => node.id)).toEqual(["node-a", "node-z"]);
    expect(projected.nodes[0]).toMatchObject({ typeLabel: "概念", color: "#42d6a4" });
  });

  it("组合应用生命周期和置信度筛选，不把 Evidence 伪装成节点", () => {
    const report = graphReport({
        nodes: [
          { id: "node-a", node_type: "concept", label: "A", confidence: .92, properties: { status: "active", source_id: "seed-1" } },
          { id: "node-b", node_type: "concept", label: "B", confidence: .84, properties: { status: "active", source_id: "seed-1" } },
          { id: "node-c", node_type: "concept", label: "C", confidence: .95, properties: { status: "archived", source_id: "other" } },
        ],
        assertions: [
          { assertion_id: "assertion-keep", subject_id: "node-a", object_node_id: "node-b", predicate: "supports", confidence: .88, evidence_ids: ["evidence-1"] },
          { assertion_id: "assertion-low", subject_id: "node-a", object_node_id: "node-b", predicate: "friend_of", confidence: .3, evidence_ids: ["evidence-1"] },
        ],
        evidence: [{ evidence_id: "evidence-1" }],
      });

    const graph = projectMemoryDebugGraph(report, { lifecycle: "active", minConfidence: .8 });

    expect(graph.nodes.map((node) => node.id)).toEqual(["node-a", "node-b"]);
    expect(graph.edges.map((edge) => edge.id)).toEqual(["assertion-keep"]);
  });

  it("按枚举关系类型过滤 Assertion 边", () => {
    const report = graphReport({
        nodes: [
          { id: "node-a", node_type: "person", label: "甲" },
          { id: "node-b", node_type: "person", label: "乙" },
        ],
        assertions: [
          { assertion_id: "assertion-friend", subject_id: "node-a", object_node_id: "node-b", predicate: "friend_of", evidence_ids: ["ev-1"] },
          { assertion_id: "assertion-supports", subject_id: "node-a", object_node_id: "node-b", predicate: "supports", evidence_ids: ["ev-1"] },
        ],
        evidence: [{ evidence_id: "ev-1" }],
      });

    const graph = projectMemoryDebugGraph(report, { predicateTypes: new Set(["friend_of"]) });

    expect(graph.nodes.map((node) => node.id)).toEqual(["node-a", "node-b"]);
    expect(graph.edges.map((edge) => edge.id)).toEqual(["assertion-friend"]);
  });

  it("不把旧的 about/knows 边重新显示成语义关系", () => {
    const graph = projectMemoryDebugGraph(graphReport({
        nodes: [{ id: "self", node_type: "elfie", label: "艾菲" }, { id: "knowledge", node_type: "concept", label: "规律" }],
        assertions: [{ assertion_id: "legacy-about", subject_id: "self", object_node_id: "knowledge", predicate: "about", evidence_ids: ["ev-1"] }],
        evidence: [],
      }));

    expect(graph.edges).toEqual([]);
  });

  it("支持在同一个过滤面板中组合多个节点类型", () => {
    const report = graphReport({
        nodes: [
          { id: "person-1", node_type: "person", label: "甲" },
          { id: "person-2", node_type: "person", label: "乙" },
          { id: "place-1", node_type: "place", label: "地点" },
        ],
        assertions: [
          { assertion_id: "person-place", subject_id: "person-1", object_node_id: "place-1", predicate: "located_in", evidence_ids: ["ev-1"] },
          { assertion_id: "person-person", subject_id: "person-1", object_node_id: "person-2", predicate: "friend_of", evidence_ids: ["ev-1"] },
        ],
        evidence: [{ evidence_id: "ev-1" }],
      });

    const graph = projectMemoryDebugGraph(report, { nodeTypes: new Set(["person", "place"]) });

    expect(graph.nodes.map((node) => node.id)).toEqual(["person-1", "person-2", "place-1"]);
    expect(graph.edges.map((edge) => edge.id)).toEqual(["person-person", "person-place"]);
  });

  it("类型组和节点类型联动，筛选只改变图节点并按端点重投影边", () => {
    const nodeTypes = graphOntology.node_types;
    expect(selectMemoryNodeGroup("space_geography", ["person"], nodeTypes)).toEqual({
      groupId: "space_geography",
      nodeTypes: [],
    });
    expect(selectMemoryNodeTypes(["person"], "", nodeTypes)).toEqual({
      groupId: "social_relations",
      nodeTypes: ["person"],
    });
    expect(selectMemoryNodeTypes([], "social_relations", nodeTypes)).toEqual({
      groupId: "social_relations",
      nodeTypes: [],
    });

    const report = graphReport({
      nodes: [
        { id: "person-1", node_type: "person", label: "甲" },
        { id: "person-2", node_type: "person", label: "乙" },
        { id: "place-1", node_type: "place", label: "地点" },
      ],
      assertions: [
        { assertion_id: "person-place", subject_id: "person-1", object_node_id: "place-1", predicate: "located_in", evidence_ids: ["ev-1"] },
        { assertion_id: "person-person", subject_id: "person-1", object_node_id: "person-2", predicate: "friend_of", evidence_ids: ["ev-1"] },
      ],
      evidence: [{ evidence_id: "ev-1" }],
    });
    const projected = projectMemoryDebugGraph(report, { nodeGroup: "social_relations" });
    expect(projected.nodes.map((node) => node.id)).toEqual(["person-1", "person-2"]);
    expect(projected.edges.map((edge) => edge.id)).toEqual(["person-person"]);
  });
});
