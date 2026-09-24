import { Component, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Select } from "antd";
import type { ForceGraphMethods } from "react-force-graph-3d";
import { CanvasTexture, Sprite, SpriteMaterial } from "three";

import "./memory-debug-workspace.css";
import {
  projectAssertionDetail,
  projectEpisodeDetail,
  projectEvidenceDetail,
  projectNodeDetail,
  type InspectorField as ProjectedInspectorField,
  type InspectorHeader as ProjectedInspectorHeader,
  type InspectorNode,
} from "./inspectorProjection";

type Tab = "add" | "recall";
type DetailSelection = "node" | "edge" | "episode" | "evidence" | null;
type AuditItem = { id: string; node_type?: string; label: string; description?: string | null; confidence?: number | null; importance?: number | null; freshness?: number | null; half_life_days?: number | null; status?: string | null; properties?: Record<string, unknown>; relevance?: number };
type AuditRecord = Record<string, unknown>;
type SnapshotMetadata = { snapshot_id: string; generated_at: string; consistency: string; source: string; schema_version: number; semantic_revision: number | null; semantic_revision_status?: string; read_consistency_token?: string };
type RecallCandidate = { candidate_id: string; candidate_kind: string; score: number; matched_terms: string[]; query_terms?: string[]; source?: string; rank?: number | null; kept: boolean; exclusion_reason?: string | null };
type RecallSelection = { recall_id?: string | null; candidate_boundary: string; candidates: RecallCandidate[]; summaries: AuditRecord[]; returned_ids: { nodes: string[]; assertions: string[]; episodes: string[]; evidence: string[] } };
type AuditReport = { database: string; elfie_id: string; snapshot: SnapshotMetadata & { coverage?: string; read_limit?: number; filters_applied?: boolean; next_cursor?: string | null }; counts: Record<string, number>; loaded_counts: Record<string, number>; matched_counts: Record<string, number>; focus_node_ids?: string[]; coverage: { status: string; truncated: Record<string, boolean>; filters_applied: boolean; read_limit: number }; pagination?: { page_size: number; next_cursor: string | null; cursor: string | null }; node_type_counts: Record<string, number>; predicate_counts: Record<string, number>; checks: { checks: Array<{ status: string; name: string; detail?: string }> }; data: { nodes: AuditItem[]; context_nodes?: AuditItem[]; assertions: AuditRecord[]; episodes: AuditRecord[]; evidence: AuditRecord[] } };
type RecallReport = { elapsed_ms: number; snapshot: SnapshotMetadata; request?: AuditRecord; counts: Record<string, number | boolean>; bundle: { focus_nodes: AuditItem[]; assertions: AuditRecord[]; episodes: AuditRecord[]; evidence: AuditRecord[]; conflicts?: AuditRecord[]; limits?: AuditRecord }; selection: RecallSelection; rendered: string };
type PreviewReport = { operation: { operation_id: string; elapsed_ms: number; status: string; mode: string; sandbox: boolean; production_mutated: boolean; cleanup: string }; input: { episode_id: string; content_chars: number; summary: string | null }; before: { counts: Record<string, number> }; after: { counts: Record<string, number> }; changes: { added_ids: Record<string, string[]>; affected: Record<string, AuditRecord[]> }; receipt: AuditRecord; error: { type: string; message: string } | null };
type ConsolidationReport = { success: boolean; triggered: boolean; candidate_id?: string | null; turn_id?: string | null; status?: string; before?: AuditRecord | null; after?: AuditRecord | null; knowledge_created?: number; consolidated_count?: number };
export type MemoryDebugRecallReturnedIds = Readonly<{
  readonly nodes: readonly string[];
  readonly assertions: readonly string[];
  readonly episodes: readonly string[];
  readonly evidence: readonly string[];
}>;
export type MemoryDebugRecallContext = Readonly<{
  readonly source: "baseline" | "on_demand";
  readonly recall_id?: string | null;
  readonly query?: string;
  readonly status?: string;
  readonly revision?: string | number | null;
  readonly reason?: string | null;
  readonly selection?: Readonly<Record<string, unknown>>;
  readonly returned_points?: readonly unknown[];
  readonly returned_ids?: MemoryDebugRecallReturnedIds;
  readonly raw?: unknown;
}>;
export type MemoryDebugWorkspaceProps = Readonly<{
  readonly elfieId?: string;
  readonly elfieName?: string;
  readonly initialRecall?: MemoryDebugRecallContext | null;
  readonly embedded?: boolean;
  readonly onClose?: () => void;
}>;
type GraphNodeSeed = { id: string; kind: string; label: string };
type GraphNode = { id: string; kind: string; label: string; x: number; y: number; radius?: number };
type GraphEdge = { id: string; source: string; target: string; label: string; predicate?: string; kind: string; evidenceIds?: string[]; symmetric?: boolean; importance?: number };
type Graph3DNode = GraphNodeSeed & { val: number; degree: number; originalId?: string; preview?: boolean; x?: number; y?: number; z?: number };
type Graph3DLink = GraphEdge;
type GraphFilters = { lifecycle?: string; minConfidence?: number | undefined; nodeTypes?: ReadonlySet<string> | undefined; predicateTypes?: ReadonlySet<string> | undefined; includeNodeIds?: ReadonlySet<string> | undefined; includeAssertionIds?: ReadonlySet<string> | undefined };
type GraphLayout = { nodes: GraphNode[]; edges: GraphEdge[]; lod: "force" | "overview" };
type ReadPhase = "loading" | "partial" | "ready" | "empty" | "stale" | "error";

function normalizedGraphScore(value: number | undefined): number {
  if (value === undefined || !Number.isFinite(value)) return 0.5;
  return Math.min(1, Math.max(0, value));
}

/** Node radius is a memory-salience projection; graph degree is kept for labels/layout only. */
export function graphNodeValue(importance: number | undefined): number {
  return Math.max(1.5, normalizedGraphScore(importance) * 4);
}

/** Semantic assertion width represents pairwise relation importance, not selection state. */
export function graphLinkWidth(importance: number | undefined): number {
  return 1.2 + normalizedGraphScore(importance) * 3;
}

const labels: Record<string, string> = { person: "人物", group: "群体/家庭", knowledge: "知识", place: "地点", object: "物体", event: "事件", elfie: "精灵", self_model: "自我模型", genesis_commit_receipt: "初始化回执", literal: "字面值" };
const graphTypeColors: Record<string, string> = { person: "#b892ff", group: "#d5a85f", knowledge: "#42d6a4", place: "#5bb9ff", object: "#7db277", event: "#ffc857", elfie: "#ff8f6b", self_model: "#8da9c4", genesis_commit_receipt: "#d0b57a", literal: "#a7b7c4" };
const DIMMED_LINK_COLOR = "rgba(107, 133, 151, 0.16)";
const NON_SEMANTIC_LEGACY_PREDICATES = new Set(["about", "knows", "knows_boundary", "related_to"]);

function graphNodeColor(kind: string): string { return graphTypeColors[kind] ?? "#8da9c4"; }

function nodeLabel(node: AuditItem): string { const kind = node.node_type ?? "unknown"; return labels[kind] ?? kind; }
function escapeHtml(value: string): string { return value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ?? character); }
function normalizeNode(node: AuditItem & { node_id?: string }): AuditItem { return { ...node, id: node.id || node.node_id || "" }; }
function recordArray(record: AuditRecord | null, key: string): AuditRecord[] { const value = record?.[key]; return Array.isArray(value) ? value.filter((item): item is AuditRecord => typeof item === "object" && item !== null && !Array.isArray(item)) : []; }
function recordText(record: AuditRecord | null, key: string, fallback = "—"): string { const value = record?.[key]; return value == null || value === "" ? fallback : String(value); }
function recordNumber(record: AuditRecord | null, key: string): number | null { const value = record?.[key]; return typeof value === "number" && Number.isFinite(value) ? value : null; }
function recordBoolean(record: AuditRecord | null, key: string): boolean | null { const value = record?.[key]; return typeof value === "boolean" ? value : null; }
function recordStringArray(record: AuditRecord | null, key: string): string[] { const value = record?.[key]; return Array.isArray(value) ? value.map(String).filter(Boolean) : []; }
function recordLifecycle(record: AuditItem): string { return String(record.status ?? record.properties?.lifecycle ?? record.properties?.status ?? "unknown"); }
const relationLabels: Record<string, string> = {
  owner_of: "主人",
  owned_by: "归属于",
  member_of: "成员",
  kin_of: "家人（具体关系未知）",
  friend_of: "朋友",
  classmate_of: "同学",
  colleague_of: "同事",
  neighbor_of: "邻居",
  acquaintance_of: "认识",
  parent_of: "父母",
  child_of: "子女",
  sibling_of: "兄弟姐妹",
  student_of: "学生",
  teacher_of: "老师",
  guided_by: "由其引导",
  // Legacy rows are read-only compatibility data and are normalized for the
  // detail surface without becoming new semantic vocabulary.
  family: "家人（具体关系未知）",
  friend: "朋友",
  owner: "归属于",
  acquaintance: "认识",
};
const relationAliases: Record<string, string> = { family: "kin_of", friend: "friend_of", owner: "owned_by", acquaintance: "acquaintance_of" };
const symmetricRelationKinds = new Set(["kin_of", "friend_of", "classmate_of", "colleague_of", "neighbor_of", "acquaintance_of", "sibling_of", "near", "related_to"]);
function relationIsSymmetric(kind: string): boolean { return symmetricRelationKinds.has(relationAliases[kind] ?? kind); }
function relationKindFromRecord(record: AuditRecord | null, fallback = "关系"): string {
  const predicate = recordText(record, "predicate", fallback);
  if (predicate !== "relationship") return relationAliases[predicate] ?? predicate;
  const qualifiers = record?.qualifiers;
  if (qualifiers && typeof qualifiers === "object" && !Array.isArray(qualifiers)) {
    const context = (qualifiers as Record<string, unknown>).context;
    if (typeof context === "string") {
      const role = context.split(":").pop()?.trim();
      if (role) return relationAliases[role] ?? role;
    }
  }
  return predicate;
}
export function relationDisplayLabel(kind: string): string { return relationLabels[kind] ?? kind; }
export function relationSentence(source: string, target: string, kind: string, sourceKind?: string, targetKind?: string): string {
  const normalizedKind = relationAliases[kind] ?? kind;
  const label = relationDisplayLabel(normalizedKind);
  if (normalizedKind === "friend_of") return `${source} 和 ${target} 是朋友`;
  if (normalizedKind === "kin_of") return `${source} 和 ${target} 是家人（具体关系未知）`;
  if (normalizedKind === "classmate_of") return `${source} 和 ${target} 是同学`;
  if (normalizedKind === "colleague_of") return `${source} 和 ${target} 是同事`;
  if (normalizedKind === "neighbor_of") return `${source} 和 ${target} 是邻居`;
  if (normalizedKind === "acquaintance_of") return `${source} 和 ${target} 互相认识`;
  if (normalizedKind === "near") return `${source} 和 ${target} 相互靠近`;
  if (normalizedKind === "parent_of") return `${source} 是 ${target} 的父母`;
  if (normalizedKind === "child_of") return `${source} 是 ${target} 的子女`;
  if (normalizedKind === "sibling_of") return `${source} 和 ${target} 是兄弟姐妹`;
  if (normalizedKind === "owned_by" && sourceKind === "elfie" && targetKind !== "elfie") return `${target} 是 ${source} 的主人`;
  if (normalizedKind === "owner_of") return `${source} 是 ${target} 的主人`;
  if (normalizedKind === "student_of") return `${source} 是 ${target} 的学生`;
  if (normalizedKind === "teacher_of") return `${source} 是 ${target} 的老师`;
  if (normalizedKind === "member_of") return `${source} 是 ${target} 的成员`;
  if (normalizedKind === "guided_by") return `${source} 由 ${target} 引导`;
  return `${source} → ${target} · ${label}`;
}
const emptyRecallReturnedIds = (): MemoryDebugRecallReturnedIds => ({ nodes: [], assertions: [], episodes: [], evidence: [] });
function inferRecallReturnedIds(points: readonly unknown[]): MemoryDebugRecallReturnedIds {
  const result = emptyRecallReturnedIds() as { nodes: string[]; assertions: string[]; episodes: string[]; evidence: string[] };
  points.forEach((value) => {
    const point = value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
    const id = String(point.id ?? point.node_id ?? point.assertion_id ?? point.episode_id ?? point.evidence_id ?? "");
    if (!id) return;
    const kind = String(point.kind ?? "");
    if (kind === "focus_node" || kind === "node") result.nodes.push(id);
    else if (kind === "assertion") result.assertions.push(id);
    else if (kind === "episode") result.episodes.push(id);
    else if (kind === "evidence") result.evidence.push(id);
  });
  return { nodes: [...new Set(result.nodes)], assertions: [...new Set(result.assertions)], episodes: [...new Set(result.episodes)], evidence: [...new Set(result.evidence)] };
}
function buildTraceRecallReport(context: MemoryDebugRecallContext, report: AuditReport | null): RecallReport {
  const points = context.returned_points ?? [];
  const inferred = inferRecallReturnedIds(points);
  const explicit = context.returned_ids ?? emptyRecallReturnedIds();
  const returnedIds = {
    nodes: explicit.nodes.length ? [...explicit.nodes] : [...inferred.nodes],
    assertions: explicit.assertions.length ? [...explicit.assertions] : [...inferred.assertions],
    episodes: explicit.episodes.length ? [...explicit.episodes] : [...inferred.episodes],
    evidence: explicit.evidence.length ? [...explicit.evidence] : [...inferred.evidence],
  };
  const selectionSource = context.selection && typeof context.selection === "object" ? context.selection : {};
  const candidates = Array.isArray(selectionSource.candidates) ? selectionSource.candidates : [];
  const summaries = Array.isArray(selectionSource.summaries) ? selectionSource.summaries : [];
  const nodes = returnedIds.nodes.map((id) => report?.data.nodes.find((item) => item.id === id)).filter((item): item is AuditItem => item !== undefined);
  const assertions = returnedIds.assertions.map((id) => report?.data.assertions.find((item) => String(item.assertion_id) === id)).filter((item): item is AuditRecord => item !== undefined);
  const episodes = returnedIds.episodes.map((id) => report?.data.episodes.find((item) => String(item.episode_id) === id)).filter((item): item is AuditRecord => item !== undefined);
  const evidence = returnedIds.evidence.map((id) => report?.data.evidence.find((item) => String(item.evidence_id) === id)).filter((item): item is AuditRecord => item !== undefined);
  const snapshot = report?.snapshot ?? { snapshot_id: "chat-trace", generated_at: "", consistency: "trace", source: "chat_trace", schema_version: 1, semantic_revision: null };
  return {
    elapsed_ms: 0,
    snapshot,
    ...(context.query ? { request: { query: context.query } } : {}),
    counts: { focus_nodes: returnedIds.nodes.length, assertions: returnedIds.assertions.length, episodes: returnedIds.episodes.length, evidence: returnedIds.evidence.length, paths: 0, conflicts: 0, truncated: false },
    bundle: { focus_nodes: nodes, assertions, episodes, evidence },
    selection: {
      recall_id: context.recall_id ?? null,
      candidate_boundary: String(selectionSource.candidate_boundary ?? "trace_candidates"),
      candidates: candidates as RecallCandidate[],
      summaries,
      returned_ids: returnedIds,
    },
    rendered: JSON.stringify(context.raw ?? { source: "chat_trace", query: context.query, returned_points: points }, null, 2),
  };
}
type InspectorField = { label: string; value: ReactNode; mono?: boolean };
function InspectorFieldGrid({ fields }: { fields: InspectorField[] }): React.JSX.Element {
  return <dl className="memory-debug-field-grid">{fields.map((field) => <div className="memory-debug-field-row" key={field.label}><dt>{field.label}</dt><dd className={field.mono ? "is-mono" : undefined}>{field.value}</dd></div>)}</dl>;
}

