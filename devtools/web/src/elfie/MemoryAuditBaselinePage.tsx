import { useEffect, useMemo, useState } from "react";

import "./memory-audit.css";

type Node = { id: string; node_id?: string; node_type?: string; label: string; description?: string | null; properties?: Record<string, unknown> };
type Report = { counts: Record<string, number>; data: { nodes: Node[]; episodes: Array<Record<string, unknown>>; evidence: Array<Record<string, unknown>>; assertions: Array<Record<string, unknown>> } };
type GNode = { id: string; kind: string; label: string; x: number; y: number };
type GEdge = { id: string; source: string; target: string; label: string; evidence: string[] };

const colors: Record<string, string> = { person: "#7a5aa6", knowledge: "#277b5e", place: "#3b7195", event: "#a06b18", elfie: "#b55f3d", self_model: "#516f8b" };
const NON_SEMANTIC_LEGACY_PREDICATES = new Set(["about", "knows", "knows_boundary", "related_to"]);
const short = (value: string, max = 18): string => value.length > max ? `${value.slice(0, max)}…` : value;

export function MemoryAuditBaselinePage(): React.JSX.Element {
  const [report, setReport] = useState<Report | null>(null);
  const [episodeId, setEpisodeId] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [selectedEdge, setSelectedEdge] = useState<GEdge | null>(null);

  useEffect(() => { void fetch("/api/memory-audit/inspect").then((response) => response.json() as Promise<Report>).then((next) => { next.data.nodes = next.data.nodes.map((node) => ({ ...node, id: node.id || node.node_id || "" })); setReport(next); setEpisodeId(String(next.data.episodes[0]?.episode_id ?? "")); }); }, []);
  const graph = useMemo(() => {
    if (!report) return { nodes: [] as GNode[], edges: [] as GEdge[] };
    const evidence = report.data.evidence.filter((item) => String(item.source_id) === episodeId);
    const ids = new Set(evidence.map((item) => String(item.evidence_id)));
    const assertions = report.data.assertions.filter((item) => !NON_SEMANTIC_LEGACY_PREDICATES.has(String(item.predicate ?? "")) && (Array.isArray(item.evidence_ids) ? item.evidence_ids : []).some((id) => ids.has(String(id))));
    const nodeIds = new Set<string>(); assertions.forEach((item) => { if (item.subject_id) nodeIds.add(String(item.subject_id)); if (item.object_node_id) nodeIds.add(String(item.object_node_id)); });
    const positions = [[135, 445], [320, 535], [490, 420], [675, 500], [850, 430], [250, 640], [540, 640], [800, 620]];
    const nodes = report.data.nodes.filter((item) => nodeIds.has(item.id)).slice(0, positions.length).map((item, index) => ({ id: item.id, kind: item.node_type ?? "node", label: item.label, x: positions[index]?.[0] ?? 0, y: positions[index]?.[1] ?? 0 }));
    const edges = assertions.map((item) => ({ id: String(item.assertion_id), source: String(item.subject_id), target: String(item.object_node_id), label: String(item.predicate ?? "关系"), evidence: (Array.isArray(item.evidence_ids) ? item.evidence_ids : []).map(String) })).filter((item) => nodes.some((node) => node.id === item.source) && nodes.some((node) => node.id === item.target));
    return { nodes, edges };
  }, [report, episodeId]);
  const nodeMap = new Map(graph.nodes.map((node) => [node.id, node]));
  const selected = report?.data.nodes.find((node) => node.id === selectedId);
  const selectedEvidence = selectedEdge ? report?.data.evidence.filter((item) => selectedEdge.evidence.includes(String(item.evidence_id))) ?? [] : [];
  return <main className="memory-audit-page memory-audit-baseline-page">
    <header className="memory-audit-header"><div><span className="memory-audit-kicker">MEMORY AUDIT · BASELINE</span><h1>记忆审计台</h1><p>11:08 基线：记忆卡片来源与单个故事的关系图。</p></div><span className="memory-audit-live">● 真实 SQLite 数据</span></header>
    <section className="memory-audit-shell"><div className="memory-audit-main">
      <div className="memory-audit-graph-head"><div><strong>记忆组织图</strong><span>卡片来源 → Evidence 证明 → Node 关系</span></div><span>{graph.nodes.length} 个 Node · {graph.edges.length} 条关系</span></div>
      <div className="memory-audit-baseline-cards">{(report?.data.episodes ?? []).map((episode) => <button className={String(episode.episode_id) === episodeId ? "is-active" : ""} key={String(episode.episode_id)} onClick={() => { setEpisodeId(String(episode.episode_id)); setSelectedEdge(null); }}>{short(String(episode.content_text ?? episode.episode_id), 30)}</button>)}</div>
      <svg className="memory-audit-baseline-svg" viewBox="0 0 1040 760" role="img" aria-label="11:08 基线记忆关系图">
        <defs><marker id="baseline-arrow" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="3.5"><path d="M0,0 L8,3.5 L0,7 Z" /></marker></defs>
        {graph.edges.map((edge) => { const source = nodeMap.get(edge.source); const target = nodeMap.get(edge.target); if (!source || !target) return null; return <g className={selectedEdge?.id === edge.id ? "baseline-edge selected" : "baseline-edge"} key={edge.id} onClick={() => { setSelectedEdge(edge); setSelectedId(""); }}><line markerEnd="url(#baseline-arrow)" x1={source.x} y1={source.y} x2={target.x} y2={target.y} /><text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 7}>{edge.label}</text><title>{edge.label}</title></g>; })}
        {graph.nodes.map((node) => <g className="baseline-node" key={node.id} onClick={() => { setSelectedId(node.id); setSelectedEdge(null); }}><circle cx={node.x} cy={node.y} r="34" fill={colors[node.kind] ?? "#718078"} /><text x={node.x} y={node.y + 4} textAnchor="middle">{short(node.label, 10)}</text><title>{node.label}</title></g>)}
      </svg>
      <footer className="memory-audit-footer">当前故事 {graph.nodes.length} 个 Node · {graph.edges.length} 条关系　|　全库 {report?.counts.nodes ?? 0} 节点 · {report?.counts.assertions ?? 0} 关系</footer>
    </div><aside className="memory-audit-side"><div className="memory-audit-panel"><h2>{selectedEdge ? "关系详情" : "当前选择"}</h2>{selectedEdge ? <><h3>{selectedEdge.label}</h3><p>Assertion 关系边，Evidence 证明如下：</p>{selectedEvidence.map((item) => <blockquote className="memory-audit-edge-evidence" key={String(item.evidence_id)}>{String(item.evidence_id)}<br />{String(item.excerpt ?? "")}</blockquote>)}</> : selected ? <><h3>{selected.label}</h3><p>{selected.description || "没有描述"}</p><pre>{JSON.stringify(selected.properties ?? {}, null, 2)}</pre></> : <p>点击 Node 或关系边查看详情。</p>}</div></aside></section>
  </main>;
}
