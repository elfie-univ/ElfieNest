import { useEffect, useMemo, useState } from "react";

import "./memory-audit.css";

type Tab = "detail" | "add" | "recall";
type AuditItem = { id: string; node_type?: string; label: string; description?: string | null; confidence?: number | null; properties?: Record<string, unknown>; relevance?: number };
type AuditReport = { database: string; elfie_id: string; counts: Record<string, number>; node_type_counts: Record<string, number>; predicate_counts: Record<string, number>; checks: { checks: Array<{ status: string; name: string; detail?: string }> }; data: { nodes: AuditItem[]; assertions: Array<Record<string, unknown>>; episodes: Array<Record<string, unknown>>; evidence: Array<Record<string, unknown>> } };
type RecallReport = { elapsed_ms: number; counts: Record<string, number | boolean>; bundle: { focus_nodes: AuditItem[]; assertions: Array<Record<string, unknown>>; episodes: Array<Record<string, unknown>>; evidence: Array<Record<string, unknown>> }; rendered: string };
type GraphNode = { id: string; kind: string; label: string; x: number; y: number };
type GraphEdge = { id: string; source: string; target: string; label: string; kind: string; evidenceIds?: string[] };

const labels: Record<string, string> = { person: "人物", group: "群体/家庭", knowledge: "知识", place: "地点", object: "物体", event: "事件", elfie: "精灵", self_model: "自我模型", genesis_commit_receipt: "初始化回执", literal: "字面值" };
const colors: Record<string, string> = { person: "#7a5aa6", group: "#8b6b3f", knowledge: "#277b5e", place: "#3b7195", object: "#6d8f62", event: "#a06b18", elfie: "#b55f3d", self_model: "#516f8b", genesis_commit_receipt: "#80735f", literal: "#718078" };
const NON_SEMANTIC_LEGACY_PREDICATES = new Set(["about", "knows", "knows_boundary", "related_to"]);

function nodeLabel(node: AuditItem): string { const kind = node.node_type ?? "unknown"; return labels[kind] ?? kind; }
function graphLabel(value: string, limit = 12): string { return value.length > limit ? `${value.slice(0, limit)}…` : value; }
function normalizeNode(node: AuditItem & { node_id?: string }): AuditItem { return { ...node, id: node.id || node.node_id || "" }; }

