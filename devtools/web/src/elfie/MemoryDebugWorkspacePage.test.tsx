import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { GRAPH_SELECTED_LINK_COLOR, MEMORY_DEBUG_GRAPH_ARROW_REL_POS, MEMORY_DEBUG_GRAPH_CONTROL_TYPE, MEMORY_DEBUG_GRAPH_FIT_PADDING, MemoryDebugLegend, MemoryNodeFilter, MemoryDebugWorkspacePage, RECALL_PROCESS_LABELS, buildRecallDisplayResults, buildRecallObjectTree, buildRecallRequestPayload, countRecallDisplayResults, episodeCardTooltip, episodeTraceSourcePoint, filterMemoryDebugEpisodes, filterRecallDisplayResults, formatEpisodeTime, formatRecallElapsed, graphFitCameraTarget, graphLinkArrowLength, graphLinkColor, graphLinkIsContextual, graphLinkWidth, graphNavigationActive, graphNodeHighlightKind, graphNodeLabelMaterialOptions, graphNodeValue, graphVisibleLabelIds, isMemoryDebugSearchMode, isMemoryDebugSemanticNodeType, memoryDebugRecallProjectionKey, memoryNodeGroupOptions, memoryRecallDateBounds, projectMemoryDebugGraph, recallExclusionLabel, recallFiltersFromObjectSelection, recallGraphNodeHitIds, recallGraphProjectionFilters, recallRouteLabel, recallRouteStatusLabel, relationDisplayLabel, relationSentence, selectMemoryNodeGroup, selectMemoryNodeTypes, splitRecallFocusNodes, toggleEpisodeSelection } from "./MemoryDebugWorkspacePage";

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
    .map((predicate) => ({ predicate, label: predicate === "friend_of" ? "朋友" : predicate, self_stance: predicate === "prefers", symmetric: predicate === "friend_of" || predicate === "kin_of", inverse: predicate === "parent_of" ? "child_of" : predicate === "child_of" ? "parent_of" : null, status: "active", count: 0 })),
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

  it("让节点标签和关系箭头走图谱库的原生深度与箭头路径", () => {
    expect(graphNodeLabelMaterialOptions()).toEqual({ transparent: true, depthWrite: false, depthTest: false, opacity: .94 });
    expect(MEMORY_DEBUG_GRAPH_ARROW_REL_POS).toBe(.95);
    expect(graphLinkArrowLength(true, "", "relation", "assertion", false, false)).toBe(10);
  });

  it("被前方节点覆盖时整体隐藏后方标签，而不是把文字切成半截", () => {
    const visible = graphVisibleLabelIds([
      { id: "front", depth: 4, center: { x: 100, y: 100 }, radius: 42 },
      { id: "rear", depth: 8, center: { x: 100, y: 100 }, radius: 12, label: { left: 80, right: 120, top: 92, bottom: 108 } },
      { id: "clear", depth: 8, center: { x: 260, y: 100 }, radius: 12, label: { left: 240, right: 280, top: 92, bottom: 108 } },
    ]);

    expect(visible.has("rear")).toBe(false);
    expect(visible.has("clear")).toBe(true);
  });

  it("初始化适配完整图谱并保留足够边距", () => {
    expect(MEMORY_DEBUG_GRAPH_FIT_PADDING).toBeGreaterThan(36);
  });

  it("适配时以图谱边界中心为相机目标，不受面板布局影响", () => {
    const fit = graphFitCameraTarget(
      { x: [100, 140], y: [-20, 20], z: [40, 80] },
      { x: 180, y: 60, z: 120 },
      25,
      2,
      800,
      MEMORY_DEBUG_GRAPH_FIT_PADDING,
    );

    expect(fit?.target).toEqual({ x: 120, y: 0, z: 60 });
    expect(fit?.distance).toBeGreaterThan(0);

    expect(graphFitCameraTarget(
      { x: [1, 1], y: [2, 2], z: [3, 3] },
      { x: 0, y: 0, z: 10 },
      25,
      1,
      800,
      MEMORY_DEBUG_GRAPH_FIT_PADDING,
    )?.target).toEqual({ x: 1, y: 2, z: 3 });
  });

  it("全图搜索只更新高亮，不改变底层图谱投影", () => {
    const nodeIds = new Set(["node-b", "node-a"]);
    const assertionNodeIds = new Set(["node-c"]);
    const assertionIds = new Set(["assertion-2", "assertion-1"]);

    expect(memoryDebugRecallProjectionKey(false, "recall-1", nodeIds, assertionNodeIds, assertionIds)).toBe("");
    expect(memoryDebugRecallProjectionKey(true, "recall-1", nodeIds, assertionNodeIds, assertionIds))
      .toBe(memoryDebugRecallProjectionKey(true, "recall-1", new Set(["node-a", "node-b"]), assertionNodeIds, new Set(["assertion-1", "assertion-2"])));
  });

  it("展示真实审计页的三个操作入口", () => {
    const markup = renderToStaticMarkup(<MemoryDebugWorkspacePage />);

    expect(markup).toContain("搜索 Node、Assertion、Episode");
    expect(markup).toContain('class="memory-debug-topbar-left"');
    expect(markup).toContain('class="memory-debug-search-group"');
    expect(markup).toContain('class="memory-debug-operation-actions"');
    expect(markup).toContain('class="memory-debug-top-actions"');
    expect(markup).not.toContain("memory-debug-search-clear");
    expect(markup).toContain(">高级");
    expect(markup).not.toContain("高级搜索");
    expect(markup).not.toContain("搜索选项");
    expect(markup).toContain("anticon-down");
    expect(markup).not.toContain("anticon-sliders");
    expect(markup).not.toContain("anticon-filter");
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

    expect(markup).toContain('<span aria-hidden="true">↓</span> 查看详情');
    expect(markup).toContain('value="用户近况"');
    expect(markup).not.toContain("当前搜索");
    expect(markup).not.toContain("按相关性排序的搜索结果");
    expect(markup).not.toContain("搜索内容");
    expect(markup).not.toContain("再次执行真实检索");
    expect(markup).toContain('class="memory-debug-drawer-count"');
    expect(markup).not.toContain("MEMORY · WORKSPACE");
    expect(markup).toContain('<span aria-hidden="true">↓</span> 查看详情');
    expect(markup).toContain('<span aria-hidden="true">→</span> 查看结果');
    expect(markup).not.toContain("memory-debug-recall-result-summary");
    expect(markup).toContain('class="memory-debug-search-mode-toggle"');
    expect(markup).toContain('aria-pressed="false"><span aria-hidden="true">→</span> 查看结果</button>');
    expect(markup).toContain("recall-turn-1");
    expect(markup).toContain("关闭记忆图谱浮窗");
  });

  it("搜索详情保留全局五步流水线顺序", () => {
    expect(RECALL_PROCESS_LABELS).toEqual(["搜索（三路）", "合并、去重", "过滤", "排序", "结果关联与输出"]);
  });

  it("把三路搜索的执行状态和候选数量压缩成 Tab 状态", () => {
    expect(recallRouteStatusLabel(true, 10)).toBe("已执行 · 10 条候选");
    expect(recallRouteStatusLabel(false, 0)).toBe("未执行 · 0 条候选");
  });

  it("把 Recall 总耗时格式化为左侧面板可读的指标", () => {
    expect(formatRecallElapsed(26.701)).toBe("26.70 ms");
    expect(formatRecallElapsed(1200)).toBe("1.20 s");
    expect(formatRecallElapsed(null)).toBe("未记录");
  });

  it("把 Recall 候选淘汰原因转换成可读说明", () => {
    expect(recallExclusionLabel("score_below_floor")).toBe("低于相关度门槛");
    expect(recallExclusionLabel("ranked_out_of_top_k")).toBe("排序后超出 Top-K");
    expect(recallExclusionLabel("other_reason")).toBe("other_reason");
    expect(recallExclusionLabel(null)).toBe("原因未观测");
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

  it("统一排列 Recall 返回的节点、经历和关系，并只给有来源证据的候选标记路径", () => {
    const results = buildRecallDisplayResults({
      focus_nodes: [
        { id: "node-high", label: "高相关节点", node_type: "person", relevance: .8, role: "primary" },
        { id: "node-support", label: "关联节点", node_type: "place", relevance: 0, role: "support" },
      ],
      assertions: [{ assertion_id: "assertion-top", subject_id: "node-high", predicate: "located_in", object_node_id: "node-support", evidence_ids: ["evidence-1"], relevance: .95, role: "primary" }],
      episodes: [{ episode_id: "episode-middle", excerpt: "花园散步。完整的来源正文仍保留。", summary_text: "花园散步", relevance: .7, role: "primary" }],
      evidence: [{ evidence_id: "evidence-1", source_id: "assertion-top", excerpt: "来源摘录" }],
    } as unknown as Parameters<typeof buildRecallDisplayResults>[0], [
      { candidate_id: "assertion-top", candidate_kind: "assertion", score: .95, matched_terms: ["花园"], kept: true, source: "lexical" },
    ]);

    expect(results.map((item) => item.id)).toEqual(["assertion-top", "node-high", "episode-middle", "node-support"]);
    expect(results[0]?.related).toEqual(["来源摘录"]);
    expect(results[0]?.relevance).toBeCloseTo(.95);
    expect(results[0]?.candidate?.matched_terms).toEqual(["花园"]);
    expect(results.find((item) => item.id === "episode-middle")?.title).toBe("花园散步");
    expect(results.find((item) => item.id === "node-support")?.summary).toBe("");
    expect(results.find((item) => item.id === "assertion-top")?.summary).toBe("");
    expect(results.find((item) => item.id === "episode-middle")?.summary).toBe("完整的来源正文仍保留。");
    expect(countRecallDisplayResults(results)).toEqual({ all: 4, node: 2, episode: 1, assertion: 1 });
    expect(filterRecallDisplayResults(results, "node").map((item) => item.id)).toEqual(["node-high", "node-support"]);
    expect(recallRouteLabel(results[0]?.candidate?.source)).toBe("Query · 文本");
    expect(recallRouteLabel(null, "support")).toBe("关联上下文");
  });

  it("把高级面板的硬过滤条件原样映射到 Recall 请求", () => {
    expect(buildRecallRequestPayload("  公园里的经历  ", "elfie-1", {
      recordKinds: ["episode", "assertion"],
      nodeTypes: ["person"],
      relationTypes: ["located_in"],
      occurredFrom: "2026-09-01",
      occurredTo: "2026-09-30",
      minimumImportance: .5,
    })).toEqual({
      query: "公园里的经历",
      limit: 8,
      elfie_id: "elfie-1",
      record_kinds: ["episode", "assertion"],
      node_types: ["person"],
      relation_types: ["located_in"],
      occurred_from: "2026-09-01",
      occurred_to: "2026-09-30T23:59:59.999999",
      minimum_importance: .5,
    });
  });

  it("空文本时把地点和情绪作为结构化场景传入，不拼接 Query", () => {
    expect(buildRecallRequestPayload("  ", undefined, {
      recordKinds: [], nodeTypes: [], relationTypes: [],
      occurredFrom: "", occurredTo: "", minimumImportance: null,
      placeNodeId: "place-1",
      sense: { emotion_label: "happiness", intensity: .6 },
    })).toEqual({ query: "", limit: 8, place_node_ids: ["place-1"],
      sense: { emotion_label: "happiness", intensity: .6 } });
  });

  it("不把未接入的场景线索悄悄拼进文本 Query", () => {
    expect(buildRecallRequestPayload("  一段场景描述  ", undefined, {
      recordKinds: [],
      nodeTypes: [],
      relationTypes: [],
      occurredFrom: "",
      occurredTo: "",
      minimumImportance: null,
    })).toEqual({ query: "一段场景描述", limit: 8 });
  });

  it("时间范围以最早的已记录发生时间为下界，并限制在今天", () => {
    expect(memoryRecallDateBounds([
      { occurred_from: "2025-02-03T08:30:00Z", occurred_to: "2025-02-05" },
      { occurred_at: "2024-12-19T20:00:00Z" },
      { occurred_from: "2030-01-01T00:00:00Z" },
      { temporal_label: "幼年时期" },
    ], new Date("2026-09-27T12:00:00Z"))).toEqual({ from: "2024-12-19", to: "2026-09-27" });
    expect(memoryRecallDateBounds([], new Date("2026-09-27T12:00:00Z"))).toEqual({ from: "2026-09-27", to: "2026-09-27" });
  });

  it("把对象多级树选择转换成 Recall 的类型硬过滤", () => {
    expect(recallFiltersFromObjectSelection(["kind:episode", "slice:entities", "relation:friend_of"], graphOntology)).toEqual({
      recordKinds: ["episode", "node", "assertion"],
      nodeTypes: ["object"],
      relationTypes: ["friend_of"],
    });
    expect(recallFiltersFromObjectSelection(["kind:node"], graphOntology)).toEqual({
      recordKinds: ["node"],
      nodeTypes: [],
      relationTypes: [],
    });
  });

  it("对象树只列出当前有效本体类型，并明确自我模型暂不可作为 Recall 过滤项", () => {
    const tree = buildRecallObjectTree(graphOntology);
    const nodeRoot = tree.find((item) => item.value === "kind:node");
    const selfModel = nodeRoot?.children?.find((item) => item.value === "slice:self_model");
    const knowledgeSlice = nodeRoot?.children?.find((item) => item.value === "slice:general_knowledge");

    expect(tree.map((item) => item.value)).toEqual(["kind:episode", "kind:node", "kind:assertion"]);
    expect(selfModel).toMatchObject({ disableCheckbox: true, selectable: false });
    expect(knowledgeSlice?.children?.map((item) => item.value)).toEqual(["node:concept", "node:claim"]);
    expect(knowledgeSlice?.children?.some((item) => item.value === "node:candidate_pattern")).toBe(false);
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

    expect(tooltip).toBe("标题：第一段完整正文。\n正文：第一段完整正文。第二段完整正文。");
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
    expect(graph.edges[0]).toMatchObject({ label: "朋友", predicate: "friend_of", symmetric: true, direction: "both", assertionIds: ["friend-1"] });
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

  it("把高亮上下文之外的 Assertion 箭头和连线一起保留为弱化灰态", () => {
    expect(MEMORY_DEBUG_GRAPH_ARROW_REL_POS).toBe(0.95);
    expect(graphLinkArrowLength(true, "", "unrelated", "assertion", false, false)).toBe(10);
    expect(graphLinkColor(true, "", "unrelated", "assertion", false, false)).toBe("rgba(107, 133, 151, 0.16)");
    expect(graphLinkArrowLength(true, "", "affected", "assertion", false, true)).toBe(10);
    expect(graphLinkArrowLength(true, "selected", "selected", "assertion", false, false)).toBe(10);
    expect(graphLinkArrowLength(true, "selected", "selected", "assertion", false, false)).toBeGreaterThan(2 * graphLinkWidth(1));
  });

  it("把选中态与搜索背景态分开，单独选中关系不会压暗其他关系", () => {
    expect(graphLinkIsContextual(false, "selected", "unrelated", false, false)).toBe(true);
    expect(graphLinkColor(false, "selected", "unrelated", "assertion", false, false)).toBe("#5e9fbb");
    expect(graphLinkColor(true, "selected", "unrelated", "assertion", false, false)).toBe("rgba(107, 133, 151, 0.16)");
  });

  it("把明确选中的关系提升为独立高亮层", () => {
    expect(graphLinkColor(true, "selected", "selected", "assertion", false, false)).toBe(GRAPH_SELECTED_LINK_COLOR);
    expect(graphLinkColor(true, "selected", "returned", "assertion", true, false)).toBe("#5e9fbb");
  });

  it("选中节点或关系端点使用外圈状态而不是替换节点语义色", () => {
    expect(graphNodeHighlightKind(true, false, false, false)).toBe("selected");
    expect(graphNodeHighlightKind(false, true, false, false)).toBe("selected");
    expect(graphNodeHighlightKind(false, false, true, false)).toBe("none");
    expect(graphNodeHighlightKind(false, false, false, false)).toBe("none");
  });

  it("只用重要度决定节点大小和关系线宽", () => {
    expect(graphNodeValue(.8)).toBe(graphNodeValue(.8));
    expect(graphNodeValue(.8)).toBeGreaterThan(graphNodeValue(.2));
    expect(graphNodeValue(0)).toBeCloseTo((3.6 / 3.1) ** 3);
    expect(graphNodeValue(1)).toBeCloseTo((7.2 / 3.1) ** 3);
    expect(graphLinkWidth(.8)).toBeGreaterThan(graphLinkWidth(.2));
    expect(graphLinkWidth(undefined)).toBe(graphLinkWidth(.5));
    expect(graphLinkWidth(0)).toBeCloseTo(.55);
    expect(graphLinkWidth(1)).toBeCloseTo(2.4);

    const graph = projectMemoryDebugGraph(graphReport({
        nodes: [{ id: "a", node_type: "person", label: "甲" }, { id: "b", node_type: "person", label: "乙" }],
        assertions: [{ assertion_id: "relation-1", subject_id: "a", object_node_id: "b", predicate: "friend_of", importance: .82, evidence_ids: ["ev-1"] }],
        evidence: [{ evidence_id: "ev-1" }],
      }));

    expect(graph.edges[0]).toMatchObject({ importance: .82, direction: "both", assertionIds: ["relation-1"] });
  });

  it("把同一对节点的多条有向 Assertion 合并成一根线，并取最大重要度", () => {
    const graph = projectMemoryDebugGraph(graphReport({
      nodes: [{ id: "a", node_type: "person", label: "甲" }, { id: "b", node_type: "person", label: "乙" }],
      assertions: [
        { assertion_id: "parent", subject_id: "a", object_node_id: "b", predicate: "parent_of", importance: .84, evidence_ids: ["ev-parent"] },
        { assertion_id: "child", subject_id: "b", object_node_id: "a", predicate: "child_of", importance: .92, evidence_ids: ["ev-child"] },
        { assertion_id: "supports", subject_id: "a", object_node_id: "b", predicate: "supports", importance: .38, evidence_ids: ["ev-supports"] },
      ],
      evidence: [{ evidence_id: "ev-parent" }, { evidence_id: "ev-child" }, { evidence_id: "ev-supports" }],
    }));

    expect(graph.edges).toHaveLength(1);
    expect(graph.edges[0]).toMatchObject({
      id: "relation:a::b",
      source: "a",
      target: "b",
      direction: "both",
      importance: .92,
      assertionIds: ["child", "parent", "supports"],
      evidenceIds: ["ev-child", "ev-parent", "ev-supports"],
    });
  });

  it("图例只保留重要度和按需出现的来源说明", () => {
    const markup = renderToStaticMarkup(<MemoryDebugLegend layoutLocked />);
    expect(markup).toContain("节点越大越重要，线越粗越重要");
    expect(markup).toContain("按住左键拖动画布旋转 · 滚轮缩放");
    expect(markup).toContain("点击节点/关系查看右侧详情");
    expect(markup).not.toContain("episode-key");
    expect(markup).not.toContain("evidence-key");
    expect(renderToStaticMarkup(<MemoryDebugLegend showSources />)).toContain("虚线：Episode 来源关联");
  });

  it("自我模型先选立场边，再保留邻域内部边，不递归扩展", () => {
    const report = graphReport({
      nodes: [
        { id: "self", node_type: "elfie", label: "我", properties: { is_self: true } },
        ...["a", "b", "outside"].map(id => ({ id, node_type: "person", label: id })),
      ],
      assertions: [
        { assertion_id: "stance", subject_id: "self", object_node_id: "a", predicate: "prefers", evidence_ids: ["ev"] },
        { assertion_id: "internal", subject_id: "a", object_node_id: "self", predicate: "friend_of", evidence_ids: ["ev"] },
        { assertion_id: "expand", subject_id: "a", object_node_id: "b", predicate: "prefers", evidence_ids: ["ev"] },
        { assertion_id: "ordinary", subject_id: "self", object_node_id: "outside", predicate: "friend_of", evidence_ids: ["ev"] },
      ], evidence: [{ evidence_id: "ev" }],
    });
    const graph = projectMemoryDebugGraph(report, { nodeGroup: "self_model" });
    expect(graph.nodes.map(node => node.id)).toEqual(["a", "self"]);
    expect(graph.edges.map(edge => edge.id)).toEqual(["relation:a::self"]);
    expect(graph.edges[0]).toMatchObject({ direction: "both", assertionIds: ["internal", "stance"] });
  });

  it("全部组展示包括零数量在内的所有活动类型", () => {
    const markup = renderToStaticMarkup(<MemoryNodeFilter ontology={graphOntology} group="" selectedTypes={[]} onGroupChange={() => {}} onTypesChange={() => {}} />);
    expect(markup.indexOf("地点</button>")).toBeLessThan(markup.indexOf("精灵</button>"));
    expect(markup).toContain("概念");
    expect(markup).toContain("命题");
    expect(markup).not.toContain("更多类型");
    expect(markup).not.toContain("候选模式");
  });

  it("快捷类型组选项不生成重复的原生 title 提示", () => {
    const options = memoryNodeGroupOptions(graphOntology);

    expect(options.map(option => option.label)).toEqual(["全部", "社会关系", "实体", "空间地理", "事件", "通用知识", "自我模型"]);
    expect(options.every(option => option.title === "")).toBe(true);
  });

  it("快捷类型栏不显示计数，自我模型只显示全部", () => {
    const markup = renderToStaticMarkup(<MemoryNodeFilter ontology={graphOntology} group="self_model" selectedTypes={[]} onGroupChange={() => {}} onTypesChange={() => {}} />);
    expect(markup).toContain("自我模型");
    expect(markup).toContain('aria-pressed="true"');
    expect(markup).not.toContain("人物");
    expect(selectMemoryNodeTypes(["person", "place"], "", graphOntology.node_types)).toEqual({ groupId: "", nodeTypes: ["person", "place"] });
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
      id: "relation:elfie::literal:assertion-literal",
      source: "elfie",
      target: "literal:assertion-literal",
      evidenceIds: ["evidence-literal"],
      assertionIds: ["assertion-literal"],
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
    expect(graph.edges.map((edge) => edge.id)).toEqual(["relation:node-a::node-b"]);
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
    expect(graph.edges.map((edge) => edge.id)).toEqual(["relation:node-a::node-b"]);
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
    expect(graph.edges.map((edge) => edge.id)).toEqual(["relation:person-1::person-2", "relation:person-1::place-1"]);
  });

  it("类型组和节点类型联动，筛选只改变图节点并按端点重投影边", () => {
    const nodeTypes = graphOntology.node_types;
    expect(selectMemoryNodeGroup("space_geography", ["person"], nodeTypes)).toEqual({
      groupId: "space_geography",
      nodeTypes: [],
    });
    expect(selectMemoryNodeTypes(["person"], "", nodeTypes)).toEqual({
      groupId: "",
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
    expect(projected.edges.map((edge) => edge.id)).toEqual(["relation:person-1::person-2"]);
  });
});