function projectedFields(fields: ProjectedInspectorField[]): InspectorField[] {
  return fields.map((field) => ({ label: field.label, value: field.value, mono: field.source === "technical" }));
}

function InspectorHeaderSummary({ header, className = "" }: { header: ProjectedInspectorHeader; className?: string }): React.JSX.Element {
  const percent = (value: number | null): string => value == null ? "未记录" : `${Math.round(value * 100)}%`;
  return <div className="memory-debug-inspector-header">
    <span className={`memory-debug-type ${className}`}>{header.semanticType}</span>
    <h2>{header.label}</h2>
    <p className="memory-debug-detail-copy">{header.summary}</p>
    <div className="memory-debug-inspector-stats" aria-label="对象状态摘要">
      <div><span>状态</span><strong>{header.status}</strong></div>
      <div><span>重要度</span><strong>{percent(header.importance)}</strong></div>
      <div><span>置信度</span><strong>{percent(header.confidence)}</strong></div>
    </div>
  </div>;
}

function InspectorConnections({
  connections,
  onAssertion,
}: {
  connections: Array<{ id: string; label: string; detail: string; importance: number | null; confidence: number | null; kind: string }>;
  onAssertion?: (id: string) => void;
}): React.JSX.Element {
  if (!connections.length) return <p>暂无已记录关联。</p>;
  return <div>{connections.map((connection) => {
    const content = <><strong>{connection.label}</strong><span>{connection.detail}</span><small>{connection.importance == null ? "重要度未记录" : `${Math.round(connection.importance * 100)}% 重要度`} · {connection.confidence == null ? "置信度未记录" : `${Math.round(connection.confidence * 100)}% 置信度`}</small></>;
    return onAssertion && connection.kind === "relation"
      ? <button className="memory-debug-related-card" type="button" key={connection.id} onClick={() => onAssertion(connection.id)}>{content}</button>
      : <div className="memory-debug-related-card memory-debug-related-card-static" key={connection.id}>{content}</div>;
  })}</div>;
}

function InspectorSources({
  sources,
  onEpisode,
}: {
  sources: Array<{ id: string; label: string; excerpt: string; kind: string }>;
  onEpisode?: (id: string) => void;
}): React.JSX.Element {
  if (!sources.length) return <p>当前快照没有可解析的来源 Episode。</p>;
  return <div>{sources.map((source) => {
    const content = <><strong>{source.label}</strong><span>{source.excerpt}</span></>;
    return onEpisode && source.kind === "episode"
      ? <button className="memory-debug-evidence-card" type="button" key={source.id} onClick={() => onEpisode(source.id)}>{content}</button>
      : <div className="memory-debug-evidence-card memory-debug-related-card-static" key={source.id}>{content}</div>;
  })}</div>;
}

export function MemoryDebugLegend({ layoutLocked }: { layoutLocked: boolean }): React.JSX.Element {
  return <div className="memory-debug-legend-v2" aria-label="图例"><span className="memory-debug-type-key person-key">人物</span><span className="memory-debug-type-key elfie-key">精灵</span><span className="memory-debug-type-key group-key">群体/家庭</span><span className="memory-debug-type-key knowledge-key">知识</span><span className="memory-debug-type-key place-key">地点</span><span className="assertion-key">关系</span><span className="evidence-key">来源</span><span className="memory-debug-scale-key">点大小=重要度 · 关系线宽=重要度</span><span className="memory-debug-legend-hint">{layoutLocked ? "节点位置已锁定 · 按住左键拖动画布旋转 · 滚轮缩放" : "节点可拖拽 · 按住左键拖动节点调整位置"} · 悬停只查看 · 点击节点/关系查看右侧详情</span></div>;
}

function endpointId(endpoint: unknown): string {
  if (typeof endpoint === "string" || typeof endpoint === "number") return String(endpoint);
  if (typeof endpoint === "object" && endpoint !== null && "id" in endpoint) return String((endpoint as { id: unknown }).id);
  return String(endpoint ?? "");
}
export function formatEpisodeTime(record: AuditRecord): string {
  const value = record.occurred_from ?? record.occurred_at ?? record.occurred_to;
  if (value == null || value === "") return "时间未记录";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date).replace(/\//g, "-");
}

export function recallGraphProjectionFilters(
  hasRecall: boolean,
  showOnlyRecallResults: boolean,
  nodeIds: ReadonlySet<string>,
  assertionIds: ReadonlySet<string>,
): Pick<GraphFilters, "includeNodeIds" | "includeAssertionIds"> {
  return hasRecall && showOnlyRecallResults
    ? { includeNodeIds: nodeIds, includeAssertionIds: assertionIds }
    : {};
}

export function splitRecallFocusNodes(nodes: readonly AuditItem[]): {
  ranked: AuditItem[];
  zeroScore: AuditItem[];
  unscored: AuditItem[];
} {
  const ranked = nodes
    .filter((node) => typeof node.relevance === "number" && Number.isFinite(node.relevance) && node.relevance > 0)
    .sort((left, right) => (right.relevance ?? 0) - (left.relevance ?? 0));
  const zeroScore = nodes.filter((node) => typeof node.relevance === "number" && Number.isFinite(node.relevance) && node.relevance <= 0);
  const unscored = nodes.filter((node) => typeof node.relevance !== "number" || !Number.isFinite(node.relevance));
  return { ranked, zeroScore, unscored };
}

export function recallGraphNodeHitIds(returnedNodeIds: ReadonlySet<string>, focusNodes: ReturnType<typeof splitRecallFocusNodes>): Set<string> {
  const zeroScoreIds = new Set(focusNodes.zeroScore.map((node) => node.id));
  return new Set([...returnedNodeIds].filter((id) => !zeroScoreIds.has(id)));
}

export function filterMemoryDebugEpisodes(
  episodes: readonly AuditRecord[],
  lifecycleFilter: string,
  recalledEpisodeIds?: ReadonlySet<string>,
): AuditRecord[] {
  return episodes
    .filter((episode) => {
      if (lifecycleFilter !== "all" && String(episode.lifecycle ?? "unknown") !== lifecycleFilter) return false;
      if (recalledEpisodeIds && !recalledEpisodeIds.has(String(episode.episode_id ?? ""))) return false;
      return true;
    })
    .sort((left, right) => String(left.occurred_from ?? left.occurred_at ?? left.episode_id)
      .localeCompare(String(right.occurred_from ?? right.occurred_at ?? right.episode_id)));
}

function mergeRecords(records: AuditRecord[], incoming: AuditRecord[], key: string): AuditRecord[] {
  const merged = new Map(records.map((record) => [String(record[key] ?? ""), record]));
  incoming.forEach((record) => merged.set(String(record[key] ?? ""), record));
  return Array.from(merged.values());
}

const LARGE_GRAPH_NODE_THRESHOLD = 260;

// Orbit controls keep camera rotation behind an explicit press-and-drag gesture.
// Hovering the graph must remain a read-only inspection interaction.
export const MEMORY_DEBUG_GRAPH_CONTROL_TYPE = "orbit" as const;

export function graphNavigationActive(pointerType: string, buttons: number): boolean {
  return pointerType === "touch" || buttons !== 0;
}

export function graphLinkIsContextual(
  hasTransientHighlight: boolean,
  selectedEdgeId: string,
  linkId: string,
  isReturned: boolean,
  isAffected: boolean,
): boolean {
  return !hasTransientHighlight || selectedEdgeId === linkId || isReturned || isAffected;
}

export function graphLinkColor(
  hasTransientHighlight: boolean,
  selectedEdgeId: string,
  linkId: string,
  kind: string,
  isReturned: boolean,
  isAffected: boolean,
): string {
  if (!graphLinkIsContextual(hasTransientHighlight, selectedEdgeId, linkId, isReturned, isAffected)) return DIMMED_LINK_COLOR;
  return kind === "preview-assertion" ? "#ff9d57" : "#5e9fbb";
}

export function graphLinkArrowLength(
  hasTransientHighlight: boolean,
  selectedEdgeId: string,
  linkId: string,
  kind: string,
  isReturned: boolean,
  isAffected: boolean,
): number {
  if (kind !== "assertion" && kind !== "preview-assertion") return 0;
  return graphLinkIsContextual(hasTransientHighlight, selectedEdgeId, linkId, isReturned, isAffected) ? 4 : 0;
}

function graphLinkArrowColor(
  hasTransientHighlight: boolean,
  selectedEdgeId: string,
  linkId: string,
  kind: string,
  isReturned: boolean,
  isAffected: boolean,
): string {
  if (!graphLinkIsContextual(hasTransientHighlight, selectedEdgeId, linkId, isReturned, isAffected)) return DIMMED_LINK_COLOR;
  return kind === "preview-assertion" ? "#ff9d57" : "#8bc8df";
}

type TraceRect = { left: number; top: number; width: number; height: number };

export function episodeTraceSourcePoint(cardRect: TraceRect, canvasRect: TraceRect): { x: number; y: number } {
  return {
    x: cardRect.left - canvasRect.left + cardRect.width / 2,
    y: cardRect.top - canvasRect.top + cardRect.height,
  };
}

export function toggleEpisodeSelection(currentId: string, requestedId: string): string {
  return currentId === requestedId ? "" : requestedId;
}

type WebGLStatus = "checking" | "available" | "unavailable";