export function MemoryAuditPage(): React.JSX.Element {
  const [report, setReport] = useState<AuditReport | null>(null);
  const [recall, setRecall] = useState<RecallReport | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [selectedEdgeId, setSelectedEdgeId] = useState("");
  const [tab, setTab] = useState<Tab>("detail");
  const [filter, setFilter] = useState("all");
  const [contains, setContains] = useState("");
  const [query, setQuery] = useState("");
  const [episodeText, setEpisodeText] = useState("");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  async function loadReport(): Promise<void> {
    setLoading(true);
    const params = new URLSearchParams();
    if (filter !== "all") params.set("node_type", filter);
    if (contains.trim()) params.set("contains", contains.trim());
    const response = await fetch(`/api/memory-audit/inspect?${params.toString()}`);
    if (!response.ok) throw new Error(await response.text());
    const next = await response.json() as AuditReport;
    next.data.nodes = next.data.nodes.map((node) => normalizeNode(node as AuditItem & { node_id?: string }));
    setReport(next);
    setSelectedId(next.data.nodes[0]?.id ?? "");
    setLoading(false);
  }

  useEffect(() => { void loadReport().catch((error: unknown) => { setMessage(String(error)); setLoading(false); }); }, [filter]);

  const selected = report?.data.nodes.find((node) => node.id === selectedId) ?? null;
  const visibleAssertions = report?.data.assertions ?? [];
  const graph = useMemo(() => {
    const assertions = report?.data.assertions ?? [];
    const nodes = report?.data.nodes ?? [];
    const evidenceIds = new Set((report?.data.evidence ?? []).map((item) => String(item.evidence_id)));
    if (!nodes.length) return { nodes: [] as GraphNode[], edges: [] as GraphEdge[] };
    const nodeIds = new Set(nodes.map((item) => item.id));
    const edges: GraphEdge[] = [];
    assertions.forEach((item) => {
      if (NON_SEMANTIC_LEGACY_PREDICATES.has(String(item.predicate ?? ""))) return;
      const assertionId = String(item.assertion_id);
      const assertionEvidence = (Array.isArray(item.evidence_ids) ? item.evidence_ids : []).map(String).filter((id) => evidenceIds.has(id));
      if (item.subject_id && item.object_node_id && nodeIds.has(String(item.subject_id)) && nodeIds.has(String(item.object_node_id))) edges.push({ id: assertionId, source: String(item.subject_id), target: String(item.object_node_id), label: String(item.predicate ?? "关系"), kind: "assertion", evidenceIds: assertionEvidence });
    });
    const positions = new Map(nodes.map((item, index) => { const angle = index * 2.39996; const radius = 90 + Math.sqrt(index + 1) * 30; return [item.id, { x: 520 + Math.cos(angle) * radius, y: 390 + Math.sin(angle) * radius * .62 }]; }));
    for (let iteration = 0; iteration < 20; iteration += 1) {
      const delta = new Map(nodes.map((item) => [item.id, { x: 0, y: 0 }]));
      for (let i = 0; i < nodes.length; i += 1) for (let j = i + 1; j < nodes.length; j += 1) { const ni = nodes[i]; const nj = nodes[j]; if (!ni || !nj) continue; const a = positions.get(ni.id); const b = positions.get(nj.id); const da = delta.get(ni.id); const db = delta.get(nj.id); if (!a || !b || !da || !db) continue; const dx = a.x - b.x; const dy = a.y - b.y; const distance = Math.max(18, Math.hypot(dx, dy)); const force = 380 / (distance * distance); const ux = dx / distance; const uy = dy / distance; da.x += ux * force; da.y += uy * force; db.x -= ux * force; db.y -= uy * force; }
      edges.forEach((edge) => { const a = positions.get(edge.source); const b = positions.get(edge.target); const da = delta.get(edge.source); const db = delta.get(edge.target); if (!a || !b || !da || !db) return; const dx = b.x - a.x; const dy = b.y - a.y; const distance = Math.max(1, Math.hypot(dx, dy)); const force = Math.min(2.2, distance / 170); da.x += dx / distance * force; da.y += dy / distance * force; db.x -= dx / distance * force; db.y -= dy / distance * force; });
      nodes.forEach((item) => { const point = positions.get(item.id)!; const shift = delta.get(item.id)!; point.x = Math.max(35, Math.min(1005, point.x + shift.x)); point.y = Math.max(80, Math.min(690, point.y + shift.y)); });
    }
    return { nodes: nodes.map((item) => ({ id: item.id, kind: item.node_type ?? "node", label: item.label, x: positions.get(item.id)!.x, y: positions.get(item.id)!.y })), edges };
  }, [report]);
  const graphNodeById = new Map(graph.nodes.map((node) => [node.id, node]));

  async function runRecall(): Promise<void> {
    if (!query.trim()) return;
    setMessage("正在执行真实 recall…");
    const response = await fetch("/api/memory-audit/recall", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query }) });
    if (!response.ok) { setMessage(await response.text()); return; }
    const next = await response.json() as RecallReport;
    next.bundle.focus_nodes = next.bundle.focus_nodes.map((node) => normalizeNode(node as AuditItem & { node_id?: string }));
    setRecall(next);
    setMessage(`已完成检索：${next.counts.focus_nodes ?? 0} 个节点，${next.elapsed_ms}ms`);
    setTab("recall");
  }

  function showItem(id: string): void { setSelectedId(id); setTab("detail"); }
  const selectedEdge = graph.edges.find((edge) => edge.id === selectedEdgeId) ?? null;
  const selectedEdgeEvidence = selectedEdge ? (selectedEdge.evidenceIds ?? []).map((id) => report?.data.evidence.find((item) => String(item.evidence_id) === id)).filter(Boolean) : [];

  return <main className="memory-audit-page">
    <header className="memory-audit-header">
      <div><span className="memory-audit-kicker">MEMORY AUDIT · READ ONLY</span><h1>记忆审计台</h1><p>从现有数据库看清 Episode、证据、关系和召回结果。</p></div>
      <span className="memory-audit-live">● 真实 SQLite 数据</span>
    </header>

    <section className="memory-audit-toolbar">
      <label>节点类型<select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="all">全部</option>{Object.entries(report?.node_type_counts ?? {}).map(([kind, count]) => <option key={kind} value={kind}>{labels[kind] ?? kind} ({count})</option>)}</select></label>
      <label>名称或描述<input value={contains} onChange={(event) => setContains(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void loadReport(); }} placeholder="输入后回车过滤" /></label>
      <button onClick={() => void loadReport()}>刷新</button>
    </section>

    <section className="memory-audit-shell">
      <div className="memory-audit-main">
        <div className="memory-audit-graph-head"><div><strong>记忆关系图</strong><span>全部 Node 与 Assertion；Evidence 在选中关系后查看</span></div><span>全库 {report?.counts.nodes ?? 0} 节点 · {report?.counts.assertions ?? 0} 条关系</span></div>
        {loading ? <div className="memory-audit-empty">正在读取真实 Memory…</div> : <div className="memory-audit-graph-canvas" aria-label="真实记忆来源链">
          <div className="memory-audit-memory-cards" aria-label="记忆卡片来源">{(report?.data.episodes ?? []).map((episode) => <button key={String(episode.episode_id)} title={String(episode.content_text ?? episode.episode_id)} onClick={() => setMessage(`记忆卡片：${String(episode.content_text ?? episode.episode_id)}`)}>{String(episode.content_text ?? episode.episode_id)}</button>)}</div>
          <svg className="memory-audit-svg" viewBox="0 0 1040 720" role="img" aria-label="Episode、Evidence 与 Node 关系网络">
            <defs><marker id="memory-audit-arrow-v2" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="3.5"><path d="M0,0 L8,3.5 L0,7 Z" /></marker></defs>
            {graph.edges.map((edge) => { const source = graphNodeById.get(edge.source); const target = graphNodeById.get(edge.target); if (!source || !target) return null; return <g className={`memory-audit-svg-edge ${edge.kind} ${selectedEdgeId === edge.id ? "is-selected" : ""}`} key={edge.id} onClick={() => { setSelectedEdgeId(edge.id); setSelectedId(""); setTab("detail"); }} role="button" tabIndex={0}><line markerEnd="url(#memory-audit-arrow-v2)" x1={source.x} x2={target.x} y1={source.y + 22} y2={target.y - 22} /><text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 6}>{edge.label}</text><title>{edge.label}</title></g>; })}
            {graph.nodes.map((node) => <g className={`memory-audit-svg-node ${node.kind} ${selectedId === node.id ? "is-selected" : ""}`} key={node.id} onClick={() => { setSelectedEdgeId(""); const item = report?.data.nodes.find((candidate) => candidate.id === node.id); if (item) showItem(item.id); else setMessage(node.label); }} role="button" tabIndex={0}>
              <circle cx={node.x} cy={node.y} r="22" />
              <text className="memory-audit-svg-node-label" x={node.x} y={node.y + 4} textAnchor="middle">{graphLabel(node.label, 8)}</text><title>{node.label}</title>
            </g>)}
          </svg>
          <div className="memory-audit-legend-v2"><span className="assertion-key">关系边 Assertion</span><span className="person-key">人物</span><span className="elfie-key">精灵</span><span className="group-key">群体/家庭</span><span className="knowledge-key">知识</span><span className="place-key">地点</span></div>
        </div>}
        <footer className="memory-audit-footer">当前画布：{graph.nodes.filter((node) => !["episode", "evidence"].includes(node.kind)).length} 个 Node · {graph.edges.filter((edge) => edge.kind === "assertion").length} 条关系边　|　全库：{report?.counts.nodes ?? 0} 节点 · {report?.counts.assertions ?? 0} 关系 · {report?.counts.episodes ?? 0} Episode</footer>
      </div>

      <aside className="memory-audit-side">
        <nav className="memory-audit-tabs">{([["detail", "详情"], ["add", "添加 Episode"], ["recall", "检索"]] as const).map(([value, text]) => <button className={tab === value ? "is-active" : ""} key={value} onClick={() => setTab(value)}>{text}</button>)}</nav>
        {tab === "detail" && <div className="memory-audit-panel"><h2>当前选择</h2>{selectedEdge ? <><span className="memory-audit-type memory-audit-relation-type">关系边</span><h3>{selectedEdge.label}</h3><p>这条边表示两个 Node 之间的 Assertion。</p><h4>证明 Evidence</h4>{selectedEdgeEvidence.length ? selectedEdgeEvidence.map((item) => <blockquote className="memory-audit-edge-evidence" key={String(item?.evidence_id)}>{String(item?.evidence_id)}<br />{String(item?.excerpt ?? "")}</blockquote>) : <p>这条关系没有关联 Evidence。</p>}</> : selected ? <><span className="memory-audit-type" style={{ background: colors[selected.node_type ?? ""] }}>{nodeLabel(selected)}</span><h3>{selected.label}</h3><p>{selected.description || "没有描述"}</p><dl><dt>置信度</dt><dd>{selected.confidence == null ? "—" : `${Math.round(selected.confidence * 100)}%`}</dd><dt>关系</dt><dd>{visibleAssertions.filter((item) => item.subject_id === selected.id || item.object_node_id === selected.id).length}</dd></dl><h4>属性</h4><pre>{JSON.stringify(selected.properties ?? {}, null, 2)}</pre></> : <p>点击 Node 或关系边查看详情。</p>}</div>}
        {tab === "add" && <div className="memory-audit-panel"><h2>添加完整 Episode</h2><p>输入一段有上下文、有头尾的完整故事，用于接入记忆整理流程。</p><textarea value={episodeText} onChange={(event) => setEpisodeText(event.target.value)} placeholder="例如：今天……" rows={9} /><button className="primary" onClick={() => setMessage("当前版本只展示输入；真实写入必须经过 Memory candidate 和 consolidation 链路。")}>开始整理</button><p className="memory-audit-muted">页面不会绕过生产写入链，也不会伪造已经写入的结果。</p></div>}
        {tab === "recall" && <div className="memory-audit-panel"><h2>检索记忆</h2><input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void runRecall(); }} placeholder="输入问题或关键词" /><button className="primary" onClick={() => void runRecall()}>执行真实检索</button>{recall && <><div className="memory-audit-result-meta">{recall.elapsed_ms}ms · {recall.counts.focus_nodes} 个节点 · {recall.counts.evidence} 条证据</div>{recall.bundle.focus_nodes.map((node, index) => <button className="memory-audit-result" key={node.id} onClick={() => showItem(node.id)}><b>{index + 1}</b><span>{node.label}<small>{node.node_type ?? "unknown"} · relevance {node.relevance ?? "—"}</small></span></button>)}<pre className="memory-audit-rendered">{recall.rendered}</pre></>}</div>}
      </aside>
    </section>
    <p className="memory-audit-message" role="status">{message}</p>
  </main>;
}