function detectWebGLSupport(): boolean {
  if (typeof document === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

type WebGLGraphErrorBoundaryProps = { children: React.ReactNode; fallback: React.ReactNode };
type WebGLGraphErrorBoundaryState = { hasError: boolean };

class WebGLGraphErrorBoundary extends Component<WebGLGraphErrorBoundaryProps, WebGLGraphErrorBoundaryState> {
  state: WebGLGraphErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): WebGLGraphErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error): void {
    console.error("Memory Debug 3D renderer failed; using the 2D fallback.", error);
  }

  render(): React.ReactNode {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}

export function layoutMemoryDebugGraph(projection: { nodes: GraphNodeSeed[]; edges: GraphEdge[] }): GraphLayout {
  const nodes = projection.nodes;
  const edges = projection.edges;
  if (!nodes.length) return { nodes: [], edges: [], lod: "force" };
  if (nodes.length > LARGE_GRAPH_NODE_THRESHOLD) {
    const columns = Math.max(2, Math.ceil(Math.sqrt(nodes.length * 1.35)));
    const rows = Math.ceil(nodes.length / columns);
    const xStep = 990 / Math.max(1, columns - 1);
    const yStep = 670 / Math.max(1, rows - 1);
    return {
      lod: "overview",
      edges,
      nodes: nodes.map((item, index) => ({
        id: item.id,
        kind: item.kind,
        label: item.label,
        x: 25 + (index % columns) * xStep,
        y: 25 + Math.floor(index / columns) * yStep,
        radius: 5.5,
      })),
    };
  }
  const positions = new Map(nodes.map((item, index) => {
    const angle = index * 2.39996;
    const radius = 90 + Math.sqrt(index + 1) * 30;
    return [item.id, { x: 520 + Math.cos(angle) * radius, y: 390 + Math.sin(angle) * radius * .62 }];
  }));
  for (let iteration = 0; iteration < 20; iteration += 1) {
    const delta = new Map(nodes.map((item) => [item.id, { x: 0, y: 0 }]));
    for (let i = 0; i < nodes.length; i += 1) for (let j = i + 1; j < nodes.length; j += 1) {
      const ni = nodes[i]; const nj = nodes[j]; if (!ni || !nj) continue;
      const a = positions.get(ni.id); const b = positions.get(nj.id); const da = delta.get(ni.id); const db = delta.get(nj.id);
      if (!a || !b || !da || !db) continue;
      const dx = a.x - b.x; const dy = a.y - b.y; const distance = Math.max(18, Math.hypot(dx, dy)); const force = 380 / (distance * distance); const ux = dx / distance; const uy = dy / distance;
      da.x += ux * force; da.y += uy * force; db.x -= ux * force; db.y -= uy * force;
    }
    edges.forEach((edge) => {
      const a = positions.get(edge.source); const b = positions.get(edge.target); const da = delta.get(edge.source); const db = delta.get(edge.target);
      if (!a || !b || !da || !db) return;
      const dx = b.x - a.x; const dy = b.y - a.y; const distance = Math.max(1, Math.hypot(dx, dy)); const force = Math.min(2.2, distance / 170);
      da.x += dx / distance * force; da.y += dy / distance * force; db.x -= dx / distance * force; db.y -= dy / distance * force;
    });
    nodes.forEach((item) => { const point = positions.get(item.id); const shift = delta.get(item.id); if (!point || !shift) return; point.x = Math.max(35, Math.min(1005, point.x + shift.x)); point.y = Math.max(80, Math.min(690, point.y + shift.y)); });
  }
  return { lod: "force", edges, nodes: nodes.map((item) => ({ id: item.id, kind: item.kind, label: item.label, x: positions.get(item.id)!.x, y: positions.get(item.id)!.y })) };
}

type MemoryDebugGraphFallbackProps = {
  graphData: { nodes: Graph3DNode[]; links: Graph3DLink[] };
  selectedId: string;
  selectedEdgeId: string;
  highlightedNodeIds: ReadonlySet<string>;
  highlightedEdgeIds: ReadonlySet<string>;
  hasTransientHighlight: boolean;
  onNodeClick: (node: Graph3DNode) => void;
  onLinkClick: (link: Graph3DLink) => void;
};

function shortGraphLabel(value: string, limit = 24): string {
  return value.length > limit ? `${value.slice(0, limit)}…` : value;
}

function MemoryDebugGraphFallback({
  graphData,
  selectedId,
  selectedEdgeId,
  highlightedNodeIds,
  highlightedEdgeIds,
  hasTransientHighlight,
  onNodeClick,
  onLinkClick,
}: MemoryDebugGraphFallbackProps): React.JSX.Element {
  const layout = useMemo(() => {
    const edges = graphData.links.map((edge): GraphEdge => {
      const projected: GraphEdge = {
        id: edge.id,
        source: endpointId(edge.source),
        target: endpointId(edge.target),
        label: edge.label,
        kind: edge.kind,
      };
      if (edge.evidenceIds) projected.evidenceIds = [...edge.evidenceIds];
      if (edge.predicate) projected.predicate = edge.predicate;
      if (edge.symmetric) projected.symmetric = true;
      if (edge.importance !== undefined) projected.importance = edge.importance;
      return projected;
    });
    return layoutMemoryDebugGraph({
      nodes: graphData.nodes.map(({ id, kind, label }) => ({ id, kind, label })),
      edges,
    });
  }, [graphData]);
  const nodesById = new Map(graphData.nodes.map((node) => [node.id, node]));
  const linksById = new Map(graphData.links.map((link) => [link.id, link]));
  const positions = new Map(layout.nodes.map((node) => [node.id, node]));
  const nodePalette: Record<string, string> = {
    person: "#b892ff",
    group: "#d5a85f",
    knowledge: "#42d6a4",
    place: "#5bb9ff",
    object: "#7db277",
    event: "#ffc857",
    elfie: "#ff8f6b",
    self_model: "#8da9c4",
    literal: "#a7b7c4",
  };

  return <div className="memory-debug-graph-fallback">
    <div className="memory-debug-graph-fallback-notice" role="status">
      <strong>当前浏览器未提供 WebGL，已切换到 2D 诊断视图</strong>
      <span>数据、筛选、节点详情和关系详情仍然可用；恢复硬件加速后会自动使用 3D 图。</span>
    </div>
    <svg className="memory-debug-2d-fallback-canvas" viewBox="0 0 1040 760" role="img" aria-label="2D 记忆知识图谱降级视图">
      <defs>
        <marker id="memory-debug-fallback-arrow" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="3.5">
          <path d="M0,0 L8,3.5 L0,7 Z" fill="#8bc8df" />
        </marker>
      </defs>
      {layout.edges.map((edge) => {
        const source = positions.get(edge.source);
        const target = positions.get(edge.target);
        if (!source || !target) return null;
        const selected = selectedEdgeId === edge.id;
        const highlighted = highlightedEdgeIds.has(edge.id);
        const dimmed = hasTransientHighlight && !selected && !highlighted;
        const link = linksById.get(edge.id) ?? edge as Graph3DLink;
        const stroke = selected ? "#fff" : highlighted ? "#ff9d57" : dimmed ? DIMMED_LINK_COLOR : "#5e9fbb";
        return <g className={dimmed ? "memory-debug-2d-edge is-dimmed" : "memory-debug-2d-edge"} key={edge.id} onClick={() => onLinkClick(link)} role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onLinkClick(link); } }}>
          <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} stroke={stroke} strokeWidth={graphLinkWidth(edge.importance)} strokeDasharray={edge.kind === "preview-assertion" ? "7 4" : undefined} markerEnd={dimmed || edge.symmetric ? undefined : "url(#memory-debug-fallback-arrow)"} />
          <text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 5}>{shortGraphLabel(edge.label, 18)}</text>
          <title>{edge.label}</title>
        </g>;
      })}
      {layout.nodes.map((node) => {
        const graphNode = nodesById.get(node.id);
        if (!graphNode) return null;
        const selected = selectedId === node.id;
        const highlighted = highlightedNodeIds.has(node.id);
        const dimmed = hasTransientHighlight && !selected && !highlighted;
        const radius = Math.max(4, Math.min(15, graphNode.val * 1.5));
        const fill = graphNode.preview ? "#ff9d57" : selected ? "#fff" : nodePalette[graphNode.kind] ?? "#8da9c4";
        return <g className={`memory-debug-2d-node ${selected ? "is-selected" : ""} ${highlighted ? "is-highlighted" : ""} ${dimmed ? "is-dimmed" : ""}`} key={node.id} onClick={() => onNodeClick(graphNode)} role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onNodeClick(graphNode); } }}>
          <circle cx={node.x} cy={node.y} r={radius} fill={fill} stroke={highlighted || selected ? "#fff" : "rgba(210,231,243,.7)"} strokeWidth={selected ? 3.5 : highlighted ? 2.5 : 1} />
          <text className="memory-debug-2d-node-kind" x={node.x} y={node.y - radius - 5} textAnchor="middle">{graphNode.kind}</text>
          <text className="memory-debug-2d-node-label" x={node.x} y={node.y + radius + 14} textAnchor="middle">{shortGraphLabel(graphNode.label)}</text>
          <title>{graphNode.label}</title>
        </g>;
      })}
    </svg>
  </div>;
}

export function projectMemoryDebugGraph(report: AuditReport | null, filters: GraphFilters = {}): { nodes: GraphNodeSeed[]; edges: GraphEdge[] } {
  const assertions = report?.data.assertions ?? [];
  const nodes = (report?.data.nodes ?? []).filter((item) => {
    if (filters.includeNodeIds && !filters.includeNodeIds.has(item.id)) return false;
    if (filters.nodeTypes && !filters.nodeTypes.has(item.node_type ?? "node")) return false;
    if (filters.lifecycle && filters.lifecycle !== "all" && recordLifecycle(item) !== filters.lifecycle) return false;
    if (filters.minConfidence != null && (typeof item.confidence !== "number" || item.confidence < filters.minConfidence)) return false;
    return true;
  });
  const nodeIds = new Set(nodes.map((item) => item.id));
  const projectedNodes: GraphNodeSeed[] = nodes.map((item) => ({ id: item.id, kind: item.node_type ?? "node", label: item.label }));
  const literalNodes = new Map<string, GraphNodeSeed>();
  const evidenceIds = new Set((report?.data.evidence ?? []).map((item) => String(item.evidence_id)));
  const edges: GraphEdge[] = [];
  assertions.forEach((item) => {
    const assertionId = String(item.assertion_id);
    if (filters.includeAssertionIds && !filters.includeAssertionIds.has(assertionId)) return;
    const predicate = String(item.predicate ?? "关系");
    if (NON_SEMANTIC_LEGACY_PREDICATES.has(predicate)) return;
    if (filters.predicateTypes && !filters.predicateTypes.has(predicate)) return;
    if (filters.minConfidence != null && (typeof item.confidence !== "number" || item.confidence < filters.minConfidence)) return;
    const source = item.subject_id == null ? "" : String(item.subject_id);
    if (!source || !nodeIds.has(source)) return;
    const assertionEvidence = (Array.isArray(item.evidence_ids) ? item.evidence_ids : [])
      .map(String)
      .filter((id) => evidenceIds.has(id));
    let target = item.object_node_id == null ? "" : String(item.object_node_id);
    if (target && !nodeIds.has(target)) return;
    if (!target && item.object_literal != null && String(item.object_literal).trim()) {
      target = `literal:${assertionId}`;
      literalNodes.set(target, { id: target, kind: "literal", label: String(item.object_literal) });
    }
    if (!target) return;
    const importance = recordNumber(item, "importance");
    edges.push({
      id: assertionId,
      source,
      target,
      label: relationDisplayLabel(relationKindFromRecord(item, predicate)),
      predicate,
      kind: "assertion",
      evidenceIds: assertionEvidence,
      symmetric: relationIsSymmetric(relationKindFromRecord(item, predicate)),
      ...(importance == null ? {} : { importance }),
    });
  });
  projectedNodes.sort((left, right) => left.id.localeCompare(right.id));
  edges.sort((left, right) => left.id.localeCompare(right.id));
  return { nodes: [...projectedNodes, ...[...literalNodes.values()].sort((left, right) => left.id.localeCompare(right.id))], edges };
}

export function MemoryDebugWorkspacePage({ elfieId, initialRecall = null, embedded = false, onClose }: MemoryDebugWorkspaceProps = {}): React.JSX.Element {
  type ForceGraphComponent = typeof import("react-force-graph-3d").default;
  const [report, setReport] = useState<AuditReport | null>(null);
  const [recall, setRecall] = useState<RecallReport | null>(null);
  const [traceRecall, setTraceRecall] = useState<MemoryDebugRecallContext | null>(initialRecall);
  const [preview, setPreview] = useState<PreviewReport | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [selectedEdgeId, setSelectedEdgeId] = useState("");
  const [selectedEpisodeId, setSelectedEpisodeId] = useState("");
  const [selectedEvidenceId, setSelectedEvidenceId] = useState("");
  const [detailSelection, setDetailSelection] = useState<DetailSelection>(null);
  const [filterContextNodeIds, setFilterContextNodeIds] = useState<ReadonlySet<string>>(new Set());
  const [tab, setTab] = useState<Tab>("recall");
  const [leftPanelOpen, setLeftPanelOpen] = useState(Boolean(initialRecall));
  const [detailPanelOpen, setDetailPanelOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [selectedPredicates, setSelectedPredicates] = useState<string[]>([]);
  const [lifecycleFilter, setLifecycleFilter] = useState("all");
  const [confidenceFilter, setConfidenceFilter] = useState("all");
  const [query, setQuery] = useState(initialRecall?.query ?? "");
  const [episodeText, setEpisodeText] = useState("");
  const [loading, setLoading] = useState(true);
  const [readPhase, setReadPhase] = useState<ReadPhase>("loading");
  const [readError, setReadError] = useState("");
  const [message, setMessage] = useState("");
  const [graphFitReady, setGraphFitReady] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [consolidationRunning, setConsolidationRunning] = useState(false);
  const [showOnlyRecallResults, setShowOnlyRecallResults] = useState(false);
  const [layoutLocked, setLayoutLocked] = useState(true);
  const [tracePositions, setTracePositions] = useState<Record<string, { x: number; y: number }>>({});
  const [graphViewport, setGraphViewport] = useState({ width: 0, height: 0 });
  const [ForceGraph3DComponent, setForceGraph3DComponent] = useState<ForceGraphComponent | null>(null);
  const [webglStatus, setWebglStatus] = useState<WebGLStatus>("checking");
  const graphRef = useRef<ForceGraphMethods<Graph3DNode, Graph3DLink> | undefined>(undefined);
  const graphCanvasRef = useRef<HTMLDivElement | null>(null);
  const episodeCardRefs = useRef(new Map<string, HTMLButtonElement>());
  const reportRequestRef = useRef(0);
  const graphFitPendingRef = useRef(true);
  const labelSpritesRef = useRef(new Map<string, { text: string; sprite: Sprite }>());

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    let active = true;
    if (!detectWebGLSupport()) {
      setWebglStatus("unavailable");
      return () => { active = false; };
    }
    setWebglStatus("available");
    void import("react-force-graph-3d").then(({ default: component }) => {
      if (active) setForceGraph3DComponent(() => component);
    }).catch((error: unknown) => {
      console.error("Unable to load the 3D memory graph; using the 2D fallback.", error);
      if (active) setWebglStatus("unavailable");
    });
    return () => { active = false; };
  }, []);

  useEffect(() => () => {
    labelSpritesRef.current.forEach(({ sprite }) => {
      const material = sprite.material;
      if (material instanceof SpriteMaterial) {
        material.map?.dispose();
        material.dispose();
      }
    });
    labelSpritesRef.current.clear();
  }, []);

  async function loadReport(requestFilter = "all", preserveMessage = false): Promise<void> {
    const requestId = reportRequestRef.current + 1;
    reportRequestRef.current = requestId;
    setLoading(true);
    setReadPhase("loading");
    setReadError("");
    if (!preserveMessage) setMessage("");
    try {
      let cursor: string | null = null;
      let merged: AuditReport | null = null;
      const contextIds = new Set<string>();
      for (let page = 0; page < 100; page += 1) {
        const params = new URLSearchParams();
        if (elfieId) params.set("elfie_id", elfieId);
        if (requestFilter !== "all") params.set("node_type", requestFilter);
        params.set("page_size", "1000");
        if (cursor) params.set("cursor", cursor);
        const response = await fetch(`/api/memory-audit/inspect?${params.toString()}`);
        if (requestId !== reportRequestRef.current) return;
        if (response.status === 409) {
          const payload = await response.json() as { detail?: { message?: string } | string };
          const detail = payload.detail;
          const staleMessage = typeof detail === "object" && detail !== null
            ? detail.message ?? "当前读取边界已过期"
            : String(detail ?? "当前读取边界已过期");
          setReport((current) => current ? { ...current, snapshot: { ...current.snapshot, consistency: "stale" }, coverage: { ...current.coverage, status: "stale" } } : current);
          setReadPhase("stale");
          setReadError(staleMessage);
          setMessage(`快照已过期：${staleMessage}。请点击“刷新”重新读取。`);
          setLoading(false);
          return;
        }
        if (!response.ok) {
          const body = await response.text();
          let detail = body;
          try {
            const payload = JSON.parse(body) as { detail?: string | { message?: string } };
            detail = typeof payload.detail === "object" && payload.detail !== null
              ? payload.detail.message ?? body
              : payload.detail ?? body;
          } catch {
            // Keep the server body when it is not JSON.
          }
          throw new Error(String(detail));
        }
        const next = await response.json() as AuditReport;
        if (requestId !== reportRequestRef.current) return;
        const pageContextNodes = (next.data.context_nodes ?? [])
          .map((node) => normalizeNode(node as AuditItem & { node_id?: string }));
        pageContextNodes.forEach((node) => contextIds.add(node.id));
        next.data.nodes.forEach((node) => contextIds.delete(String(node.id ?? (node as AuditItem & { node_id?: string }).node_id ?? "")));
        const pageNodes = [...next.data.nodes, ...pageContextNodes]
          .map((node) => normalizeNode(node as AuditItem & { node_id?: string }));
        next.data.nodes = mergeRecords([], pageNodes, "id") as AuditItem[];
        next.data.context_nodes = [];
        if (!merged) {
          merged = next;
          setReport(merged);
        } else {
          merged.data.nodes = mergeRecords(merged.data.nodes, next.data.nodes, "id") as AuditItem[];
          merged.data.assertions = mergeRecords(merged.data.assertions, next.data.assertions, "assertion_id");
          merged.data.episodes = mergeRecords(merged.data.episodes, next.data.episodes, "episode_id");
          merged.data.evidence = mergeRecords(merged.data.evidence, next.data.evidence, "evidence_id");
          if (next.pagination) merged.pagination = next.pagination;
          merged.coverage = next.coverage;
          merged.snapshot = next.snapshot;
          merged.loaded_counts = { ...next.loaded_counts, episodes: merged.data.episodes.length, nodes: merged.data.nodes.length, assertions: merged.data.assertions.length, evidence: merged.data.evidence.length };
        }
        cursor = next.pagination?.next_cursor ?? null;
        setReadPhase(cursor ? "partial" : (next.counts.nodes === 0 && next.counts.episodes === 0 && next.counts.assertions === 0 && next.counts.evidence === 0 ? "empty" : "ready"));
        if (!cursor) break;
      }
      if (requestId !== reportRequestRef.current) return;
      if (cursor || !merged) throw new Error("Memory 分页未能在 100 批内收敛");
      setReport(merged);
      setFilterContextNodeIds(new Set([...contextIds].filter((id) => !new Set(merged?.focus_node_ids ?? []).has(id))));
      setSelectedId((current) => current && merged?.data.nodes.some((node) => node.id === current) ? current : "");
      setSelectedEdgeId((current) => current && merged?.data.assertions.some((item) => String(item.assertion_id) === current) ? current : "");
      setSelectedEvidenceId((current) => current && merged?.data.evidence.some((item) => String(item.evidence_id) === current) ? current : "");
      setReadPhase(merged.counts.nodes === 0 && merged.counts.episodes === 0 && merged.counts.assertions === 0 && merged.counts.evidence === 0 ? "empty" : "ready");
      setLoading(false);
    } catch (error: unknown) {
      if (requestId !== reportRequestRef.current) return;
      const errorMessage = String(error);
      setReadPhase("error");
      setReadError(errorMessage);
      if (!preserveMessage) setMessage(errorMessage);
      setLoading(false);
    }
  }

  useEffect(() => { void loadReport(); }, [elfieId]);
  useEffect(() => {
    const container = graphCanvasRef.current;
    if (!container) return undefined;
    const updateSize = (): void => {
      const layer = container.querySelector<HTMLElement>(".memory-debug-3d-layer");
      setGraphViewport({
        width: Math.max(320, container.clientWidth),
        height: Math.max(360, layer?.clientHeight ?? container.clientHeight - 140),
      });
    };
    updateSize();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(updateSize);
    observer.observe(container);
    return () => observer.disconnect();
  }, [report?.snapshot.snapshot_id]);

  const selected = report?.data.nodes.find((node) => node.id === selectedId) ?? null;
  const visibleAssertions = report?.data.assertions ?? [];
  const localConfidence = confidenceFilter === "0.5" ? .5 : confidenceFilter === "0.8" ? .8 : undefined;
  const selectedEpisodeNodeIds = new Set<string>();
  const selectedEpisodeAssertionIds = new Set<string>();
  const selectedEpisode = report?.data.episodes.find((episode) => String(episode.episode_id) === selectedEpisodeId) ?? null;
  const selectedEvidence = report?.data.evidence.find((item) => String(item.evidence_id) === selectedEvidenceId) ?? null;
  const selectedEpisodeEvidence = selectedEpisode
    ? (report?.data.evidence ?? []).filter((item) => String(item.source_id) === selectedEpisodeId)
    : [];
  const selectedEpisodeEvidenceIds = new Set(selectedEpisodeEvidence.map((item) => String(item.evidence_id)));
  visibleAssertions
    .filter((item) => Array.isArray(item.evidence_ids) && item.evidence_ids.some((id) => selectedEpisodeEvidenceIds.has(String(id))))
    .forEach((item) => {
      selectedEpisodeAssertionIds.add(String(item.assertion_id));
      [String(item.subject_id), item.object_node_id == null ? "" : String(item.object_node_id)].filter(Boolean).forEach((id) => selectedEpisodeNodeIds.add(id));
    });
  const recallView = recall ?? (traceRecall ? buildTraceRecallReport(traceRecall, report) : null);
  const returnedRecallNodeIds = new Set(recallView?.selection.returned_ids.nodes ?? []);
  const recalledFocusNodeGroups = splitRecallFocusNodes(recallView?.bundle.focus_nodes ?? []);
  const recalledNodeIds = recallGraphNodeHitIds(returnedRecallNodeIds, recalledFocusNodeGroups);
  const recalledAssertionIds = new Set(recallView?.selection.returned_ids.assertions ?? []);
  const recalledEpisodeIds = new Set(
    (recallView?.bundle.episodes ?? []).map((episode) => String(episode.episode_id ?? "")).filter(Boolean),
  );
  const recalledAssertionNodeIds = new Set(
    visibleAssertions
      .filter((item) => recalledAssertionIds.has(String(item.assertion_id)))
      .flatMap((item) => [String(item.subject_id), item.object_node_id == null ? "" : String(item.object_node_id)])
      .filter(Boolean),
  );
  const previewNodeIds = useMemo(() => new Set(preview?.changes.added_ids.nodes ?? []), [preview]);
  const previewAssertionIds = useMemo(() => new Set(preview?.changes.added_ids.assertions ?? []), [preview]);
  const previewAssertionNodeIds = useMemo(() => new Set(
    (preview?.changes.affected.assertions ?? [])
      .filter((item) => previewAssertionIds.has(String(item.assertion_id)))
      .flatMap((item) => [String(item.subject_id), item.object_node_id == null ? "" : String(item.object_node_id)])
      .filter(Boolean),
  ), [preview, previewAssertionIds]);
  const graph = useMemo(() => {
    const recallProjection = recallGraphProjectionFilters(
      Boolean(recallView),
      showOnlyRecallResults,
      new Set([...recalledNodeIds, ...recalledAssertionNodeIds]),
      recalledAssertionIds,
    );
    const projection = projectMemoryDebugGraph(report, {
      lifecycle: lifecycleFilter,
      minConfidence: localConfidence,
      nodeTypes: selectedTypes.length ? new Set(selectedTypes) : undefined,
      predicateTypes: selectedPredicates.length ? new Set(selectedPredicates) : undefined,
      ...recallProjection,
    });
    const degree = new Map<string, number>();
    projection.edges.forEach((edge) => {
      degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
    });
    const records = new Map((report?.data.nodes ?? []).map((item) => [item.id, item]));
    const nodes: Graph3DNode[] = projection.nodes.map((item) => {
      const record = records.get(item.id);
      const importance = typeof record?.importance === "number" ? record.importance : .5;
      const nodeDegree = degree.get(item.id) ?? 0;
      return { ...item, degree: nodeDegree, val: graphNodeValue(importance) };
    });
    return { nodes, edges: projection.edges };
  }, [lifecycleFilter, localConfidence, recallView, report, selectedPredicates, selectedTypes, showOnlyRecallResults]);
  const graphNodeIds = useMemo(() => new Set(graph.nodes.map((node) => node.id)), [graph.nodes]);
  const previewNodeKey = (id: string): string => previewNodeIds.has(id) || !graphNodeIds.has(id) ? `preview:${id}` : id;
  const previewGraphNodes = useMemo(() => (preview?.changes.affected.nodes ?? []).map((item) => {
    const originalId = String(item.node_id);
    const id = previewNodeKey(originalId);
    return {
      id,
      originalId,
      kind: String(item.node_type ?? "node"),
      label: String(item.label ?? item.node_id),
      degree: 1,
      val: graphNodeValue(typeof item.importance === "number" ? item.importance : undefined),
      preview: id !== originalId,
    } satisfies Graph3DNode;
  }), [graphNodeIds, preview, previewNodeIds]);
  const previewGraphEdges = useMemo(() => (preview?.changes.affected.assertions ?? []).map((item) => ({
    id: `preview:${String(item.assertion_id)}`,
    source: previewNodeKey(String(item.subject_id)),
    target: previewNodeKey(String(item.object_node_id ?? "")),
    label: relationDisplayLabel(relationKindFromRecord(item, String(item.predicate ?? "关系"))),
    predicate: String(item.predicate ?? "关系"),
    kind: "preview-assertion",
    evidenceIds: Array.isArray(item.evidence_ids) ? item.evidence_ids.map(String) : [],
    symmetric: relationIsSymmetric(relationKindFromRecord(item, String(item.predicate ?? "关系"))),
    importance: typeof item.importance === "number" ? item.importance : undefined,
  })).filter((edge) => edge.target !== "preview:"), [graphNodeIds, preview, previewNodeIds]);
  const graphData: { nodes: Graph3DNode[]; links: Graph3DLink[] } = useMemo(() => ({
    nodes: [...graph.nodes, ...previewGraphNodes],
    // react-force-graph mutates link.source/link.target into node objects while
    // indexing the scene. Keep those mutations out of the projection used by
    // the right-hand detail panel, otherwise React can receive a Three object
    // where a string endpoint is expected after a graph click.
    links: [...graph.edges, ...previewGraphEdges].map((edge): Graph3DLink => {
      const cloned: Graph3DLink = { id: edge.id, source: edge.source, target: edge.target, label: edge.label, kind: edge.kind };
      if (edge.predicate) cloned.predicate = edge.predicate;
      if (edge.symmetric) cloned.symmetric = true;
      if (edge.evidenceIds) cloned.evidenceIds = [...edge.evidenceIds];
      if (edge.importance !== undefined) cloned.importance = edge.importance;
      return cloned;
    }),
  }), [graph, previewGraphEdges, previewGraphNodes]);
  const visibleEpisodes = useMemo(() => filterMemoryDebugEpisodes(
    report?.data.episodes ?? [],
    lifecycleFilter,
    recallView ? recalledEpisodeIds : undefined,
  ), [lifecycleFilter, recallView, report]);
  const hasLocalFilters = Boolean(
    selectedTypes.length || selectedPredicates.length || lifecycleFilter !== "all" || confidenceFilter !== "all",
  );
  const activeFilterCount = [
    ...selectedTypes.map(() => true),
    ...selectedPredicates.map(() => true),
    lifecycleFilter !== "all",
    confidenceFilter !== "all",
  ].filter(Boolean).length;
  function updateTracePositions(): void {
    const instance = graphRef.current;
    if (!selectedEpisodeId || !instance) {
      setTracePositions((current) => Object.keys(current).length ? {} : current);
      return;
    }
    const next: Record<string, { x: number; y: number }> = {};
    graph.nodes.filter((node) => selectedEpisodeNodeIds.has(node.id)).forEach((node) => {
      if (typeof node.x !== "number" || typeof node.y !== "number" || typeof node.z !== "number") return;
      const point = instance.graph2ScreenCoords(node.x, node.y, node.z);
      next[node.id] = { x: point.x, y: point.y };
    });
    setTracePositions((current) => JSON.stringify(current) === JSON.stringify(next) ? current : next);
  }

  useEffect(() => {
    if (!selectedEpisodeId) {
      setTracePositions({});
      return undefined;
    }
    let frame = 0;
    const tick = (): void => {
      updateTracePositions();
      frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [graph, selectedEpisodeId]);

  function fitGraph(durationMs = 700): void {
    const instance = graphRef.current;
    if (!instance || !graphData.nodes.length) return;
    graphFitPendingRef.current = false;
    // Let force-graph calculate the camera distance from its actual node
    // bounds. The previous hand-written distance left the whole graph as a
    // small cluster when the data contained a distant or isolated node.
    window.requestAnimationFrame(() => {
      const hasConnectedNodes = graphData.nodes.some((node) => node.degree > 0 || node.preview);
      const fitNode = (node: Graph3DNode): boolean => node.degree > 0 || Boolean(node.preview);
      instance.zoomToFit(0, 36, hasConnectedNodes ? fitNode : undefined);
      const bounds = instance.getGraphBbox(hasConnectedNodes ? fitNode : undefined);
      if (!bounds) return;
      const center = {
        x: (bounds.x[0] + bounds.x[1]) / 2,
        y: (bounds.y[0] + bounds.y[1]) / 2,
        z: (bounds.z[0] + bounds.z[1]) / 2,
      };
      const camera = instance.camera() as unknown as { position?: { x: number; y: number; z: number } };
      const position = camera.position;
      if (!position) return;
      const dx = position.x - center.x;
      const dy = position.y - center.y;
      const dz = position.z - center.z;
      const distance = Math.hypot(dx, dy, dz);
      if (!Number.isFinite(distance) || distance <= 0) return;
      // The library fit includes a conservative perspective margin. Closing
      // the resulting distance by one controlled factor uses more of the
      // full-screen canvas without making the graph crop at the edges.
      const scale = .78;
      instance.cameraPosition(
        { x: center.x + dx * scale, y: center.y + dy * scale, z: center.z + dz * scale },
        center,
        durationMs,
      );
      window.setTimeout(() => setGraphFitReady(true), Math.max(0, durationMs));
    });
  }

  function nodeLabelObject(node: Graph3DNode): Sprite {
    const text = shortGraphLabel(node.label, node.kind === "knowledge" ? 6 : 12);
    const showPersistentLabel = selectedTypes.length > 0
      || graphData.nodes.length <= 60
      || node.kind !== "knowledge"
      || selectedId === node.id;
    if (!showPersistentLabel) {
      const sprite = new Sprite();
      sprite.visible = false;
      return sprite;
    }
    const cached = labelSpritesRef.current.get(String(node.id));
    if (cached?.text === text) {
      cached.sprite.position.set(0, 0, 0);
      return cached.sprite;
    }
    if (cached) {
      const previousMaterial = cached.sprite.material;
      if (previousMaterial instanceof SpriteMaterial) {
        previousMaterial.map?.dispose();
        previousMaterial.dispose();
      }
    }
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    if (!context) return new Sprite();
    const font = '600 24px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    context.font = font;
    const textWidth = Math.ceil(context.measureText(text).width);
    const logicalWidth = Math.max(56, textWidth + 12);
    const logicalHeight = 32;
    const pixelRatio = 2;
    canvas.width = logicalWidth * pixelRatio;
    canvas.height = logicalHeight * pixelRatio;
    context.scale(pixelRatio, pixelRatio);
    context.font = font;
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.lineJoin = "round";
    context.lineWidth = 5;
    context.strokeStyle = "rgba(7, 19, 31, .92)";
    context.strokeText(text, logicalWidth / 2, logicalHeight / 2 + 1);
    context.fillStyle = "#e6f0f8";
    context.fillText(text, logicalWidth / 2, logicalHeight / 2 + 1);
    const sprite = new Sprite(new SpriteMaterial({ map: new CanvasTexture(canvas), transparent: true, depthWrite: false, depthTest: false, opacity: .94 }));
    sprite.scale.set(logicalWidth / 22, logicalHeight / 22, 1);
    sprite.position.set(0, 0, 0);
    labelSpritesRef.current.set(String(node.id), { text, sprite });
    return sprite;
  }

  useEffect(() => {
    if (webglStatus !== "available" || !ForceGraph3DComponent || !graphData.nodes.length) return undefined;
    setGraphFitReady(false);
    graphFitPendingRef.current = true;
    return undefined;
  }, [ForceGraph3DComponent, graphData, webglStatus]);

  // Do not fit on the first viewport frame: force-graph has not settled its
  // 3D positions yet, so fitting there produces a tiny centered cluster.
  // The engine-stop callback fits the settled bounds; manual resize/fit stays
  // available through the explicit toolbar action.

  function resetGraph(): void {
    setSelectedId("");
    setSelectedEdgeId("");
    setSelectedEpisodeId("");
    setSelectedEvidenceId("");
    setDetailSelection(null);
    setRecall(null);
    setTraceRecall(null);
    setShowOnlyRecallResults(false);
    setPreview(null);
    setFilterOpen(false);
    setLeftPanelOpen(false);
    setDetailPanelOpen(false);
    setLayoutLocked(true);
    fitGraph(0);
  }

  function setGraphNavigationEnabled(enabled: boolean): void {
    const controls = graphRef.current?.controls() as { enabled?: boolean } | undefined;
    if (controls) controls.enabled = enabled;
  }

  function clearFilters(): void {
    setSelectedTypes([]);
    setSelectedPredicates([]);
    setLifecycleFilter("all");
    setConfidenceFilter("all");
  }

  function clearSearch(closeRecallPanel = tab === "recall"): void {
    setQuery("");
    setRecall(null);
    setTraceRecall(null);
    setShowOnlyRecallResults(false);
    if (closeRecallPanel) setLeftPanelOpen(false);
    setMessage("已清除搜索结果。");
  }

  function openFilter(): void {
    setFilterOpen((open) => {
      const next = !open;
      if (next) setLeftPanelOpen(false);
      return next;
    });
  }

  function openAddPanel(): void {
    setFilterOpen(false);
    setRecall(null);
    setTraceRecall(null);
    setPreview(null);
    setTab("add");
    setLeftPanelOpen(true);
  }

  async function runRecall(): Promise<void> {
    setFilterOpen(false);
    setTab("recall");
    setLeftPanelOpen(true);
    if (!query.trim()) {
      clearSearch(true);
      return;
    }
    setSelectedId("");
    setSelectedEdgeId("");
    setSelectedEpisodeId("");
    setSelectedEvidenceId("");
    setDetailSelection(null);
    setDetailPanelOpen(false);
    setPreview(null);
    setRecall(null);
    setTraceRecall(null);
    setShowOnlyRecallResults(false);
    setMessage("正在执行真实 recall…");
    const response = await fetch("/api/memory-audit/recall", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, limit: 8, ...(elfieId ? { elfie_id: elfieId } : {}) }) });
    if (!response.ok) { setMessage(await response.text()); return; }
    const next = await response.json() as RecallReport;
    next.bundle.focus_nodes = next.bundle.focus_nodes.map((node) => normalizeNode(node as AuditItem & { node_id?: string }));
    setTraceRecall(null);
    setRecall(next);
    setMessage(`已完成检索：${next.counts.focus_nodes ?? 0} 个节点，${next.elapsed_ms}ms`);
    setTab("recall");
  }

  async function runManualConsolidation(): Promise<void> {
    setFilterOpen(false);
    if (!elfieId) {
      setMessage("请先选择一个精灵。");
      return;
    }
    setConsolidationRunning(true);
    setMessage("正在手动触发 Consolidation…");
    try {
      const foodsResponse = await fetch("/api/runtime/foods");
      if (!foodsResponse.ok) {
        setMessage(await foodsResponse.text());
        return;
      }
      const foodsPayload = await foodsResponse.json() as { items?: Array<{ key: string; ready_for_attempt?: boolean }> };
      const food = (foodsPayload.items ?? []).find((item) => item.ready_for_attempt);
      if (!food) {
        setMessage("没有可用的模型粮食，无法执行 Consolidation。");
        return;
      }
      const response = await fetch(`/api/elfies/${encodeURIComponent(elfieId)}/consolidation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ food_key: food.key }),
      });
      if (!response.ok) {
        setMessage(await response.text());
        return;
      }
      const next = await response.json() as ConsolidationReport;
      if (!next.triggered) {
        setMessage("本次没有触发：当前没有待整理的 Episode，或已有整理正在进行。");
      } else if (next.success) {
        setMessage(`手动 Consolidation 已完成：整理 ${next.consolidated_count ?? 0} 个 Episode，新增 ${next.knowledge_created ?? 0} 个知识节点。`);
      } else {
        setMessage(`Consolidation 已触发，但回合状态为 ${next.status ?? "unknown"}。`);
      }
      void loadReport("all", true);
    } catch (error: unknown) {
      setMessage(String(error));
    } finally {
      setConsolidationRunning(false);
    }
  }

  async function runEpisodePreview(): Promise<void> {
    setFilterOpen(false);
    setTab("add");
    setLeftPanelOpen(true);
    if (!episodeText.trim()) {
      setMessage("请先输入完整 Episode 内容。");
      return;
    }
    setRecall(null);
    setTraceRecall(null);
    setPreview(null);
    setPreviewLoading(true);
    setMessage("正在临时副本中执行 Episode → Consolidation…");
    try {
      const response = await fetch("/api/memory-audit/add-episode-preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ elfie_id: elfieId, content_text: episodeText, mode: "deterministic_local" }) });
      if (!response.ok) { setMessage(await response.text()); return; }
      const next = await response.json() as PreviewReport;
      setPreview(next);
      setMessage(`隔离预演${next.operation.status === "completed" ? "完成" : "结束但未完成"}：${next.operation.operation_id}`);
    } finally {
      setPreviewLoading(false);
    }
  }

  function showItem(id: string): void {
    // Keep search results in the left panel while the selected item opens on the right.
    setSelectedId(id);
    setSelectedEdgeId("");
    setSelectedEpisodeId("");
    setSelectedEvidenceId("");
    setDetailSelection("node");
    setDetailPanelOpen(true);
  }
  function showEpisode(id: string): void {
    const nextId = toggleEpisodeSelection(selectedEpisodeId, id);
    setSelectedEpisodeId(nextId);
    setSelectedId("");
    setSelectedEdgeId("");
    setSelectedEvidenceId("");
    setDetailSelection(nextId ? "episode" : null);
    setDetailPanelOpen(Boolean(nextId));
  }
  function showEvidence(id: string): void {
    setSelectedId("");
    setSelectedEdgeId("");
    setSelectedEpisodeId("");
    setSelectedEvidenceId(id);
    setDetailSelection("evidence");
    setDetailPanelOpen(true);
  }
  function showAssertion(id: string): void {
    setSelectedId("");
    setSelectedEpisodeId("");
    setSelectedEvidenceId("");
    setSelectedEdgeId(id);
    setDetailSelection("edge");
    setDetailPanelOpen(true);
  }
  const selectedEdge = graph.edges.find((edge) => edge.id === selectedEdgeId) ?? null;
  const selectedEdgeTargetId = selectedEdge ? endpointId(selectedEdge.target) : "";
  const selectedEdgeEvidence = selectedEdge ? (selectedEdge.evidenceIds ?? []).map((id) => report?.data.evidence.find((item) => String(item.evidence_id) === id)).filter(Boolean) : [];
  const selectedEdgeRecord = visibleAssertions.find((item) => String(item.assertion_id) === selectedEdgeId) ?? null;
  const selectedEdgeRelationKind = relationKindFromRecord(selectedEdgeRecord, selectedEdge?.predicate ?? selectedEdge?.label ?? "关系");
  const selectedEdgeIsSymmetric = relationIsSymmetric(selectedEdgeRelationKind);
  const selectedNodeAssertions = selected ? visibleAssertions.filter((item) => String(item.subject_id) === selected.id || String(item.object_node_id) === selected.id) : [];
  const selectedNodeEvidence = [...new Map(selectedNodeAssertions.flatMap((item) => (Array.isArray(item.evidence_ids) ? item.evidence_ids : []).map(String)).map((id) => [id, report?.data.evidence.find((item) => String(item.evidence_id) === id)]).filter((entry): entry is [string, AuditRecord] => entry[1] != null))].map(([, item]) => item);
  const selectedEpisodeSourceRefs = recordArray(selectedEpisode, "source_refs");
  const inspectorNodeById = new Map<string, InspectorNode>((report?.data.nodes ?? []).map((node) => [node.id, node as InspectorNode]));
  const inspectorEvidenceById = new Map<string, AuditRecord>((report?.data.evidence ?? []).map((item) => [String(item.evidence_id), item]));
  const inspectorEpisodeById = new Map<string, AuditRecord>((report?.data.episodes ?? []).map((item) => [String(item.episode_id), item]));
  const inspectorRelationInput = {
    nodeById: inspectorNodeById,
    evidenceById: inspectorEvidenceById,
    episodes: report?.data.episodes ?? [],
    relationKind: relationKindFromRecord,
    relationLabel: relationDisplayLabel,
    relationSentence,
  };
  const selectedNodeProjection = selected ? projectNodeDetail(selected, { ...inspectorRelationInput, assertions: visibleAssertions }) : null;
  const selectedAssertionProjection = selectedEdgeRecord
    ? projectAssertionDetail({ ...selectedEdgeRecord, symmetric: selectedEdgeIsSymmetric }, inspectorRelationInput)
    : null;
  const selectedEpisodeProjection = selectedEpisode
    ? projectEpisodeDetail(selectedEpisode, { assertions: visibleAssertions, evidence: report?.data.evidence ?? [], nodeById: inspectorNodeById })
    : null;
  const selectedEvidenceProjection = selectedEvidence
    ? projectEvidenceDetail(selectedEvidence, visibleAssertions, inspectorEpisodeById)
    : null;
  const selectedEdgeNodeIds = new Set([selectedEdge ? endpointId(selectedEdge.source) : "", selectedEdgeTargetId].filter(Boolean));
  // The initial node is only a detail-panel default; it must not turn the whole
  // library into a dimmed focus view before the developer performs an action.
  const hasTransientHighlight = Boolean(selectedEpisodeId || selectedEdgeId || recallView || preview);
  const highlightedNodeIds = new Set([
    ...selectedEpisodeNodeIds,
    ...selectedEdgeNodeIds,
    ...recalledNodeIds,
    ...recalledAssertionNodeIds,
    ...previewNodeIds,
    ...previewAssertionNodeIds,
  ]);
  const typeFilterOrder = ["elfie", "event", "genesis_commit_receipt", "group", "knowledge", "person", "place", "object", "self_model", "literal"];
  const typeFilterOptions = Object.entries(report?.node_type_counts ?? {})
    .sort(([left], [right]) => (typeFilterOrder.indexOf(left) === -1 ? 999 : typeFilterOrder.indexOf(left)) - (typeFilterOrder.indexOf(right) === -1 ? 999 : typeFilterOrder.indexOf(right)) || left.localeCompare(right));
  const predicateFilterOptions = Object.entries(report?.predicate_counts ?? {})
    .sort(([left], [right]) => left.localeCompare(right));
  const typeFilterSelectOptions = typeFilterOptions.map(([kind, count]) => ({
    value: kind,
    label: <span className="memory-debug-filter-option"><i style={{ background: graphNodeColor(kind) }} />{labels[kind] ?? kind}<b>{count}</b></span>,
  }));
  const predicateFilterSelectOptions = predicateFilterOptions.map(([predicate, count]) => ({
    value: predicate,
    label: <span className="memory-debug-filter-option"><span>{predicate}</span><b>{count}</b></span>,
  }));
  const coverageLabel = readPhase === "loading" && !report
    ? "正在读取"
    : readPhase === "partial"
      ? "部分加载，不能代表全库图"
      : readPhase === "empty"
        ? "Memory 为空"
        : readPhase === "stale"
          ? "快照已过期，请刷新"
          : readPhase === "error"
            ? "读取失败，可重试"
            : recallView && showOnlyRecallResults
              ? "搜索命中子图"
            : recallView
              ? "全图搜索高亮"
            : hasLocalFilters
              ? "已按筛选读取"
            : report?.coverage.status === "complete"
              ? "全库已加载"
              : report?.coverage.status === "filtered"
                ? "已按筛选读取"
                : "读取范围未知";
  const loadedNodeCount = report?.loaded_counts.nodes ?? 0;
  const totalNodeCount = report?.counts.nodes ?? 0;
  const matchedNodeCount = report?.matched_counts.nodes ?? 0;
  const loadedEvidenceCount = report?.loaded_counts.evidence ?? 0;
  const totalEvidenceCount = report?.counts.evidence ?? 0;
  const graphNodeCount = report?.counts.graph_nodes ?? loadedNodeCount;
  const focusNodeCount = report?.counts.focus_nodes ?? matchedNodeCount;
  const contextNodeCount = hasLocalFilters ? Math.max(filterContextNodeIds.size, graphNodeCount - focusNodeCount) : 0;
  const coverageDetail = recallView && showOnlyRecallResults
    ? `搜索子图 ${graph.nodes.length} · 命中 Episode ${recalledEpisodeIds.size} · 全库 ${totalNodeCount}`
    : recallView
    ? `相关节点 ${recalledFocusNodeGroups.ranked.length} · 零分 ${recalledFocusNodeGroups.zeroScore.length} · 未评分 ${recalledFocusNodeGroups.unscored.length} · 命中关系 ${recalledAssertionIds.size} · 全库 ${totalNodeCount}`
    : hasLocalFilters
    ? `焦点 ${focusNodeCount} · 上下文 ${contextNodeCount} · 全库 ${totalNodeCount}`
    : `当前 ${loadedNodeCount} · 全库 ${totalNodeCount}`;
  const recallSummary = recallView?.selection.summaries.at(-1) ?? null;
  const recallLimits = recallView?.bundle.limits ?? null;
  const requestQueryTerms = recordStringArray(recallView?.request ?? null, "query_terms");
  const candidateQueryTerms = [...new Set((recallView?.selection.candidates ?? []).flatMap((candidate) => candidate.query_terms ?? candidate.matched_terms ?? []))];
  const recallQueryTerms = requestQueryTerms.length ? requestQueryTerms : candidateQueryTerms;
  const Graph3D = ForceGraph3DComponent;
  const recallProcess = [
    { label: "查询", detail: query.trim() ? "已输入" : "等待输入", state: query.trim() ? "done" : "idle" },
    { label: "候选", detail: recallView ? `${recallView.selection.candidates.length} 个` : "等待执行", state: recallView ? "done" : "idle" },
    { label: "评分 / 过滤", detail: recallView ? "已完成" : "等待候选", state: recallView ? "done" : "idle" },
    { label: "RecallBundle", detail: recallView ? "已生成" : "等待回执", state: recallView ? "done" : "idle" },
  ];
  const addProcess = [
    { label: "接收 / 校验", detail: episodeText.trim() ? "输入已填写" : "等待输入", state: episodeText.trim() ? "done" : "idle" },
    { label: "来源写入", detail: preview ? "隔离副本" : "未观测", state: preview ? "done" : "unobserved" },
    { label: "提取候选知识", detail: preview ? "未接入细粒度 trace" : "未观测", state: "unobserved" },
    { label: "生成 Evidence", detail: preview ? `${preview.changes.added_ids.evidence?.length ?? 0} 条新增` : "未观测", state: preview ? "done" : "unobserved" },
    { label: "创建 / 更新 Node", detail: preview ? `${preview.changes.added_ids.nodes?.length ?? 0} 个新增` : "未观测", state: preview ? "done" : "unobserved" },
    { label: "创建 / 更新 Assertion", detail: preview ? `${preview.changes.added_ids.assertions?.length ?? 0} 条新增` : "未观测", state: preview ? "done" : "unobserved" },
    { label: "Consolidation", detail: preview ? "由回执汇总" : "未观测", state: preview ? "done" : "unobserved" },
    { label: "Maintenance / 冲突", detail: preview ? "细节未观测" : "未观测", state: "unobserved" },
    { label: "结果快照", detail: preview ? preview.operation.status : "等待回执", state: preview ? "done" : "idle" },
  ];

  function handleGraphNodeClick(node: Graph3DNode): void {
    const nodeId = String(node.originalId ?? node.id ?? "");
    if (node.preview) {
      setMessage(`隔离预演节点：${node.label}`);
      return;
    }
    setSelectedEvidenceId("");
    const item = report?.data.nodes.find((candidate) => candidate.id === nodeId);
    if (item) showItem(item.id);
    else if (node.kind === "literal") {
      setSelectedEdgeId(nodeId.replace(/^literal:/, ""));
      setSelectedId("");
      setSelectedEpisodeId("");
      setDetailSelection("edge");
      setDetailPanelOpen(true);
    } else setMessage(node.label);
  }

  function handleGraphLinkClick(link: Graph3DLink): void {
    setSelectedEdgeId(String(link.id ?? ""));
    setSelectedId("");
    setSelectedEpisodeId("");
    setSelectedEvidenceId("");
    setDetailSelection("edge");
    setDetailPanelOpen(true);
  }

  const fallbackHighlightedNodeIds = new Set([
    ...recalledNodeIds,
    ...selectedEpisodeNodeIds,
    ...previewNodeIds,
    ...previewAssertionNodeIds,
    ...selectedEdgeNodeIds,
    ...recalledAssertionNodeIds,
    ...highlightedNodeIds,
  ]);
  const fallbackHighlightedEdgeIds = new Set([
    ...selectedEpisodeAssertionIds,
    ...previewAssertionIds,
    ...recalledAssertionIds,
  ]);
  const graphFallback = <MemoryDebugGraphFallback
    graphData={graphData}
    selectedId={selectedId}
    selectedEdgeId={selectedEdgeId}
    highlightedNodeIds={fallbackHighlightedNodeIds}
    highlightedEdgeIds={fallbackHighlightedEdgeIds}
    hasTransientHighlight={hasTransientHighlight}
    onNodeClick={handleGraphNodeClick}
    onLinkClick={handleGraphLinkClick}
  />;

  return <main className={`memory-debug-page${embedded ? " memory-debug-page-embedded" : ""}${filterOpen ? " memory-debug-filter-open" : ""}${leftPanelOpen ? " memory-debug-left-panel-open" : ""}${detailPanelOpen ? " memory-debug-right-panel-open" : ""}${leftPanelOpen && detailPanelOpen ? " memory-debug-two-drawers" : ""}`}>
    <div className="memory-debug-graph-canvas" ref={graphCanvasRef} aria-label="真实记忆来源链">
      <header className="memory-debug-topbar">
        <div className="memory-debug-search-group">
          <div className="memory-debug-top-search">
            <span aria-hidden="true">⌕</span>
            <input aria-label="搜索记忆" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void runRecall(); }} placeholder="搜索 Node、Assertion、Episode…" />
            {query ? <button type="button" className="memory-debug-search-clear" aria-label="清除搜索" title="清除搜索" onClick={() => clearSearch()}>×</button> : null}
            <button type="button" onClick={() => void runRecall()}>搜索</button>
          </div>
          <button type="button" className={`memory-debug-filter-trigger${filterOpen ? " is-active" : ""}`} aria-expanded={filterOpen} onClick={openFilter}>过滤{activeFilterCount ? ` · ${activeFilterCount}` : ""}</button>
        </div>
        <div className="memory-debug-top-actions">
          <button type="button" className="is-primary" onClick={openAddPanel}>＋ 添加 Episode</button>
          <button type="button" className="memory-debug-consolidation-trigger" onClick={() => void runManualConsolidation()} disabled={!elfieId || consolidationRunning} title="手动触发一次夜间 Consolidation；不会伪造用户 Episode" aria-label="手动触发 Consolidation">{consolidationRunning ? "整理中…" : "手动 Consolidation"}</button>
          {recallView && <button type="button" className={showOnlyRecallResults ? "is-active" : ""} aria-pressed={showOnlyRecallResults} onClick={() => setShowOnlyRecallResults((visible) => !visible)} title={showOnlyRecallResults ? "显示完整 Memory 图谱" : "只显示本次搜索结果"}>{showOnlyRecallResults ? "显示完整图谱" : "仅看搜索结果"}</button>}
          <button type="button" className={layoutLocked ? "is-active" : ""} aria-pressed={layoutLocked} title={layoutLocked ? "允许拖拽节点位置；相机仍需按住鼠标拖动旋转" : "锁定节点位置；相机仍可按住鼠标拖动旋转"} aria-label={layoutLocked ? "允许拖拽节点" : "锁定节点"} onClick={() => setLayoutLocked((locked) => !locked)}>{layoutLocked ? "允许拖拽节点" : "锁定节点"}</button>
          <button type="button" onClick={() => fitGraph()} title="重新居中并缩放当前可见的连通图" aria-label="适配当前图谱">适配当前图谱</button>
          <button type="button" onClick={resetGraph} title="清除选择、Recall 和预演状态，并重新适配图谱" aria-label="重置视图状态">重置视图</button>
          {embedded && onClose ? <button type="button" className="memory-debug-topbar-close" onClick={onClose} aria-label="关闭记忆图谱浮窗" title="关闭记忆图谱">×</button> : null}
        </div>
      </header>

      {filterOpen && <section className="memory-debug-filter-popover" aria-label="过滤记忆图">
        <div className="memory-debug-filter-head"><div><strong>过滤条件</strong><span>这里只筛选当前图谱；文字检索使用顶部搜索框。枚举字段支持多选。</span></div><button type="button" aria-label="关闭过滤" onClick={() => setFilterOpen(false)}>×</button></div>
        <div className="memory-debug-filter-grid">
          <label>节点类型（可多选）<Select aria-label="节点类型" mode="multiple" allowClear maxTagCount="responsive" onChange={(values: string[]) => setSelectedTypes(values)} options={typeFilterSelectOptions} placeholder="全部节点类型" popupClassName="memory-debug-filter-select-dropdown" popupMatchSelectWidth={false} value={selectedTypes} /></label>
          <label>关系类型（可多选）<Select aria-label="关系类型" mode="multiple" allowClear maxTagCount="responsive" onChange={(values: string[]) => setSelectedPredicates(values)} options={predicateFilterSelectOptions} placeholder="全部关系类型" popupClassName="memory-debug-filter-select-dropdown" popupMatchSelectWidth={false} value={selectedPredicates} /></label>
          <label>生命周期<Select aria-label="生命周期" onChange={(value: string) => setLifecycleFilter(value || "all")} options={[{ label: "全部", value: "all" }, { label: "活动 active", value: "active" }, { label: "已归档 archived", value: "archived" }, { label: "已遗忘 forgotten", value: "forgotten" }, { label: "未知 unknown", value: "unknown" }]} popupClassName="memory-debug-filter-select-dropdown" popupMatchSelectWidth={false} value={lifecycleFilter} /></label>
          <label>最低置信度<Select aria-label="最低置信度" onChange={(value: string) => setConfidenceFilter(value || "all")} options={[{ label: "全部", value: "all" }, { label: "≥ 50%", value: "0.5" }, { label: "≥ 80%", value: "0.8" }]} popupClassName="memory-debug-filter-select-dropdown" popupMatchSelectWidth={false} value={confidenceFilter} /></label>
        </div>
        <div className="memory-debug-filter-actions"><button type="button" onClick={() => { clearFilters(); setFilterOpen(false); }} disabled={!hasLocalFilters}>清除筛选</button></div>
      </section>}

      {readError && <div className={`memory-debug-read-notice memory-debug-read-notice-${readPhase}`} role="alert"><strong>{readPhase === "stale" ? "读取边界已过期" : readPhase === "error" ? "Memory 读取失败" : "Memory 读取状态"}</strong><span>{readError}</span><button onClick={() => void loadReport()}>重试</button></div>}
      {readPhase === "empty" && <div className="memory-debug-read-notice memory-debug-read-notice-empty" role="status"><strong>当前 Memory 为空</strong><span>没有可绘制的 Episode、Node、Assertion 或 Evidence；可以打开右侧“添加 Episode”做隔离预演。</span></div>}

      {loading && !report ? <div className="memory-debug-empty">正在读取真实 Memory…</div> : <>
          <div className="memory-debug-memory-cards" aria-label="Episode 时间线">{visibleEpisodes.map((episode) => {
            const episodeId = String(episode.episode_id);
            const isSelected = selectedEpisodeId === episodeId;
            const summary = String(episode.content_text ?? episode.episode_id);
            const evidenceCount = (report?.data.evidence ?? []).filter((item) => String(item.source_id ?? "") === episodeId).length;
            return <button ref={(element) => { if (element) episodeCardRefs.current.set(episodeId, element); else episodeCardRefs.current.delete(episodeId); }} className={isSelected ? "is-active" : ""} key={episodeId} title={summary} onClick={() => showEpisode(episodeId)} aria-pressed={isSelected}>
              <span className="memory-debug-episode-time">{formatEpisodeTime(episode)}</span>
              <strong className="memory-debug-episode-title">{summary}</strong>
              <span className="memory-debug-episode-meta">{recordText(episode, "event_kind", "Episode")} · {recordText(episode, "lifecycle", "unknown")} · {evidenceCount} Evidence</span>
            </button>;
          })}</div>
          <div
            className="memory-debug-3d-layer"
            role="img"
            aria-label="可旋转、缩放、拖拽节点的三维记忆知识图谱"
            onPointerDownCapture={(event) => setGraphNavigationEnabled(graphNavigationActive(event.pointerType, event.buttons))}
            onPointerMoveCapture={(event) => setGraphNavigationEnabled(graphNavigationActive(event.pointerType, event.buttons))}
            onPointerUpCapture={() => setGraphNavigationEnabled(false)}
            onPointerCancelCapture={() => setGraphNavigationEnabled(false)}
            onWheelCapture={() => {
              // Allow the current wheel event to reach OrbitControls, then
              // immediately return to the hover-safe state. Without this
              // reset, one wheel zoom would re-enable hover rotation.
              setGraphNavigationEnabled(true);
              window.requestAnimationFrame(() => setGraphNavigationEnabled(false));
            }}
          >
            {webglStatus === "checking" ? <div className="memory-debug-3d-loading">正在检查浏览器 3D 能力…</div> : webglStatus === "available" && Graph3D ? <WebGLGraphErrorBoundary fallback={graphFallback}><Graph3D
              ref={graphRef}
              graphData={graphData}
              width={graphViewport.width || 800}
              height={graphViewport.height || 580}
              backgroundColor="#07131f"
              nodeRelSize={3.1}
              nodeVal={(node) => node.val}
              nodeColor={(node) => {
                const nodeId = String(node.id ?? "");
                const isSelected = selectedId === nodeId;
                const isReturned = recalledNodeIds.has(nodeId);
                const isAffected = selectedEpisodeNodeIds.has(nodeId) || previewNodeIds.has(nodeId) || previewAssertionNodeIds.has(nodeId);
                const isRelated = selectedEdgeNodeIds.has(nodeId) || recalledAssertionNodeIds.has(nodeId);
                const isHighlighted = isSelected || isReturned || isAffected || isRelated || highlightedNodeIds.has(nodeId);
                if (hasTransientHighlight && !isHighlighted) return "rgba(97, 123, 143, 0.22)";
                if (node.preview) return "#ff9d57";
                return graphNodeColor(node.kind);
              }}
              nodeLabel={(node) => `<strong>${escapeHtml(node.label)}</strong><br/><small>${escapeHtml(node.kind)} · ${node.degree} 条关系${node.preview ? " · 隔离预演" : ""}</small>`}
              nodeThreeObject={nodeLabelObject}
              nodeThreeObjectExtend
              linkLabel={(link) => `<strong>Assertion</strong><br/>${escapeHtml(link.label)}${link.evidenceIds?.length ? `<br/><small>${link.evidenceIds.length} 条 Evidence</small>` : ""}`}
              linkColor={(link) => {
                const linkId = String(link.id ?? "");
                const isReturned = recalledAssertionIds.has(linkId);
                const isAffected = selectedEpisodeAssertionIds.has(linkId) || previewAssertionIds.has(linkId) || link.kind === "preview-assertion";
                return graphLinkColor(hasTransientHighlight, selectedEdgeId, linkId, link.kind, isReturned, isAffected);
              }}
              linkWidth={(link) => {
                return graphLinkWidth(link.importance);
              }}
              linkDirectionalArrowLength={(link) => {
                const linkId = String(link.id ?? "");
                const isReturned = recalledAssertionIds.has(linkId);
                const isAffected = selectedEpisodeAssertionIds.has(linkId) || previewAssertionIds.has(linkId) || link.kind === "preview-assertion";
                return link.symmetric ? 0 : graphLinkArrowLength(hasTransientHighlight, selectedEdgeId, linkId, link.kind, isReturned, isAffected);
              }}
              linkDirectionalArrowColor={(link) => {
                const linkId = String(link.id ?? "");
                const isReturned = recalledAssertionIds.has(linkId);
                const isAffected = selectedEpisodeAssertionIds.has(linkId) || previewAssertionIds.has(linkId) || link.kind === "preview-assertion";
                return graphLinkArrowColor(hasTransientHighlight, selectedEdgeId, linkId, link.kind, isReturned, isAffected);
              }}
              linkOpacity={0.76}
              linkResolution={6}
              linkHoverPrecision={8}
              showNavInfo={false}
              controlType={MEMORY_DEBUG_GRAPH_CONTROL_TYPE}
              enableNodeDrag={!layoutLocked}
              enableNavigationControls={false}
              d3AlphaDecay={0.08}
              d3VelocityDecay={0.68}
              // Keep the previous total layout budget (60 warmup + 90
              // cooldown) while making the final layout static. Otherwise
              // stopping the cooldown early leaves the graph too compact.
              warmupTicks={150}
              // Keep settled 3D positions stable after visual-only changes
              // such as selecting an Episode. react-force-graph restarts its
              // update cycle when callback props change; a second cooldown
              // here makes the whole graph drift during inspection.
              cooldownTicks={0}
              cooldownTime={2600}
              onEngineTick={updateTracePositions}
              onEngineStop={() => { updateTracePositions(); if (graphFitPendingRef.current) fitGraph(); }}
              onNodeClick={handleGraphNodeClick}
              onLinkClick={handleGraphLinkClick}
            /></WebGLGraphErrorBoundary> : graphFallback}
            {webglStatus === "available" && Graph3D && graphData.nodes.length > 0 && !graphFitReady && <div className="memory-debug-3d-loading memory-debug-3d-loading-overlay">正在稳定 3D 布局…</div>}
          </div>
          {selectedEpisode && <svg className="memory-debug-trace-overlay" aria-label="Episode 证据连线">
            {Array.from(selectedEpisodeNodeIds).map((nodeId) => {
              const point = tracePositions[nodeId];
              if (!point) return null;
              const canvas = graphCanvasRef.current;
              const card = episodeCardRefs.current.get(selectedEpisodeId);
              const canvasRect = canvas?.getBoundingClientRect();
              const cardRect = card?.getBoundingClientRect();
              const source = canvasRect && cardRect
                ? episodeTraceSourcePoint(cardRect, canvasRect)
                : { x: (visibleEpisodes.findIndex((episode) => String(episode.episode_id) === selectedEpisodeId) + .5) / Math.max(1, visibleEpisodes.length) * (canvas?.clientWidth ?? 1000), y: 126 };
              const sourceX = source.x;
              const sourceY = source.y;
              const controlX = (sourceX + point.x) / 2;
              const evidenceId = selectedEpisodeEvidence[0] ? String(selectedEpisodeEvidence[0].evidence_id) : "";
              const path = `M ${sourceX} ${sourceY} C ${controlX} ${sourceY + 18}, ${controlX} ${point.y - 18}, ${point.x} ${point.y}`;
              return <g key={nodeId} className="memory-debug-trace-hit" role={evidenceId ? "button" : undefined} tabIndex={evidenceId ? 0 : undefined} aria-label={evidenceId ? `查看 Evidence ${evidenceId}` : "Evidence trace"} onClick={() => { if (evidenceId) showEvidence(evidenceId); }} onKeyDown={(event) => { if (evidenceId && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); showEvidence(evidenceId); } }}><title>{selectedEpisodeEvidence.map((evidence) => String(evidence.evidence_id)).join(" · ") || "Evidence trace"}</title><path className="memory-debug-trace-hit-line" d={path} /><path className="memory-debug-trace-line" d={path} /><circle className="memory-debug-trace-dot" cx={point.x} cy={point.y} r="4" /></g>;
            })}
          </svg>}
          <MemoryDebugLegend layoutLocked={layoutLocked} />
        </>}
      <footer className="memory-debug-footer">当前视图：{graph.nodes.filter((node) => !["episode", "evidence"].includes(node.kind)).length} Node · {graph.edges.filter((edge) => edge.kind === "assertion").length} Assertion · {visibleEpisodes.length} Episode · {loadedEvidenceCount} Evidence　|　全库：{totalNodeCount} Node · {report?.counts.assertions ?? 0} Assertion · {report?.counts.episodes ?? 0} Episode · {totalEvidenceCount} Evidence</footer>

      {detailPanelOpen && <aside className="memory-debug-drawer memory-debug-drawer-right" aria-label="详情面板">
        <div className="memory-debug-drawer-head"><div><span>INSPECTOR · DETAIL</span><strong>详情</strong></div><div className="memory-debug-drawer-head-actions"><button type="button" aria-label="关闭详情面板" onClick={() => setDetailPanelOpen(false)}>×</button></div></div>
        <div className="memory-debug-inspector-context"><span>当前对象</span><strong>{detailSelection === "episode" && selectedEpisode ? "Episode 来源" : detailSelection === "edge" && selectedEdge ? "Assertion 关系" : detailSelection === "evidence" && selectedEvidence ? "Evidence 证据" : detailSelection === "node" && selected ? `${nodeLabel(selected)} Node` : "未选择"}</strong><small>{coverageLabel} · {coverageDetail}</small></div>
        <div className="memory-debug-drawer-scroll">
        <div className="memory-debug-panel">
          {detailSelection === "episode" && selectedEpisode && selectedEpisodeProjection ? <>
            <InspectorHeaderSummary header={selectedEpisodeProjection.header} className="memory-debug-episode-type" />
            <InspectorFieldGrid fields={projectedFields(selectedEpisodeProjection.fields)} />
            <h4>关联对象</h4>
            <InspectorConnections connections={selectedEpisodeProjection.connections} />
            <h4>来源证据 · {selectedEpisodeEvidence.length}</h4>
            {selectedEpisodeEvidence.length ? selectedEpisodeEvidence.map((item) => <button className="memory-debug-evidence-card" type="button" key={String(item.evidence_id)} onClick={() => showEvidence(String(item.evidence_id))}><strong>{String(item.evidence_id)}</strong><span>{String(item.excerpt ?? "没有摘录")}</span><small>{String(item.modality ?? "text")} · {String(item.attribution ?? item.stance ?? "未标注")} · {String(item.source_reliability_class ?? "可靠性未记录")}</small></button>) : <p>当前 Episode 尚未关联可见 Evidence。</p>}
            <details className="memory-debug-content-details"><summary>展开完整 Episode 正文</summary><p className="memory-debug-long-content">{selectedEpisodeProjection.content}</p></details>
            <details className="memory-debug-raw-details"><summary>技术详情</summary><InspectorFieldGrid fields={projectedFields(selectedEpisodeProjection.technical)} /><div className="memory-debug-detail-list">{selectedEpisodeSourceRefs.map((source, index) => <div key={String(source.source_id ?? index)}><span>{recordText(source, "source_kind", "source")}</span><strong>{recordText(source, "source_id")}{source.locator ? ` · ${String(source.locator)}` : ""}</strong></div>)}</div></details>
          </> : detailSelection === "edge" && selectedEdge && selectedAssertionProjection ? <>
            <InspectorHeaderSummary header={selectedAssertionProjection.header} className="memory-debug-relation-type" />
            <p className="memory-debug-detail-copy memory-debug-relation-sentence">{selectedAssertionProjection.sentence}</p>
            <InspectorFieldGrid fields={projectedFields(selectedAssertionProjection.fields)} />
            <h4>来源证据 · {selectedEdgeEvidence.length}</h4>
            {selectedEdgeEvidence.length ? selectedEdgeEvidence.map((item) => <button className="memory-debug-evidence-card" type="button" key={String(item?.evidence_id)} onClick={() => showEvidence(String(item?.evidence_id))}><strong>{String(item?.evidence_id)}</strong><span>{String(item?.excerpt ?? "没有摘录")}</span><small>{String(item?.source_type ?? "source")} · {String(item?.modality ?? "text")} · {String(item?.attribution ?? item?.stance ?? "未标注")}</small></button>) : <p>这条关系没有关联 Evidence。</p>}
            <details className="memory-debug-raw-details"><summary>技术详情与原始限定条件</summary><InspectorFieldGrid fields={projectedFields(selectedAssertionProjection.technical)} /></details>
          </> : detailSelection === "evidence" && selectedEvidence && selectedEvidenceProjection ? <>
            <InspectorHeaderSummary header={selectedEvidenceProjection.header} className="memory-debug-evidence-type" />
            <blockquote className="memory-debug-edge-evidence memory-debug-evidence-hero">{selectedEvidenceProjection.excerpt}</blockquote>
            <InspectorFieldGrid fields={projectedFields(selectedEvidenceProjection.fields)} />
            <h4>关联对象</h4>
            <InspectorConnections connections={selectedEvidenceProjection.connections} onAssertion={(id) => { setSelectedEvidenceId(""); setSelectedId(""); setSelectedEdgeId(id); setDetailSelection("edge"); setDetailPanelOpen(true); }} />
            <details className="memory-debug-raw-details"><summary>技术详情</summary><InspectorFieldGrid fields={projectedFields(selectedEvidenceProjection.technical)} /></details>
          </> : detailSelection === "node" && selected && selectedNodeProjection ? <>
            <InspectorHeaderSummary header={selectedNodeProjection.header} />
            <InspectorFieldGrid fields={projectedFields(selectedNodeProjection.fields)} />
            <h4>相关关系 · {selectedNodeProjection.connections.length}</h4>
            <InspectorConnections connections={selectedNodeProjection.connections} onAssertion={(id) => { setSelectedId(""); setSelectedEvidenceId(""); setSelectedEdgeId(id); setDetailSelection("edge"); setDetailPanelOpen(true); }} />
            <h4>来源证据 · {selectedNodeEvidence.length}</h4>
            {selectedNodeEvidence.length ? selectedNodeEvidence.map((item) => <button className="memory-debug-evidence-card" type="button" key={String(item.evidence_id)} onClick={() => showEvidence(String(item.evidence_id))}><strong>{String(item.evidence_id)}</strong><span>{String(item.excerpt ?? "没有摘录")}</span></button>) : <p>当前节点没有从可见关系追溯到 Evidence。</p>}
            <h4>被哪些 Episode 提到 · {selectedNodeProjection.sources.length}</h4>
            <InspectorSources sources={selectedNodeProjection.sources} onEpisode={showEpisode} />
            <details className="memory-debug-raw-details"><summary>技术详情</summary><InspectorFieldGrid fields={projectedFields(selectedNodeProjection.technical)} /></details>
          </> : <div className="memory-debug-empty-state"><strong>未选择对象</strong><span>点击左侧 Episode、Node 或 Assertion 查看事实、来源和关联。</span></div>}
        </div>
        </div>
      </aside>}

      {leftPanelOpen && <aside className="memory-debug-drawer memory-debug-drawer-left" aria-label={tab === "add" ? "添加 Episode 面板" : "搜索结果面板"}>
        <div className="memory-debug-drawer-head"><div><span>MEMORY · WORKSPACE</span><strong>{tab === "add" ? "添加 Episode" : "搜索结果"}</strong></div><div className="memory-debug-drawer-head-actions"><button type="button" aria-label={tab === "add" ? "关闭添加 Episode 面板" : "关闭搜索结果面板"} onClick={() => setLeftPanelOpen(false)}>×</button></div></div>
        <div className="memory-debug-inspector-context"><span>{tab === "add" ? "当前操作" : "当前搜索"}</span><strong>{tab === "add" ? "隔离预演 · 不写生产库" : "按相关性排序的搜索结果"}</strong><small>{coverageLabel} · {coverageDetail}</small></div>
        <div className="memory-debug-drawer-scroll">
        {tab === "add" && <div className="memory-debug-panel">
          <h2>添加完整 Episode</h2>
          <p>输入有上下文、有头尾的完整故事，在隔离副本中观察 Episode → Evidence → Node / Assertion 的结果。</p>
          <div className="memory-debug-operation-banner"><strong>隔离预演</strong><span>只读复制生产库 · 不写入生产 Memory · operation trace 未接入的步骤标记为“未观测”</span></div>
          <label className="memory-debug-field-label">Episode 内容<textarea value={episodeText} onChange={(event) => setEpisodeText(event.target.value)} placeholder="例如：今天我在花园散步，发现自己喜欢安静的雨声。" rows={8} /></label>
          <button className="primary" disabled={previewLoading || !episodeText.trim()} onClick={() => void runEpisodePreview()}>{previewLoading ? "正在隔离预演…" : "开始隔离预演"}</button>
          <div className="memory-debug-process-rail memory-debug-process-rail-long" aria-label="添加 Episode 过程"><div className="memory-debug-process-caption"><strong>处理过程</strong><span>仅显示当前可观测状态</span></div>{addProcess.map((step) => <div className={`memory-debug-process-item is-${step.state}`} key={step.label}><span className="memory-debug-process-dot" /><strong>{step.label}</strong><small>{step.detail}</small></div>)}</div>
          {preview && <div className={`memory-debug-preview memory-debug-preview-${preview.operation.status}`}>
            <div className="memory-debug-preview-head"><strong>{preview.operation.status === "completed" ? "预演成功" : "预演未完成"}</strong><span>{preview.operation.elapsed_ms}ms · {preview.operation.mode}</span></div>
            <div className="memory-debug-operation-meta"><span>operation</span><strong>{preview.operation.operation_id}</strong><span>输入</span><strong>{preview.input.content_chars} chars</strong><span>生产写入</span><strong>{preview.operation.production_mutated ? "是 · 异常" : "否"}</strong></div>
            <p>{preview.operation.production_mutated ? "检测到生产写入，需立即停止审查。" : "sandbox=true · 自动清理 · production_mutated=false"}</p>
            <div className="memory-debug-preview-counts">{(["episodes", "nodes", "assertions", "evidence_for_visible_assertions"] as const).map((key) => <div key={key}><span>{key}</span><strong>{preview.before.counts[key] ?? 0} → {preview.after.counts[key] ?? 0}</strong></div>)}</div>
            <h4>本次新增对象</h4>
            <div className="memory-debug-preview-ids">{Object.entries(preview.changes.added_ids).map(([key, ids]) => <span key={key}>{key}: {ids.length ? ids.join(", ") : "—"}</span>)}</div>
            {preview.error && <pre>{JSON.stringify(preview.error, null, 2)}</pre>}
            <details><summary>真实回执</summary><pre>{JSON.stringify(preview.receipt, null, 2)}</pre></details>
          </div>}
        </div>}
        {tab === "recall" && <div className="memory-debug-panel">
          <h2>搜索结果</h2>
          <div className="memory-debug-drawer-query"><span>搜索内容</span><strong>{query || "尚未输入查询"}</strong><small>结果按相关性排序 · {traceRecall ? "聊天回合 Trace（不重复检索）" : "来自当前精灵的 Memory"}</small></div>
          <button className="primary" disabled={!query.trim()} onClick={() => void runRecall()}>再次执行真实检索</button>
          {recallView && <>
            <div className="memory-debug-metric-grid" aria-label="Recall 返回摘要">
              <div><span>节点</span><strong>{recallView.bundle.focus_nodes.length}</strong><small>Recall 返回</small></div>
              <div><span>Episode</span><strong>{recallView.bundle.episodes.length}</strong><small>命中的故事</small></div>
              <div><span>关系</span><strong>{recallView.bundle.assertions.length}</strong><small>命中的边</small></div>
              <div><span>证据</span><strong>{recallView.bundle.evidence.length}</strong><small>可追溯来源</small></div>
            </div>
            <h4>相关节点 · {recalledFocusNodeGroups.ranked.length}</h4>
            {recalledFocusNodeGroups.ranked.length ? recalledFocusNodeGroups.ranked.slice(0, 8).map((node, index) => <button className="memory-debug-result" key={node.id} onClick={() => showItem(node.id)}><b>{index + 1}</b><span>{node.label}<small>{labels[node.node_type ?? ""] ?? node.node_type ?? "unknown"} · 相关度 {node.relevance == null ? "未提供" : node.relevance.toFixed(2)}</small></span></button>) : <p className="memory-debug-empty-result">没有带正相关度的节点结果。</p>}
          {recalledFocusNodeGroups.zeroScore.length > 0 && <>
            <h4>零分节点 · {recalledFocusNodeGroups.zeroScore.length}</h4>
            <p className="memory-debug-context-note">Recall 回执包含这些节点，但相关度为 0；它们不计作节点命中。若同时是命中关系的端点，图中仍会按关系结果标出。</p>
            {recalledFocusNodeGroups.zeroScore.slice(0, 8).map((node, index) => <button className="memory-debug-result memory-debug-zero-score-result" key={node.id} onClick={() => showItem(node.id)}><b>{recalledFocusNodeGroups.ranked.length + index + 1}</b><span>{node.label}<small>{labels[node.node_type ?? ""] ?? node.node_type ?? "unknown"} · 相关度 {node.relevance?.toFixed(2)}</small></span></button>)}
          </>}
          {recalledFocusNodeGroups.unscored.length > 0 && <>
            <h4>未评分节点 · {recalledFocusNodeGroups.unscored.length}</h4>
            <p className="memory-debug-context-note">这些节点由 Recall 返回，但回执没有提供相关度；保留结果，不据此推断相关性强弱。</p>
            {recalledFocusNodeGroups.unscored.slice(0, 8).map((node, index) => <button className="memory-debug-result" key={node.id} onClick={() => showItem(node.id)}><b>{recalledFocusNodeGroups.ranked.length + recalledFocusNodeGroups.zeroScore.length + index + 1}</b><span>{node.label}<small>{labels[node.node_type ?? ""] ?? node.node_type ?? "unknown"} · 相关度未提供</small></span></button>)}
          </>}
            <h4>命中的 Episode · {recallView.bundle.episodes.length}</h4>
            {recallView.bundle.episodes.length ? recallView.bundle.episodes.slice(0, 5).map((episode, index) => {
              const episodeId = recordText(episode, "episode_id", `episode-${index + 1}`);
              const excerpt = recordText(episode, "excerpt", recordText(episode, "content_text", episodeId));
              return <button className="memory-debug-result memory-debug-episode-result" key={episodeId} onClick={() => showEpisode(episodeId)}><b>{index + 1}</b><span>{excerpt}<small>Episode · 相关度 {recordNumber(episode, "relevance") == null ? "—" : recordNumber(episode, "relevance")?.toFixed(2)} · 重要度 {recordNumber(episode, "importance") == null ? "—" : `${Math.round((recordNumber(episode, "importance") ?? 0) * 100)}%`}</small></span></button>;
            }) : <p className="memory-debug-empty-result">没有直接命中的 Episode；结果可能来自节点本身。</p>}
            <h4>命中的关系 · {recallView.bundle.assertions.length}</h4>
            {recallView.bundle.assertions.length ? recallView.bundle.assertions.slice(0, 6).map((assertion, index) => {
              const assertionId = recordText(assertion, "assertion_id", `assertion-${index + 1}`);
              const source = report?.data.nodes.find((node) => node.id === String(assertion.subject_id ?? ""));
              const target = report?.data.nodes.find((node) => node.id === String(assertion.object_node_id ?? ""));
              const kind = relationKindFromRecord(assertion, recordText(assertion, "predicate", "关系"));
              const sentence = source && target ? relationSentence(source.label, target.label, kind, source.node_type, target.node_type) : `${recordText(assertion, "subject_id")} → ${recordText(assertion, "object_node_id", recordText(assertion, "object_literal"))} · ${relationDisplayLabel(kind)}`;
              return <button className="memory-debug-result" key={assertionId} onClick={() => showAssertion(assertionId)}><b>{index + 1}</b><span>{sentence}<small>关系 · 重要度 {recordNumber(assertion, "importance") == null ? "—" : `${Math.round((recordNumber(assertion, "importance") ?? 0) * 100)}%`}</small></span></button>;
            }) : <p className="memory-debug-empty-result">没有可显示的关系边。</p>}
            <details className="memory-debug-raw-details memory-debug-recall-technical"><summary>查看检索过程（一次 Recall 的解释链）</summary>
              <p className="memory-debug-technical-note">recall_id：{recallView.selection.recall_id ?? "未记录"} · 查询词：{recallQueryTerms.join("、") || "未观测"}</p>
              <div className="memory-debug-process-rail" aria-label="Recall 过程">{recallProcess.map((step) => <div className={`memory-debug-process-item is-${step.state}`} key={step.label}><span className="memory-debug-process-dot" /><strong>{step.label}</strong><small>{step.detail}</small></div>)}</div>
              <div className="memory-debug-observation-grid" aria-label="Recall 观测摘要">
                <div><span>评分候选</span><strong>{recordNumber(recallSummary, "candidates_seen") ?? "未观测"}</strong><small>进入评分</small></div>
                <div><span>保留</span><strong>{recordNumber(recallSummary, "kept") ?? "未观测"}</strong><small>进入 RecallBundle</small></div>
                <div><span>字符预算</span><strong>{recordNumber(recallSummary, "character_budget_used") ?? "未观测"} / {recordNumber(recallSummary, "character_budget_limit") ?? "未观测"}</strong><small>已用 / 上限</small></div>
                <div><span>截断</span><strong>{recordBoolean(recallSummary, "truncated") == null ? (recordBoolean(recallLimits, "truncated") == null ? "未观测" : String(recordBoolean(recallLimits, "truncated"))) : String(recordBoolean(recallSummary, "truncated"))}</strong><small>结果是否截断</small></div>
              </div>
              <h4>候选决定 · 命中与淘汰</h4>
              <div className="memory-debug-selection-list" aria-label="Recall 候选决定">{recallView.selection.candidates.map((candidate, index) => <div className={["memory-debug-selection", candidate.kept ? "is-kept" : "is-excluded"].join(" ")} key={candidate.candidate_kind + ":" + candidate.candidate_id}>
                <div className="memory-debug-selection-head"><strong>{candidate.kept ? "保留" : "排除"}</strong><code>{candidate.candidate_id}</code><span>{candidate.candidate_kind}</span></div>
                <div className="memory-debug-selection-facts"><span>{candidate.rank == null ? `序号 ${index + 1}` : `rank ${candidate.rank}`}</span><span>score {candidate.score.toFixed(3)}</span><span>命中 {candidate.matched_terms?.join("、") || "未观测"}</span></div>
                <small>{candidate.kept ? "进入 RecallBundle" : candidate.exclusion_reason ?? "原因未观测"}</small>
              </div>)}</div>
              <details><summary>原始 Recall 回执</summary><pre className="memory-debug-rendered">{recallView.rendered}</pre></details>
            </details>
          </>}
        </div>}
        </div>
      </aside>}
      {message && <p className="memory-debug-message" role="status">{message}</p>}
    </div>
  </main>;
}
