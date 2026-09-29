import { Component, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { CalendarOutlined, DownOutlined, PlusOutlined, SearchOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { Button, ConfigProvider, DatePicker, Input, InputNumber, Select, TreeSelect } from "antd";
import zhCN from "antd/es/locale/zh_CN";
import dayjs, { type Dayjs } from "dayjs";
import "dayjs/locale/zh-cn.js";
import type { ForceGraphMethods } from "react-force-graph-3d";
import { CanvasTexture, Group, Sprite, SpriteMaterial, Vector3 } from "three";
import "./memory-debug-workspace.css";

dayjs.locale("zh-cn");
import {
  projectAssertionDetail,
  episodeCardDisplayTitle,
  episodeEventKindLabel,
  episodeMaintenanceLabel,
  projectEpisodeDetail,
  projectEvidenceDetail,
  projectNodeDetail,
  stripKnowledgeMemberHeaders,
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
type OntologyGroup = { group_id: string; label: string; color: string; order: number };
type OntologyNodeType = { node_type: string; label: string; group_id: string; color: string; status: string; count: number };
type OntologyPredicate = { self_stance?: boolean; predicate: string; label: string; symmetric: boolean; inverse: string | null; status: string; count: number };
type OntologyCatalog = { revision: string; type_groups: OntologyGroup[]; node_types: OntologyNodeType[]; predicates: OntologyPredicate[]; predicate_aliases: Record<string, string> };
type AuditReport = { database: string; elfie_id: string; snapshot: SnapshotMetadata & { coverage?: string; read_limit?: number; filters_applied?: boolean; next_cursor?: string | null }; counts: Record<string, number>; loaded_counts: Record<string, number>; matched_counts: Record<string, number>; focus_node_ids?: string[]; coverage: { status: string; truncated: Record<string, boolean>; filters_applied: boolean; read_limit: number }; pagination?: { page_size: number; next_cursor: string | null; cursor: string | null }; node_type_counts: Record<string, number>; predicate_counts: Record<string, number>; ontology?: OntologyCatalog; checks: { checks: Array<{ status: string; name: string; detail?: string }> }; data: { nodes: AuditItem[]; context_nodes?: AuditItem[]; assertions: AuditRecord[]; episodes: AuditRecord[]; evidence: AuditRecord[] } };
type RecallReport = { elapsed_ms: number; search_time?: string | null; snapshot: SnapshotMetadata; request?: AuditRecord; counts: Record<string, number | boolean>; bundle: { focus_nodes: AuditItem[]; assertions: AuditRecord[]; episodes: AuditRecord[]; evidence: AuditRecord[]; conflicts?: AuditRecord[]; limits?: AuditRecord }; selection: RecallSelection; rendered: string };
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
type GraphNodeSeed = { id: string; kind: string; label: string; color?: string; typeLabel?: string };
type GraphEdgeDirection = "forward" | "reverse" | "both";
type GraphAssertionEdge = { id: string; source: string; target: string; label: string; predicate?: string; kind: string; evidenceIds?: string[]; symmetric?: boolean; importance?: number };
type GraphEdge = GraphAssertionEdge & {
  assertionIds: string[];
  direction: GraphEdgeDirection;
  labels: string[];
  predicates: string[];
};
type Graph3DNode = GraphNodeSeed & { val: number; degree: number; originalId?: string; preview?: boolean; x?: number; y?: number; z?: number };
type Graph3DLink = GraphEdge;
type GraphNodeOverlay = { signature: string; group: Group; labelSprite?: Sprite };
type GraphFilters = { lifecycle?: string; minConfidence?: number | undefined; nodeGroup?: string | undefined; nodeTypes?: ReadonlySet<string> | undefined; predicateTypes?: ReadonlySet<string> | undefined; includeNodeIds?: ReadonlySet<string> | undefined; includeAssertionIds?: ReadonlySet<string> | undefined };
type ReadPhase = "loading" | "partial" | "ready" | "empty" | "stale" | "error";
type SceneEmotion = "happiness" | "sadness" | "anger" | "fear" | "surprise" | "disgust";

const SCENE_EMOTIONS: readonly { key: SceneEmotion; label: string }[] = [
  { key: "happiness", label: "快乐" },
  { key: "sadness", label: "悲伤" },
  { key: "anger", label: "愤怒" },
  { key: "fear", label: "恐惧" },
  { key: "surprise", label: "惊讶" },
  { key: "disgust", label: "厌恶" },
];

export function isMemoryDebugSearchMode(tab: Tab, leftPanelOpen: boolean): boolean {
  return tab === "recall" && leftPanelOpen;
}

export function isMemoryDebugSemanticNodeType(nodeType: string | undefined, report?: AuditReport | null): boolean {
  return Boolean(nodeType && report?.ontology?.node_types.some((item) => item.node_type === nodeType && item.status === "active"));
}

export function selectMemoryNodeGroup(
  groupId: string,
  _selectedTypes: readonly string[],
  _nodeTypes: readonly OntologyNodeType[],
): { groupId: string; nodeTypes: string[] } {
  return { groupId, nodeTypes: [] };
}

export function selectMemoryNodeTypes(
  selectedTypes: readonly string[],
  currentGroup: string,
  nodeTypes: readonly OntologyNodeType[],
): { groupId: string; nodeTypes: string[] } {
  const compatible = new Set(nodeTypes.filter(item => item.status === "active" && (!currentGroup || item.group_id === currentGroup)).map(item => item.node_type));
  return { groupId: currentGroup, nodeTypes: selectedTypes.filter(type => compatible.has(type)) };
}

export function memoryNodeGroupOptions(ontology?: OntologyCatalog): Array<{ value: string; label: string; title: string }> {
  return [
    { value: "", label: "全部", title: "" },
    ...(ontology?.type_groups ?? []).map(item => ({ value: item.group_id, label: item.label, title: "" })),
    { value: "self_model", label: "自我模型", title: "" },
  ];
}

export function MemoryNodeFilter({ ontology, group, selectedTypes, onGroupChange, onTypesChange }: {
  ontology?: OntologyCatalog | undefined; group: string; selectedTypes: string[];
  onGroupChange: (group: string) => void; onTypesChange: (types: string[]) => void;
}): React.JSX.Element {
  const types = (ontology?.node_types ?? []).filter(type => type.status === "active" && (!group || type.group_id === group)).sort((left, right) => right.count - left.count);
  return <section className="memory-debug-node-filter" aria-label="快捷节点类型筛选">
    <label>类型组<Select aria-label="快捷类型组" size="small" popupClassName="memory-debug-quick-dropdown" value={group} options={memoryNodeGroupOptions(ontology)} onChange={onGroupChange} /></label>
    <div className="memory-debug-type-tags" role="group" aria-label="节点类型多选">
      <button type="button" aria-pressed={!selectedTypes.length} onClick={() => onTypesChange([])}>全部</button>
      {types.map(type => <button type="button" key={type.node_type} aria-pressed={selectedTypes.includes(type.node_type)} onClick={() => onTypesChange(selectedTypes.includes(type.node_type) ? selectedTypes.filter(value => value !== type.node_type) : [...selectedTypes, type.node_type])}><i style={{ background: type.color }} />{type.label}</button>)}
    </div>
  </section>;
}

function normalizedGraphScore(value: number | undefined): number {
  if (value === undefined || !Number.isFinite(value)) return 0.5;
  return Math.min(1, Math.max(0, value));
}

const GRAPH_NODE_REL_SIZE = 3.1;
const GRAPH_NODE_MIN_RADIUS = 3.6;
const GRAPH_NODE_MAX_RADIUS = 7.2;
const GRAPH_LINK_MIN_WIDTH = 0.55;
const GRAPH_LINK_MAX_WIDTH = 2.4;
const GRAPH_ARROW_LENGTH = 10;
const GRAPH_NODE_LABEL_OPACITY = .94;
const GRAPH_NODE_LABEL_RENDER_ORDER = 20;
export const MEMORY_DEBUG_GRAPH_FIT_PADDING = 96;

export function memoryDebugRecallProjectionKey(
  showOnlyRecallResults: boolean,
  recallId: string | null | undefined,
  nodeIds: ReadonlySet<string>,
  assertionNodeIds: ReadonlySet<string>,
  assertionIds: ReadonlySet<string>,
): string {
  if (!showOnlyRecallResults) return "";
  return [
    "active",
    recallId ?? "active",
    [...nodeIds].sort().join(","),
    [...assertionNodeIds].sort().join(","),
    [...assertionIds].sort().join(","),
  ].join("|");
}

export const GRAPH_SELECTED_LINK_COLOR = "#e8fbff";
const GRAPH_SELECTED_NODE_RING_COLOR = "#e8fbff";

type GraphScreenRect = { left: number; right: number; top: number; bottom: number };
type GraphLabelOcclusionEntry = {
  id: string;
  depth: number;
  center: { x: number; y: number };
  radius: number;
  label?: GraphScreenRect;
};

function graphCircleIntersectsRect(
  center: { x: number; y: number },
  radius: number,
  rect: GraphScreenRect,
): boolean {
  const nearestX = Math.max(rect.left, Math.min(center.x, rect.right));
  const nearestY = Math.max(rect.top, Math.min(center.y, rect.bottom));
  const dx = center.x - nearestX;
  const dy = center.y - nearestY;
  return dx * dx + dy * dy <= radius * radius;
}

/**
 * Keep labels atomic: a nearer node hides the whole rear label when its
 * projected sphere reaches the label rectangle. This avoids Three's normal
 * per-fragment depth test cutting a CanvasTexture through the middle of text.
 */
export function graphVisibleLabelIds(entries: readonly GraphLabelOcclusionEntry[]): ReadonlySet<string> {
  const visible = new Set(entries.filter((entry) => entry.label).map((entry) => entry.id));
  entries.forEach((target) => {
    if (!target.label || !Number.isFinite(target.depth)) return;
    const occluded = entries.some((occluder) => {
      if (occluder.id === target.id || !Number.isFinite(occluder.depth)) return false;
      if (occluder.depth >= target.depth) return false;
      return graphCircleIntersectsRect(occluder.center, Math.max(0, occluder.radius), target.label!);
    });
    if (occluded) visible.delete(target.id);
  });
  return visible;
}

/**
 * ForceGraph interprets nodeVal as a volume and applies a cube root to get the
 * sphere radius. Cube the intended radius here so memory salience remains
 * visible instead of being compressed by that renderer transform.
 */
export function graphNodeValue(importance: number | undefined): number {
  const radius = GRAPH_NODE_MIN_RADIUS + normalizedGraphScore(importance) * (GRAPH_NODE_MAX_RADIUS - GRAPH_NODE_MIN_RADIUS);
  return (radius / GRAPH_NODE_REL_SIZE) ** 3;
}

/** Semantic assertion width represents pairwise relation importance, not selection state. */
export function graphLinkWidth(importance: number | undefined): number {
  return GRAPH_LINK_MIN_WIDTH + normalizedGraphScore(importance) * (GRAPH_LINK_MAX_WIDTH - GRAPH_LINK_MIN_WIDTH);
}

function uniqueStrings(values: readonly (string | undefined)[]): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))];
}

function graphPairEndpoints(source: string, target: string): [string, string] {
  return source.localeCompare(target) <= 0 ? [source, target] : [target, source];
}

/**
 * Collapse visible Assertions into one visual relation per unordered endpoint
 * pair. The individual Assertion ids remain attached so selection, Recall
 * highlighting and the inspector can still resolve the original facts.
 */
function aggregateGraphEdges(assertionEdges: readonly GraphAssertionEdge[]): GraphEdge[] {
  const groups = new Map<string, { left: string; right: string; edges: GraphAssertionEdge[] }>();
  assertionEdges.forEach((edge) => {
    const [left, right] = graphPairEndpoints(edge.source, edge.target);
    const key = `${left}::${right}`;
    const group = groups.get(key);
    if (group) group.edges.push(edge);
    else groups.set(key, { left, right, edges: [edge] });
  });

  return [...groups.entries()].map(([key, group]) => {
    const members = [...group.edges].sort((left, right) => left.id.localeCompare(right.id));
    const symmetric = members.some((edge) => edge.symmetric);
    const forward = members.some((edge) => edge.source === group.left && edge.target === group.right);
    const reverse = members.some((edge) => edge.source === group.right && edge.target === group.left);
    const hasForward = forward || symmetric;
    const hasReverse = reverse || symmetric;
    const direction: GraphEdgeDirection = hasForward && hasReverse ? "both" : hasReverse ? "reverse" : "forward";
    const labels = uniqueStrings(members.flatMap((edge) => [edge.label]));
    const predicates = uniqueStrings(members.flatMap((edge) => [edge.predicate]));
    const primaryLabel = labels[0] ?? "关系";
    const importanceValues = members
      .map((edge) => edge.importance)
      .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
    const evidenceIds = uniqueStrings(members.flatMap((edge) => edge.evidenceIds ?? []));
    return {
      id: `relation:${key}`,
      source: direction === "reverse" ? group.right : group.left,
      target: direction === "reverse" ? group.left : group.right,
      label: labels.length === 1 ? primaryLabel : `${primaryLabel}（${labels.length} 种）`,
      ...(predicates.length === 1 ? { predicate: predicates[0] } : {}),
      kind: members[0]?.kind ?? "assertion",
      evidenceIds,
      ...(symmetric ? { symmetric: true } : {}),
      ...(importanceValues.length ? { importance: Math.max(...importanceValues) } : {}),
      assertionIds: members.map((edge) => edge.id),
      direction,
      labels,
      predicates,
    };
  }).sort((left, right) => left.id.localeCompare(right.id));
}

const DIMMED_LINK_COLOR = "rgba(107, 133, 151, 0.16)";
const GRAPH_LINK_OPACITY = 1;

function graphRenderColor(color: string): string {
  return color === DIMMED_LINK_COLOR ? "#2b4656" : color;
}

export function graphNodeLabelMaterialOptions(): { transparent: boolean; depthWrite: boolean; depthTest: boolean; opacity: number } {
  // The label is rendered as one atomic sprite after the library-owned graph
  // objects. Whole-label occlusion is decided separately, so per-fragment
  // depth testing cannot cut a CanvasTexture through the text.
  return { transparent: true, depthWrite: false, depthTest: false, opacity: GRAPH_NODE_LABEL_OPACITY };
}

type GraphPoint3D = { x: number; y: number; z: number };

type GraphBounds = {
  x: [number, number];
  y: [number, number];
  z: [number, number];
};

export function graphFitCameraTarget(
  bounds: GraphBounds,
  cameraPosition: GraphPoint3D,
  cameraFov: number,
  cameraAspect: number,
  viewportHeight: number,
  padding: number,
): { position: GraphPoint3D; target: GraphPoint3D; distance: number } | null {
  const target = {
    x: (bounds.x[0] + bounds.x[1]) / 2,
    y: (bounds.y[0] + bounds.y[1]) / 2,
    z: (bounds.z[0] + bounds.z[1]) / 2,
  };
  const span = Math.max(1,
    bounds.x[1] - bounds.x[0],
    bounds.y[1] - bounds.y[0],
    bounds.z[1] - bounds.z[0],
  );
  const safeAspect = Number.isFinite(cameraAspect) && cameraAspect > 0 ? cameraAspect : 1;
  const safeViewportHeight = Number.isFinite(viewportHeight) && viewportHeight > 0 ? viewportHeight : 1;
  const safeFov = Number.isFinite(cameraFov) && cameraFov > 0 ? cameraFov : 25;
  const paddedFov = Math.max(1, (1 - (padding * 2) / safeViewportHeight) * safeFov);
  const fitHeightDistance = span / Math.atan((paddedFov * Math.PI) / 180);
  const distance = Math.max(fitHeightDistance, fitHeightDistance / safeAspect);
  if (!Number.isFinite(distance) || distance <= 0) return null;

  const dx = cameraPosition.x - target.x;
  const dy = cameraPosition.y - target.y;
  const dz = cameraPosition.z - target.z;
  const directionLength = Math.hypot(dx, dy, dz);
  const direction = directionLength > 0
    ? { x: dx / directionLength, y: dy / directionLength, z: dz / directionLength }
    : { x: 0, y: 0, z: 1 };
  return {
    target,
    distance,
    position: {
      x: target.x + direction.x * distance,
      y: target.y + direction.y * distance,
      z: target.z + direction.z * distance,
    },
  };
}

function graphPointRadius(point: { val?: number }): number {
  const value = typeof point.val === "number" && Number.isFinite(point.val) ? point.val : 1;
  return Math.cbrt(Math.max(0, value)) * GRAPH_NODE_REL_SIZE;
}

function graphNodeColor(kind: string, report?: AuditReport | null): string {
  return report?.ontology?.node_types.find((item) => item.node_type === kind)?.color ?? (kind === "literal" ? "#a7b7c4" : "#8da9c4");
}

function nodeTypeLabel(kind: string, report?: AuditReport | null): string {
  return report?.ontology?.node_types.find((item) => item.node_type === kind)?.label ?? kind;
}
function nodeLabel(node: AuditItem, report?: AuditReport | null): string { return nodeTypeLabel(node.node_type ?? "unknown", report); }
function escapeHtml(value: string): string { return value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ?? character); }
function normalizeNode(node: AuditItem & { node_id?: string }): AuditItem { return { ...node, id: node.id || node.node_id || "" }; }
function recordArray(record: AuditRecord | null, key: string): AuditRecord[] { const value = record?.[key]; return Array.isArray(value) ? value.filter((item): item is AuditRecord => typeof item === "object" && item !== null && !Array.isArray(item)) : []; }
function recordText(record: AuditRecord | null, key: string, fallback = "—"): string { const value = record?.[key]; return value == null || value === "" ? fallback : String(value); }
function recordNumber(record: AuditRecord | null, key: string): number | null { const value = record?.[key]; return typeof value === "number" && Number.isFinite(value) ? value : null; }
function recordStringArray(record: AuditRecord | null, key: string): string[] { const value = record?.[key]; return Array.isArray(value) ? value.map(String).filter(Boolean) : []; }
function recordLifecycle(record: AuditItem): string { return String(record.status ?? record.properties?.lifecycle ?? record.properties?.status ?? "unknown"); }
export function formatRecallElapsed(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "未记录";
  return value < 1000 ? `${value.toFixed(2)} ms` : `${(value / 1000).toFixed(2)} s`;
}
function relationIsSymmetric(kind: string, report?: AuditReport | null): boolean {
  const canonical = report?.ontology?.predicate_aliases[kind] ?? kind;
  return report?.ontology?.predicates.find((item) => item.predicate === canonical)?.symmetric ?? false;
}
function relationKindFromRecord(record: AuditRecord | null, fallback = "关系", report?: AuditReport | null): string {
  const predicate = recordText(record, "predicate", fallback);
  const aliases = report?.ontology?.predicate_aliases ?? {};
  if (predicate !== "relationship") return aliases[predicate] ?? predicate;
  const qualifiers = record?.qualifiers;
  if (qualifiers && typeof qualifiers === "object" && !Array.isArray(qualifiers)) {
    const context = (qualifiers as Record<string, unknown>).context;
    if (typeof context === "string") {
      const role = context.split(":").pop()?.trim();
      if (role) return aliases[role] ?? role;
    }
  }
  return predicate;
}
export function relationDisplayLabel(kind: string, report?: AuditReport | null): string {
  const canonical = report?.ontology?.predicate_aliases[kind] ?? kind;
  return report?.ontology?.predicates.find((item) => item.predicate === canonical)?.label ?? canonical;
}
export function relationSentence(source: string, target: string, kind: string, sourceKind?: string, targetKind?: string, report?: AuditReport | null): string {
  const normalizedKind = report?.ontology?.predicate_aliases[kind] ?? kind;
  const label = relationDisplayLabel(normalizedKind, report);
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
  const raw = context.raw && typeof context.raw === "object" && !Array.isArray(context.raw)
    ? context.raw as Record<string, unknown>
    : {};
  const searchTime = [raw.captured_at, raw.started_at, raw.occurred_at]
    .find((value): value is string => typeof value === "string" && value.length > 0) ?? null;
  return {
    elapsed_ms: 0,
    search_time: searchTime,
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

export function MemoryDebugLegend({ layoutLocked = true, showSources = false }: { layoutLocked?: boolean; showSources?: boolean }): React.JSX.Element {
  const interactionHint = layoutLocked
    ? "节点位置已锁定 · 按住左键拖动画布旋转 · 滚轮缩放"
    : "节点可拖拽 · 按住左键拖动节点调整位置";
  return <div className="memory-debug-legend-v2" aria-label="图例">
    <span className="memory-debug-scale-key">节点越大越重要，线越粗越重要</span>
    {showSources && <span className="evidence-key">虚线：Episode 来源关联</span>}
    <span className="memory-debug-legend-hint">{interactionHint} · 悬停只查看 · 点击节点/关系查看右侧详情</span>
  </div>;
}

function endpointId(endpoint: unknown): string {
  if (typeof endpoint === "string" || typeof endpoint === "number") return String(endpoint);
  if (typeof endpoint === "object" && endpoint !== null && "id" in endpoint) return String((endpoint as { id: unknown }).id);
  return String(endpoint ?? "");
}
export function formatEpisodeTime(record: AuditRecord): string {
  const value = record.occurred_from ?? record.occurred_at ?? record.occurred_to;
  if (value == null || value === "") {
    const temporalLabel = String(record.temporal_label ?? "").trim();
    if (!temporalLabel) return "时间未记录";
    const translated = ({ before_arrival: "抵达前", on_arrival: "抵达时", arrival: "抵达时" } as Record<string, string>)[temporalLabel];
    const label = translated ?? (/[㐀-鿿]/.test(temporalLabel) ? temporalLabel : "");
    return label ? `${label}（具体时间未记录）` : "时间未记录";
  }
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

function dateOnly(value: unknown): string | null {
  if (typeof value !== "string" && typeof value !== "number" && !(value instanceof Date)) return null;
  const raw = value instanceof Date ? value.toISOString() : String(value).trim();
  const isoDate = raw.match(/^(\d{4}-\d{2}-\d{2})/);
  if (isoDate?.[1] && !Number.isNaN(Date.parse(`${isoDate[1]}T00:00:00Z`))) return isoDate[1];
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString().slice(0, 10);
}

export function memoryRecallDateBounds(episodes: readonly AuditRecord[], today = new Date()): { from: string; to: string } {
  const dates = episodes.flatMap((episode) => [episode.occurred_from, episode.occurred_at, episode.occurred_to])
    .map(dateOnly)
    .filter((value): value is string => value !== null)
    .sort();
  const to = dateOnly(today) ?? new Date().toISOString().slice(0, 10);
  const earliestRecordedDate = dates[0] ?? to;
  return earliestRecordedDate <= to ? { from: earliestRecordedDate, to } : { from: to, to };
}

export function episodeCardTooltip(record: AuditRecord): string {
  const content = stripKnowledgeMemberHeaders(String(record.content_text ?? ""));
  const summary = episodeCardDisplayTitle({ ...record, content_text: content }) || "（空）";
  return [
    `标题：${summary}`,
    `正文：${content || "（空）"}`,
  ].join("\n");
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

export type RecallDisplayResult = Readonly<{
  key: string;
  id: string;
  kind: "node" | "assertion" | "episode";
  title: string;
  summary: string;
  relevance: number | null;
  role: string;
  importance: number | null;
  candidate: RecallCandidate | null;
  related: readonly string[];
  record: AuditItem | AuditRecord;
}>;
export type RecallResultFilter = "all" | RecallDisplayResult["kind"];
export type RecallDisplayResultCounts = Record<RecallResultFilter, number>;

export function countRecallDisplayResults(results: readonly RecallDisplayResult[]): RecallDisplayResultCounts {
  const counts: RecallDisplayResultCounts = { all: results.length, node: 0, episode: 0, assertion: 0 };
  results.forEach((result) => { counts[result.kind] += 1; });
  return counts;
}

export function filterRecallDisplayResults(results: readonly RecallDisplayResult[], filter: RecallResultFilter): RecallDisplayResult[] {
  return filter === "all" ? [...results] : results.filter((result) => result.kind === filter);
}

export type RecallSearchFilters = Readonly<{
  recordKinds: readonly string[];
  nodeTypes: readonly string[];
  relationTypes: readonly string[];
  occurredFrom: string;
  occurredTo: string;
  minimumImportance: number | null;
  placeNodeId?: string | undefined;
  sense?: { emotion_label: SceneEmotion; intensity: number } | undefined;
}>;

type RecallObjectTreeNode = {
  title: ReactNode;
  value: string;
  key: string;
  children?: RecallObjectTreeNode[];
  disableCheckbox?: boolean;
  selectable?: boolean;
};

export function buildRecallObjectTree(ontology?: OntologyCatalog): RecallObjectTreeNode[] {
  const activeNodeTypes = (ontology?.node_types ?? []).filter((item) => item.status === "active");
  const nodeGroups: RecallObjectTreeNode[] = (ontology?.type_groups ?? [])
    .slice()
    .sort((left, right) => left.order - right.order)
    .map((group) => ({
      title: group.label,
      value: `slice:${group.group_id}`,
      key: `slice:${group.group_id}`,
      children: activeNodeTypes
        .filter((item) => item.group_id === group.group_id)
        .map((item) => ({
          title: item.label,
          value: `node:${item.node_type}`,
          key: `node:${item.node_type}`,
        })),
    }));
  nodeGroups.push({
    title: "自我模型",
    value: "slice:self_model",
    key: "slice:self_model",
    disableCheckbox: true,
    selectable: false,
  });
  const predicates = (ontology?.predicates ?? [])
    .filter((item) => item.status === "active")
    .map((item) => ({
      title: item.label,
      value: `relation:${item.predicate}`,
      key: `relation:${item.predicate}`,
    }));

  return [
    { title: "经历", value: "kind:episode", key: "kind:episode" },
    { title: "节点", value: "kind:node", key: "kind:node", children: nodeGroups },
    { title: "关系", value: "kind:assertion", key: "kind:assertion", children: predicates },
  ];
}

export function recallFiltersFromObjectSelection(
  values: readonly string[],
  ontology?: OntologyCatalog,
): Pick<RecallSearchFilters, "recordKinds" | "nodeTypes" | "relationTypes"> {
  const selected = new Set(values);
  const selectedNodeTypes = new Set<string>();
  const selectedRelations = new Set<string>();
  const includeEpisodes = selected.has("kind:episode");
  let includeNodes = selected.has("kind:node");
  let includeAssertions = selected.has("kind:assertion");

  for (const group of ontology?.type_groups ?? []) {
    if (selected.has(`slice:${group.group_id}`)) {
      includeNodes = true;
      (ontology?.node_types ?? [])
        .filter((item) => item.status === "active" && item.group_id === group.group_id)
        .forEach((item) => selectedNodeTypes.add(item.node_type));
    }
  }
  for (const item of ontology?.node_types ?? []) {
    if (item.status === "active" && selected.has(`node:${item.node_type}`)) {
      includeNodes = true;
      selectedNodeTypes.add(item.node_type);
    }
  }
  for (const item of ontology?.predicates ?? []) {
    if (item.status === "active" && selected.has(`relation:${item.predicate}`)) {
      includeAssertions = true;
      selectedRelations.add(item.predicate);
    }
  }

  const recordKinds = [
    ...(includeEpisodes ? ["episode"] : []),
    ...(includeNodes ? ["node"] : []),
    ...(includeAssertions ? ["assertion"] : []),
  ];
  return {
    recordKinds,
    // A selected Node parent means all registered Node types; an empty type
    // list already has that meaning in the existing Recall contract.
    nodeTypes: includeNodes && !selected.has("kind:node") ? [...selectedNodeTypes].sort() : [],
    // Selecting the Assertion parent means all predicates; otherwise preserve
    // only the explicitly selected relation leaves.
    relationTypes: includeAssertions && !selected.has("kind:assertion") ? [...selectedRelations].sort() : [],
  };
}

function inclusiveDateEnd(value: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T23:59:59.999999` : value;
}

export function buildRecallRequestPayload(query: string, elfieId: string | undefined, filters: RecallSearchFilters): Record<string, unknown> {
  return {
    query: query.trim(),
    limit: 8,
    ...(filters.placeNodeId ? { place_node_ids: [filters.placeNodeId] } : {}),
    ...(filters.sense ? { sense: filters.sense } : {}),
    ...(elfieId ? { elfie_id: elfieId } : {}),
    ...(filters.recordKinds.length ? { record_kinds: [...filters.recordKinds] } : {}),
    ...(filters.nodeTypes.length ? { node_types: [...filters.nodeTypes] } : {}),
    ...(filters.relationTypes.length ? { relation_types: [...filters.relationTypes] } : {}),
    ...(filters.occurredFrom ? { occurred_from: filters.occurredFrom } : {}),
    ...(filters.occurredTo ? { occurred_to: inclusiveDateEnd(filters.occurredTo) } : {}),
    ...(filters.minimumImportance == null ? {} : { minimum_importance: filters.minimumImportance }),
  };
}

export function recallRouteLabel(source: string | null | undefined, role = "primary"): string {
  if (source === "lexical") return "Query · 文本";
  if (source === "sense") return "Sense · 场景";
  if (source === "kinship") return "Graph · 亲属";
  if (source) return `路径 · ${source}`;
  return role === "support" ? "关联上下文" : "路径未观测";
}

export function recallRouteStatusLabel(active: boolean, candidateCount: number): string {
  return `${active ? "已执行" : "未执行"} · ${candidateCount} 条候选`;
}

export function formatRecallSearchTime(value: string | null | undefined): string {
  if (!value) return "检索时间未记录";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "检索时间未记录";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(parsed);
}

export function buildRecallDisplayResults(bundle: RecallReport["bundle"], candidates: readonly RecallCandidate[]): RecallDisplayResult[] {
  const candidateByKey = new Map(candidates.map((candidate) => [`${candidate.candidate_kind}:${candidate.candidate_id}`, candidate]));
  const nodesById = new Map(bundle.focus_nodes.map((node) => [node.id, node]));
  const evidenceById = new Map(bundle.evidence.map((item) => [recordText(item, "evidence_id"), item]));
  const results: RecallDisplayResult[] = [];
  const append = (kind: RecallDisplayResult["kind"], id: string, title: string, summary: string, record: AuditItem | AuditRecord, related: string[]): void => {
    if (!id) return;
    const candidate = candidateByKey.get(`${kind}:${id}`) ?? null;
    results.push({
      key: `${kind}:${id}`,
      id,
      kind,
      title,
      summary,
      relevance: recordNumber(record as AuditRecord, "relevance") ?? candidate?.score ?? null,
      role: recordText(record as AuditRecord, "role", "primary"),
      importance: recordNumber(record as AuditRecord, "importance"),
      candidate,
      related,
      record,
    });
  };

  bundle.focus_nodes.forEach((node) => {
    const relatedAssertions = bundle.assertions.filter((assertion) =>
      String(assertion.subject_id ?? "") === node.id || String(assertion.object_node_id ?? "") === node.id,
    );
    const relatedLabels = relatedAssertions.map((assertion) => {
      const otherId = String(assertion.subject_id ?? "") === node.id
        ? String(assertion.object_node_id ?? assertion.object_literal ?? "")
        : String(assertion.subject_id ?? "");
      return nodesById.get(otherId)?.label ?? (otherId || "关联关系");
    });
    // The node type is already shown in the card header. Keep only a real
    // description here so values such as `place` do not become a duplicate
    // second type label in the card body.
    const description = String(node.description ?? "").trim();
    const nodeType = String(node.node_type ?? "").trim();
    append("node", node.id, node.label, description && description !== nodeType ? description : "", node, [...new Set(relatedLabels)]);
  });

  bundle.assertions.forEach((assertion) => {
    const id = recordText(assertion, "assertion_id", "");
    const subjectId = recordText(assertion, "subject_id", "");
    const objectId = recordText(assertion, "object_node_id", recordText(assertion, "object_literal", ""));
    const subject = nodesById.get(subjectId)?.label ?? subjectId;
    const object = nodesById.get(objectId)?.label ?? objectId;
    const predicate = recordText(assertion, "predicate", "关系");
    const relatedEvidence = (Array.isArray(assertion.evidence_ids) ? assertion.evidence_ids : []).map(String)
      .map((evidenceId) => evidenceById.get(evidenceId))
      .filter((item): item is AuditRecord => item !== undefined)
      .map((item) => recordText(item, "excerpt", recordText(item, "evidence_id", "来源证据")));
    // The relation predicate is part of the assertion title and is therefore
    // not repeated as a second body line. Evidence remains visible below.
    append("assertion", id, `${subject} · ${relationDisplayLabel(predicate)} · ${object}`, "", assertion, relatedEvidence);
  });

  bundle.episodes.forEach((episode, index) => {
    const id = recordText(episode, "episode_id", `episode-${index + 1}`);
    const excerpt = recordText(episode, "excerpt", recordText(episode, "content_text", id));
    const body = stripKnowledgeMemberHeaders(excerpt);
    const title = episodeCardDisplayTitle({
      ...episode,
      content_text: body,
    }) || id;
    const relatedEvidence = bundle.evidence
      .filter((item) => String(item.source_id ?? "") === id)
      .map((item) => recordText(item, "excerpt", recordText(item, "evidence_id", "来源证据")));
    const detail = recallEpisodeDetail(body, title);
    append("episode", id, title, detail, episode, relatedEvidence);
  });

  const kindOrder: Record<RecallDisplayResult["kind"], number> = { node: 0, episode: 1, assertion: 2 };
  return results.sort((left, right) => {
    const relevanceOrder = (right.relevance ?? -1) - (left.relevance ?? -1);
    if (relevanceOrder !== 0) return relevanceOrder;
    const roleOrder = (left.role === "primary" ? 0 : 1) - (right.role === "primary" ? 0 : 1);
    if (roleOrder !== 0) return roleOrder;
    return kindOrder[left.kind] - kindOrder[right.kind] || left.id.localeCompare(right.id);
  });
}

function recallResultTypeLabel(
  result: RecallDisplayResult,
  typeLabel: (nodeType: string) => string,
): string {
  if (result.kind === "node") {
    return typeLabel(String((result.record as AuditItem).node_type ?? "unknown"));
  }
  return result.kind === "episode" ? "经历" : "关系";
}

function recallResultRelatedLabel(kind: RecallDisplayResult["kind"]): string {
  return kind === "node" ? "关联" : "依据";
}

function recallEpisodeDetail(body: string, title: string): string {
  const normalizedBody = body.trim();
  const normalizedTitle = title.trim();
  if (!normalizedBody || !normalizedTitle || normalizedBody === normalizedTitle) return "";
  return normalizedBody.startsWith(normalizedTitle)
    ? normalizedBody.slice(normalizedTitle.length).replace(/^[\s。；;,:：—-]+/, "").trim()
    : normalizedBody;
}

type RecallPanelMode = "results" | "details";

export const RECALL_PROCESS_LABELS = ["搜索（三路）", "合并、去重", "过滤", "排序", "结果关联与输出"] as const;

function recallCandidateKey(candidate: RecallCandidate): string {
  return `${candidate.candidate_kind}:${candidate.candidate_id}`;
}

function recallCandidateScore(candidate: RecallCandidate): string {
  return Number.isFinite(candidate.score) ? candidate.score.toFixed(3) : "未观测";
}

export function recallExclusionLabel(reason: string | null | undefined): string {
  if (!reason) return "原因未观测";
  const labels: Record<string, string> = {
    score_below_floor: "低于相关度门槛",
    ranked_out_of_top_k: "排序后超出 Top-K",
    filtered_by_kind: "不符合对象类型",
    filtered_by_date: "不符合时间范围",
    filtered_by_importance: "低于最低重要度",
    duplicate: "与已有候选重复",
  };
  return labels[reason] ?? reason;
}

function sortRecallCandidates(candidates: readonly RecallCandidate[]): RecallCandidate[] {
  return [...candidates].sort((left, right) => {
    const leftRank = left.rank == null ? Number.POSITIVE_INFINITY : left.rank;
    const rightRank = right.rank == null ? Number.POSITIVE_INFINITY : right.rank;
    if (leftRank !== rightRank) return leftRank - rightRank;
    if (right.score !== left.score) return right.score - left.score;
    return recallCandidateKey(left).localeCompare(recallCandidateKey(right));
  });
}

type RecallCandidateStage = "route" | "merge" | "filter" | "sort";

function RecallStageCandidateList({
  candidates,
  stage,
  emptyText,
  duplicateCounts,
}: Readonly<{
  candidates: readonly RecallCandidate[];
  stage: RecallCandidateStage;
  emptyText: string;
  duplicateCounts?: ReadonlyMap<string, number>;
}>): React.JSX.Element {
  if (!candidates.length) return <p className="memory-debug-stage-empty">{emptyText}</p>;
  return <div className="memory-debug-stage-candidate-list" aria-label={`${stage} 阶段候选结果`}>
    {candidates.map((candidate, index) => {
      const key = recallCandidateKey(candidate);
      const duplicateCount = duplicateCounts?.get(key) ?? 1;
      const status = candidate.kept ? "保留" : "淘汰";
      const detail = stage === "route"
        ? `${recallRouteLabel(candidate.source)} · ${status}`
        : stage === "merge"
          ? duplicateCount > 1 ? `重复键 · ${duplicateCount} 条` : "唯一候选键"
          : stage === "filter"
            ? candidate.kept ? "进入下一步" : recallExclusionLabel(candidate.exclusion_reason)
            : `输出序号 ${candidate.rank ?? index + 1}`;
      return <div className={`memory-debug-stage-candidate ${candidate.kept ? "is-kept" : "is-excluded"}`} key={`${key}:${index}`}>
        <div className="memory-debug-stage-candidate-head">
          <span>{stage === "sort" ? (candidate.rank ?? index + 1) : index + 1}</span>
          <code>{candidate.candidate_id}</code>
          <small>{candidate.candidate_kind}</small>
          {stage === "filter" && <strong>{status}</strong>}
        </div>
        <div className="memory-debug-stage-candidate-facts">
          <span>{detail}</span>
          <span>score {recallCandidateScore(candidate)}</span>
          <span>命中 {candidate.matched_terms?.join("、") || "未观测"}</span>
        </div>
      </div>;
    })}
  </div>;
}

function RecallStageOutputList({
  results,
  typeLabel,
}: Readonly<{
  results: readonly RecallDisplayResult[];
  typeLabel: (nodeType: string) => string;
}>): React.JSX.Element {
  if (!results.length) return <p className="memory-debug-stage-empty">本次没有可展示的 Node、Episode 或关系结果。</p>;
  return <div className="memory-debug-stage-output-list" aria-label="结果关联与输出结果">
    {results.map((result, index) => {
      return <div className="memory-debug-stage-output" key={result.key}>
        <span className="memory-debug-stage-output-rank">{index + 1}</span>
        <div>
          <strong>{result.title}</strong>
          <small>{recallResultTypeLabel(result, typeLabel)} · {recallRouteLabel(result.candidate?.source, result.role)}</small>
        </div>
        <span>{result.relevance == null ? "相关度未提供" : result.relevance.toFixed(2)}</span>
      </div>;
    })}
  </div>;
}

function RecallResultCard({
  result,
  index,
  typeLabel,
  selected,
  onOpenObject,
}: Readonly<{
  result: RecallDisplayResult;
  index: number;
  typeLabel: (nodeType: string) => string;
  selected: boolean;
  onOpenObject: (result: RecallDisplayResult) => void;
}>): React.JSX.Element {
  const candidate = result.candidate;
  const typeLabelForResult = recallResultTypeLabel(result, typeLabel);
  const relatedLabel = recallResultRelatedLabel(result.kind);
  return <article className={`memory-debug-result-card${selected ? " is-object-selected" : ""}`} aria-label={`${result.kind} 搜索结果 ${index + 1}`} aria-current={selected ? "true" : undefined}>
    <div className="memory-debug-result-card-inner">
      <section
        className="memory-debug-result-face memory-debug-result-front"
        aria-label="搜索结果摘要，点击打开对象详情"
        title="点击卡片查看右侧对象详情"
        tabIndex={0}
        onClick={() => onOpenObject(result)}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget || (event.key !== "Enter" && event.key !== " ")) return;
          event.preventDefault();
          onOpenObject(result);
        }}
      >
        <div className="memory-debug-result-card-head">
          <span className="memory-debug-result-rank">{index + 1}</span>
          <span className="memory-debug-result-kind">{typeLabelForResult}</span>
          <div className="memory-debug-result-head-meta">
            <span className="memory-debug-result-score">{result.relevance == null ? "相关度未提供" : `相关度 ${result.relevance.toFixed(2)}`}</span>
            {result.importance != null && <span className="memory-debug-result-importance">重要度 {(result.importance * 100).toFixed(0)}%</span>}
            <span className="memory-debug-result-route">{recallRouteLabel(candidate?.source, result.role)}</span>
          </div>
        </div>
        <div className="memory-debug-result-core">
          <strong className="memory-debug-result-title">{result.title}</strong>
          {result.summary && <p className="memory-debug-result-summary">{result.summary}</p>}
        </div>
        <div className="memory-debug-result-foot">
          <div className="memory-debug-result-associations">
            <span>{relatedLabel} {result.related.length}</span>
            {result.related.slice(0, 2).map((item, relatedIndex) => <small key={`${result.key}:related:${relatedIndex}`}>{item}</small>)}
            {result.related.length > 2 && <small>+{result.related.length - 2}</small>}
          </div>
          {candidate?.matched_terms?.length ? <small className="memory-debug-result-match">命中：{candidate.matched_terms.join("、")}</small> : null}
        </div>
      </section>
    </div>
  </article>;
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
    .sort((left, right) => {
      const leftTime = episodeSortTime(left);
      const rightTime = episodeSortTime(right);
      if (leftTime === null && rightTime !== null) return 1;
      if (leftTime !== null && rightTime === null) return -1;
      if (leftTime !== null && rightTime !== null && leftTime !== rightTime) {
        return leftTime - rightTime;
      }
      return String(left.episode_id ?? "").localeCompare(String(right.episode_id ?? ""));
    });
}

function episodeSortTime(episode: AuditRecord): number | null {
  const value = episode.occurred_from ?? episode.occurred_at ?? episode.occurred_to;
  if (value == null || value === "") return null;
  const timestamp = Date.parse(String(value));
  return Number.isFinite(timestamp) ? timestamp : null;
}

function mergeRecords(records: AuditRecord[], incoming: AuditRecord[], key: string): AuditRecord[] {
  const merged = new Map(records.map((record) => [String(record[key] ?? ""), record]));
  incoming.forEach((record) => merged.set(String(record[key] ?? ""), record));
  return Array.from(merged.values());
}

// Orbit controls keep camera rotation behind an explicit press-and-drag gesture.
// Hovering the graph must remain a read-only inspection interaction.
export const MEMORY_DEBUG_GRAPH_CONTROL_TYPE = "orbit" as const;
export const MEMORY_DEBUG_GRAPH_ARROW_REL_POS = 0.95;

export function graphNavigationActive(pointerType: string, buttons: number): boolean {
  return pointerType === "touch" || buttons !== 0;
}

export function graphLinkIsContextual(
  hasBackgroundHighlight: boolean,
  selectedEdgeId: string,
  linkId: string,
  isReturned: boolean,
  isAffected: boolean,
): boolean {
  return !hasBackgroundHighlight || selectedEdgeId === linkId || isReturned || isAffected;
}

export type GraphNodeHighlightKind = "none" | "selected";

export function graphNodeHighlightKind(
  isSelected: boolean,
  isEdgeEndpoint: boolean,
  isReturned: boolean,
  isAffected: boolean,
): GraphNodeHighlightKind {
  if (isSelected || isEdgeEndpoint) return "selected";
  // Search/preview hits stay in the normal semantic node style. Only an
  // explicit node or edge selection gets a selection overlay.
  void isReturned;
  void isAffected;
  return "none";
}

function graphNodeHighlightColor(kind: GraphNodeHighlightKind): { ring: string; glow: string } | null {
  return kind === "selected"
    ? { ring: GRAPH_SELECTED_NODE_RING_COLOR, glow: "rgba(114, 231, 247, 0.52)" }
    : null;
}

function createNodeHighlightSprite(nodeRadius: number, kind: GraphNodeHighlightKind): Sprite | null {
  const colors = graphNodeHighlightColor(kind);
  if (!colors) return null;
  const logicalSize = 64;
  const pixelRatio = 2;
  const canvas = document.createElement("canvas");
  canvas.width = logicalSize * pixelRatio;
  canvas.height = logicalSize * pixelRatio;
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.scale(pixelRatio, pixelRatio);
  context.lineCap = "round";
  context.shadowColor = colors.glow;
  context.shadowBlur = 14;
  context.strokeStyle = colors.ring;
  context.lineWidth = 6;
  context.beginPath();
  context.arc(logicalSize / 2, logicalSize / 2, 25, 0, Math.PI * 2);
  context.stroke();
  context.shadowBlur = 0;
  context.lineWidth = 2.5;
  context.stroke();
  const sprite = new Sprite(new SpriteMaterial({ map: new CanvasTexture(canvas), transparent: true, depthWrite: false, depthTest: false, opacity: 1 }));
  // The canvas ring occupies 50 of its 64 logical pixels. Scale the sprite
  // from that actual fraction; the old factor made the ring smaller than the
  // sphere, so depth testing hid it almost completely.
  const ringDiameter = nodeRadius * 2 + 3.2;
  const spriteDiameter = ringDiameter * logicalSize / 50;
  sprite.scale.set(spriteDiameter, spriteDiameter, 1);
  return sprite;
}

function disposeNodeOverlay(group: Group): void {
  group.children.forEach((child) => {
    if (!(child instanceof Sprite)) return;
    const material = child.material;
    if (material instanceof SpriteMaterial) {
      material.map?.dispose();
      material.dispose();
    }
  });
}

export function graphLinkColor(
  hasBackgroundHighlight: boolean,
  selectedEdgeId: string,
  linkId: string,
  kind: string,
  isReturned: boolean,
  isAffected: boolean,
): string {
  if (!graphLinkIsContextual(hasBackgroundHighlight, selectedEdgeId, linkId, isReturned, isAffected)) return DIMMED_LINK_COLOR;
  if (selectedEdgeId === linkId) return GRAPH_SELECTED_LINK_COLOR;
  return kind === "preview-assertion" ? "#ff9d57" : "#5e9fbb";
}

export function graphLinkArrowLength(
  _hasBackgroundHighlight: boolean,
  _selectedEdgeId: string,
  _linkId: string,
  kind: string,
  _isReturned: boolean,
  _isAffected: boolean,
): number {
  if (kind !== "assertion" && kind !== "preview-assertion") return 0;
  return GRAPH_ARROW_LENGTH;
}

function graphLinkArrowColor(
  hasBackgroundHighlight: boolean,
  selectedEdgeId: string,
  linkId: string,
  kind: string,
  isReturned: boolean,
  isAffected: boolean,
): string {
  return graphLinkColor(hasBackgroundHighlight, selectedEdgeId, linkId, kind, isReturned, isAffected);
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

function shortGraphLabel(value: string, limit = 24): string {
  return value.length > limit ? `${value.slice(0, limit)}…` : value;
}

type WebGLStatus = "checking" | "available" | "unavailable";

type WebGLGraphErrorBoundaryProps = { children: React.ReactNode; fallback: React.ReactNode };
type WebGLGraphErrorBoundaryState = { hasError: boolean };

class WebGLGraphErrorBoundary extends Component<WebGLGraphErrorBoundaryProps, WebGLGraphErrorBoundaryState> {
  state: WebGLGraphErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): WebGLGraphErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error): void {
    console.error("Memory Debug 3D renderer failed.", error);
  }

  render(): React.ReactNode {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}

export function projectMemoryDebugGraph(report: AuditReport | null, filters: GraphFilters = {}): { nodes: GraphNodeSeed[]; edges: GraphEdge[] } {
  const assertions = report?.data.assertions ?? [];
  const typeById = new Map((report?.ontology?.node_types ?? []).map((item) => [item.node_type, item]));
  // Self-model selects a one-hop stance neighborhood before projecting its internal edges.
  let selfNodeIds: Set<string> | undefined;
  if (filters.nodeGroup === "self_model") {
    selfNodeIds = new Set<string>();
    const anchor = report?.data.nodes.find(node => node.node_type === "elfie" && node.properties?.is_self === true);
    const stancePredicates = new Set(report?.ontology?.predicates.filter(item => item.status === "active" && item.self_stance).map(item => item.predicate));
    const registeredIds = new Set((report?.data.nodes ?? []).filter(node => isMemoryDebugSemanticNodeType(node.node_type, report)).map(node => node.id));
    if (anchor) {
      selfNodeIds.add(anchor.id);
      assertions.forEach(edge => {
        const predicate = String(edge.predicate);
        const canonical = report?.ontology?.predicate_aliases[predicate] ?? predicate;
        if (edge.subject_id === anchor.id && stancePredicates.has(canonical) && Array.isArray(edge.evidence_ids) && edge.evidence_ids.length && registeredIds.has(String(edge.object_node_id))) selfNodeIds?.add(String(edge.object_node_id));
      });
    }
  }
  const nodes = (report?.data.nodes ?? []).filter((item) => {
    if (!isMemoryDebugSemanticNodeType(item.node_type, report)) return false;
    if (filters.includeNodeIds && !filters.includeNodeIds.has(item.id)) return false;
    if (filters.nodeTypes && !filters.nodeTypes.has(item.node_type ?? "node")) return false;
    if (selfNodeIds && !selfNodeIds.has(item.id)) return false;
    if (filters.nodeGroup && !selfNodeIds && typeById.get(item.node_type ?? "")?.group_id !== filters.nodeGroup) return false;
    if (filters.lifecycle && filters.lifecycle !== "all" && recordLifecycle(item) !== filters.lifecycle) return false;
    if (filters.minConfidence != null && (typeof item.confidence !== "number" || item.confidence < filters.minConfidence)) return false;
    return true;
  });
  const nodeIds = new Set(nodes.map((item) => item.id));
  const projectedNodes: GraphNodeSeed[] = nodes.map((item) => {
    const type = typeById.get(item.node_type ?? "");
    return {
      id: item.id,
      kind: item.node_type ?? "node",
      label: item.label,
      ...(type ? { color: type.color, typeLabel: type.label } : {}),
    };
  });
  const literalNodes = new Map<string, GraphNodeSeed>();
  const predicateAliases = report?.ontology?.predicate_aliases ?? {};
  const activePredicates = new Set((report?.ontology?.predicates ?? [])
    .filter((item) => item.status === "active")
    .map((item) => item.predicate));
  const evidenceIds = new Set((report?.data.evidence ?? []).map((item) => String(item.evidence_id)));
  const edges: GraphAssertionEdge[] = [];
  assertions.forEach((item) => {
    const assertionId = String(item.assertion_id);
    if (filters.includeAssertionIds && !filters.includeAssertionIds.has(assertionId)) return;
    const rawPredicate = String(item.predicate ?? "关系");
    const predicate = predicateAliases[rawPredicate] ?? rawPredicate;
    if (!activePredicates.has(predicate)) return;
    if (!Array.isArray(item.evidence_ids) || item.evidence_ids.length === 0) return;
    if (filters.predicateTypes && !filters.predicateTypes.has(predicate)) return;
    if (filters.minConfidence != null && (typeof item.confidence !== "number" || item.confidence < filters.minConfidence)) return;
    const source = item.subject_id == null ? "" : String(item.subject_id);
    if (!source || !nodeIds.has(source)) return;
    const assertionEvidence = (Array.isArray(item.evidence_ids) ? item.evidence_ids : [])
      .map(String)
      .filter((id) => evidenceIds.has(id));
    let target = item.object_node_id == null ? "" : String(item.object_node_id);
    if (target && !nodeIds.has(target)) return;
    if (selfNodeIds && !target) return;
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
      label: relationDisplayLabel(relationKindFromRecord(item, predicate, report), report),
      predicate,
      kind: "assertion",
      evidenceIds: assertionEvidence,
      symmetric: relationIsSymmetric(relationKindFromRecord(item, predicate, report), report),
      ...(importance == null ? {} : { importance }),
    });
  });
  projectedNodes.sort((left, right) => left.id.localeCompare(right.id));
  return {
    nodes: [...projectedNodes, ...[...literalNodes.values()].sort((left, right) => left.id.localeCompare(right.id))],
    edges: aggregateGraphEdges(edges),
  };
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
  const [selectedTypeGroup, setSelectedTypeGroup] = useState("");
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [selectedPredicates, setSelectedPredicates] = useState<string[]>([]);
  const [recallObjectValues, setRecallObjectValues] = useState<string[]>([]);
  const [sceneEmotionValues, setSceneEmotionValues] = useState<Partial<Record<SceneEmotion, number>>>({});
  const [sceneLocationId, setSceneLocationId] = useState<string>();
  const [sceneVisibleCue, setSceneVisibleCue] = useState("");
  const [sceneTouchCue, setSceneTouchCue] = useState("");
  const [sceneTemperature, setSceneTemperature] = useState<number | null>(null);
  const [sceneHumidity, setSceneHumidity] = useState<number | null>(null);
  const [sceneIlluminance, setSceneIlluminance] = useState<number | null>(null);
  const [occurredFrom, setOccurredFrom] = useState("");
  const [occurredTo, setOccurredTo] = useState("");
  const [minimumImportance, setMinimumImportance] = useState<number | null>(null);
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
  const [recallPanelMode, setRecallPanelMode] = useState<RecallPanelMode>("results");
  const [recallResultFilter, setRecallResultFilter] = useState<RecallResultFilter>("all");
  const [selectedRecallRoute, setSelectedRecallRoute] = useState("");
  const [layoutLocked, setLayoutLocked] = useState(true);
  const [tracePositions, setTracePositions] = useState<Record<string, { x: number; y: number }>>({});
  const [graphViewport, setGraphViewport] = useState({ width: 0, height: 0 });
  const [ForceGraph3DComponent, setForceGraph3DComponent] = useState<ForceGraphComponent | null>(null);
  const [webglStatus, setWebglStatus] = useState<WebGLStatus>("checking");
  const graphRef = useRef<ForceGraphMethods<Graph3DNode, Graph3DLink> | undefined>(undefined);
  const graphCanvasRef = useRef<HTMLDivElement | null>(null);
  const filterTriggerRef = useRef<HTMLButtonElement | null>(null);
  const filterPopoverRef = useRef<HTMLElement | null>(null);
  const episodeCardRefs = useRef(new Map<string, HTMLButtonElement>());
  const reportRequestRef = useRef(0);
  const graphFitPendingRef = useRef(true);
  const graphFitRequestRef = useRef(0);
  const graphFitFallbackTimerRef = useRef<number | null>(null);
  const nodeOverlaysRef = useRef(new Map<string, GraphNodeOverlay>());
  const labelOcclusionFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (!filterOpen) return undefined;
    const dismissOnOutsidePointer = (event: PointerEvent): void => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (filterPopoverRef.current?.contains(target) || filterTriggerRef.current?.contains(target)) return;
      if (target instanceof Element && target.closest(".ant-select-dropdown, .ant-picker-dropdown")) return;
      setFilterOpen(false);
    };
    document.addEventListener("pointerdown", dismissOnOutsidePointer, true);
    return () => document.removeEventListener("pointerdown", dismissOnOutsidePointer, true);
  }, [filterOpen]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    let active = true;
    void import("react-force-graph-3d").then(({ default: component }) => {
      if (active) {
        setForceGraph3DComponent(() => component);
        setWebglStatus("available");
      }
    }).catch((error: unknown) => {
      console.error("Unable to load the 3D memory graph.", error);
      if (active) setWebglStatus("unavailable");
    });
    return () => { active = false; };
  }, []);

  useEffect(() => () => {
    nodeOverlaysRef.current.forEach(({ group }) => {
      disposeNodeOverlay(group);
    });
    nodeOverlaysRef.current.clear();
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
      setSelectedId((current) => current && merged?.data.nodes.some((node) => node.id === current && isMemoryDebugSemanticNodeType(node.node_type, merged)) ? current : "");
      setSelectedEdgeId((current) => current && (current.startsWith("relation:") || merged?.data.assertions.some((item) => String(item.assertion_id) === current)) ? current : "");
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

  const selected = report?.data.nodes.find((node) => node.id === selectedId && isMemoryDebugSemanticNodeType(node.node_type, report)) ?? null;
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
  useEffect(() => {
    setSelectedRecallRoute("");
  }, [recallView?.selection.recall_id]);
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
  const recallGraphProjectionKey = memoryDebugRecallProjectionKey(
    showOnlyRecallResults,
    recallView?.selection.recall_id,
    recalledNodeIds,
    recalledAssertionNodeIds,
    recalledAssertionIds,
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
      Boolean(recallGraphProjectionKey),
      showOnlyRecallResults,
      new Set([...recalledNodeIds, ...recalledAssertionNodeIds]),
      recalledAssertionIds,
    );
    const projection = projectMemoryDebugGraph(report, {
      lifecycle: lifecycleFilter,
      minConfidence: localConfidence,
      nodeGroup: selectedTypeGroup || undefined,
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
  }, [lifecycleFilter, localConfidence, recallGraphProjectionKey, report, selectedPredicates, selectedTypeGroup, selectedTypes, showOnlyRecallResults]);
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
      typeLabel: nodeTypeLabel(String(item.node_type ?? "unknown"), report),
      degree: 1,
      val: graphNodeValue(typeof item.importance === "number" ? item.importance : undefined),
      preview: id !== originalId,
    } satisfies Graph3DNode;
  }), [graphNodeIds, preview, previewNodeIds]);
  const previewGraphEdges = useMemo(() => {
    const assertionEdges: GraphAssertionEdge[] = (preview?.changes.affected.assertions ?? []).map((item) => ({
      id: String(item.assertion_id),
      source: previewNodeKey(String(item.subject_id)),
      target: previewNodeKey(String(item.object_node_id ?? "")),
      label: relationDisplayLabel(relationKindFromRecord(item, String(item.predicate ?? "关系"), report), report),
      predicate: String(item.predicate ?? "关系"),
      kind: "preview-assertion",
      evidenceIds: Array.isArray(item.evidence_ids) ? item.evidence_ids.map(String) : [],
      symmetric: relationIsSymmetric(relationKindFromRecord(item, String(item.predicate ?? "关系"), report), report),
      ...(typeof item.importance === "number" ? { importance: item.importance } : {}),
    })).filter((edge) => edge.target !== "preview:");
    return aggregateGraphEdges(assertionEdges);
  }, [graphNodeIds, preview, previewNodeIds, report]);
  const graphData: { nodes: Graph3DNode[]; links: Graph3DLink[] } = useMemo(() => ({
    nodes: [...graph.nodes, ...previewGraphNodes],
    // react-force-graph mutates link.source/link.target into node objects while
    // indexing the scene. Keep those mutations out of the projection used by
    // the right-hand detail panel, otherwise React can receive a Three object
    // where a string endpoint is expected after a graph click.
    links: [...graph.edges, ...previewGraphEdges].map((edge): Graph3DLink => ({
      ...edge,
      assertionIds: [...edge.assertionIds],
      evidenceIds: [...(edge.evidenceIds ?? [])],
      labels: [...edge.labels],
      predicates: [...edge.predicates],
    })),
  }), [graph, previewGraphEdges, previewGraphNodes]);
  const visibleEpisodes = useMemo(() => filterMemoryDebugEpisodes(
    report?.data.episodes ?? [],
    lifecycleFilter,
    recallView ? recalledEpisodeIds : undefined,
  ), [lifecycleFilter, recallView, report]);
  const memoryDateBounds = useMemo(() => memoryRecallDateBounds(report?.data.episodes ?? []), [report?.data.episodes]);
  const earliestMemoryDate = useMemo(() => dayjs(memoryDateBounds.from).locale("zh-cn"), [memoryDateBounds.from]);
  const latestMemoryDate = useMemo(() => dayjs(memoryDateBounds.to).locale("zh-cn"), [memoryDateBounds.to]);
  const timeRangePickerValue = useMemo<[Dayjs, Dayjs] | null>(() => {
    if (!occurredFrom || !occurredTo) return null;
    return [dayjs(occurredFrom).locale("zh-cn"), dayjs(occurredTo).locale("zh-cn")];
  }, [occurredFrom, occurredTo]);
  const recallObjectFilters = recallFiltersFromObjectSelection(recallObjectValues, report?.ontology);
  const selectedSceneEmotion = SCENE_EMOTIONS.find(({ key }) => sceneEmotionValues[key] != null);
  const sceneSense = selectedSceneEmotion
    ? { emotion_label: selectedSceneEmotion.key, intensity: sceneEmotionValues[selectedSceneEmotion.key]! / 100 }
    : undefined;
  const canRecall = Boolean(query.trim() || sceneLocationId || sceneSense);
  const hasLocalFilters = Boolean(
    selectedTypeGroup !== "" || selectedTypes.length || selectedPredicates.length || lifecycleFilter !== "all" || confidenceFilter !== "all",
  );
  const activeFilterCount = [
    recallObjectValues.length > 0,
    occurredFrom !== "" || occurredTo !== "",
    minimumImportance !== null,
    ...Object.values(sceneEmotionValues).map((value) => value != null),
    Boolean(sceneLocationId),
    Boolean(sceneVisibleCue.trim()),
    Boolean(sceneTouchCue.trim()),
    sceneTemperature != null,
    sceneHumidity != null,
    sceneIlluminance != null,
  ].filter(Boolean).length;
  const activeGraphFilterCount = [
    selectedTypeGroup !== "",
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

  function updateGraphLabelOcclusion(): void {
    const instance = graphRef.current;
    if (!instance || !graphData.nodes.length) return;
    const camera = instance.camera();
    const renderer = instance.renderer();
    const width = renderer.domElement.clientWidth || graphViewport.width;
    const height = renderer.domElement.clientHeight || graphViewport.height;
    if (!width || !height) return;

    camera.updateMatrixWorld();
    const cameraRight = new Vector3().setFromMatrixColumn(camera.matrixWorld, 0).normalize();
    const cameraUp = new Vector3().setFromMatrixColumn(camera.matrixWorld, 1).normalize();
    const projectToScreen = (point: Vector3): { x: number; y: number; z: number } | null => {
      const projected = point.clone().project(camera);
      if (![projected.x, projected.y, projected.z].every(Number.isFinite)) return null;
      return {
        x: (projected.x + 1) * width / 2,
        y: (1 - projected.y) * height / 2,
        z: projected.z,
      };
    };
    const entries = graphData.nodes.flatMap((node): GraphLabelOcclusionEntry[] => {
      if (![node.x, node.y, node.z].every((value) => typeof value === "number" && Number.isFinite(value))) return [];
      const center = new Vector3(node.x!, node.y!, node.z!);
      const screenCenter = projectToScreen(center);
      if (!screenCenter) return [];
      const radius = graphPointRadius(node);
      const radiusPixels = Math.max(
        0,
        ...[
          center.clone().addScaledVector(cameraRight, radius),
          center.clone().addScaledVector(cameraRight, -radius),
          center.clone().addScaledVector(cameraUp, radius),
          center.clone().addScaledVector(cameraUp, -radius),
        ].map((point) => {
          const projected = projectToScreen(point);
          return projected ? Math.hypot(projected.x - screenCenter.x, projected.y - screenCenter.y) : 0;
        }),
      );
      const overlay = nodeOverlaysRef.current.get(String(node.id));
      let label: GraphScreenRect | undefined;
      if (overlay?.labelSprite) {
        const cameraDelta = camera.position.clone().sub(center);
        const cameraDistance = cameraDelta.length();
        if (cameraDistance > 0.0001) {
          const labelCenter = center.clone().addScaledVector(cameraDelta.normalize(), radius + 0.12);
          const halfWidth = Math.abs(overlay.labelSprite.scale.x) / 2;
          const halfHeight = Math.abs(overlay.labelSprite.scale.y) / 2;
          const corners = [
            labelCenter.clone().addScaledVector(cameraRight, -halfWidth).addScaledVector(cameraUp, -halfHeight),
            labelCenter.clone().addScaledVector(cameraRight, -halfWidth).addScaledVector(cameraUp, halfHeight),
            labelCenter.clone().addScaledVector(cameraRight, halfWidth).addScaledVector(cameraUp, -halfHeight),
            labelCenter.clone().addScaledVector(cameraRight, halfWidth).addScaledVector(cameraUp, halfHeight),
          ].map(projectToScreen);
          if (corners.every((point): point is { x: number; y: number; z: number } => Boolean(point))) {
            label = {
              left: Math.min(...corners.map((point) => point.x)),
              right: Math.max(...corners.map((point) => point.x)),
              top: Math.min(...corners.map((point) => point.y)),
              bottom: Math.max(...corners.map((point) => point.y)),
            };
          }
        }
      }
      const viewPoint = center.clone().applyMatrix4(camera.matrixWorldInverse);
      return [{
        id: String(node.id),
        depth: -viewPoint.z - radius,
        center: { x: screenCenter.x, y: screenCenter.y },
        radius: radiusPixels,
        ...(label ? { label } : {}),
      }];
    });
    if (!entries.length) return;

    const visibleIds = graphVisibleLabelIds(entries);
    const currentNodeIds = new Set(graphData.nodes.map((node) => String(node.id)));
    let changed = false;
    nodeOverlaysRef.current.forEach(({ labelSprite }, nodeId) => {
      if (!labelSprite) return;
      const nextVisible = currentNodeIds.has(nodeId) ? visibleIds.has(nodeId) : true;
      if (labelSprite.visible !== nextVisible) {
        labelSprite.visible = nextVisible;
        changed = true;
      }
    });
    if (changed) instance.refresh();
  }

  function scheduleGraphLabelOcclusion(): void {
    if (typeof window === "undefined" || labelOcclusionFrameRef.current !== null) return;
    labelOcclusionFrameRef.current = window.requestAnimationFrame(() => {
      labelOcclusionFrameRef.current = null;
      updateGraphLabelOcclusion();
    });
  }

  useEffect(() => {
    if (webglStatus !== "available" || !ForceGraph3DComponent || !graphData.nodes.length) return undefined;
    const instance = graphRef.current;
    if (!instance) return undefined;
    const controls = instance.controls() as unknown as {
      addEventListener?: (type: string, listener: () => void) => void;
      removeEventListener?: (type: string, listener: () => void) => void;
    };
    const handleCameraChange = (): void => scheduleGraphLabelOcclusion();
    controls.addEventListener?.("change", handleCameraChange);
    scheduleGraphLabelOcclusion();
    return () => {
      controls.removeEventListener?.("change", handleCameraChange);
      if (labelOcclusionFrameRef.current !== null) {
        window.cancelAnimationFrame(labelOcclusionFrameRef.current);
        labelOcclusionFrameRef.current = null;
      }
    };
  }, [ForceGraph3DComponent, graphData, graphViewport, webglStatus]);

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

  function fitGraph(durationMs = 320): void {
    const instance = graphRef.current;
    if (!instance || !graphData.nodes.length) return;
    graphFitPendingRef.current = false;
    const requestId = ++graphFitRequestRef.current;
    // Keep the library-owned 3D fit path. Two animation frames let
    // force-graph copy its settled positions into the Three.js scene before
    // reading the bounds. We still compute the target from the actual graph
    // center because the library's zoomToFit aims at the world origin.
    const applyFit = (): void => {
      if (requestId !== graphFitRequestRef.current || graphRef.current !== instance) return;
      const bounds = instance.getGraphBbox();
      const camera = instance.camera() as unknown as {
        aspect?: number;
        fov?: number;
        position?: GraphPoint3D;
      };
      const viewport = graphCanvasRef.current;
      const fit = bounds && camera.position
        ? graphFitCameraTarget(
          bounds,
          camera.position,
          camera.fov ?? 25,
          camera.aspect ?? ((viewport?.clientWidth ?? 1) / Math.max(1, viewport?.clientHeight ?? 1)),
          viewport?.clientHeight ?? graphViewport.height,
          MEMORY_DEBUG_GRAPH_FIT_PADDING,
        )
        : null;
      if (!fit) {
        graphFitPendingRef.current = true;
        window.setTimeout(() => {
          if (requestId === graphFitRequestRef.current && graphFitPendingRef.current && graphRef.current === instance) {
            fitGraph(durationMs);
          }
        }, 180);
        return;
      }
      graphFitPendingRef.current = false;
      instance.cameraPosition(fit.position, fit.target, durationMs);
      window.setTimeout(() => {
        if (requestId === graphFitRequestRef.current) {
          setGraphFitReady(true);
          scheduleGraphLabelOcclusion();
        }
      }, Math.max(0, durationMs));
    };
    window.requestAnimationFrame(() => {
      if (requestId !== graphFitRequestRef.current) return;
      window.requestAnimationFrame(() => {
        if (requestId !== graphFitRequestRef.current) return;
        window.setTimeout(applyFit, 40);
      });
    });
  }

  function nodeLabelObject(node: Graph3DNode): Group {
    const nodeId = String(node.id ?? "");
    const isGeneralKnowledge = report?.ontology?.node_types.some((item) => item.node_type === node.kind && item.group_id === "general_knowledge") ?? false;
    const text = shortGraphLabel(node.label, isGeneralKnowledge ? 6 : 12);
    const showPersistentLabel = selectedTypes.length > 0
      || graphData.nodes.length <= 60
      || !isGeneralKnowledge
      || selectedId === nodeId;
    const isReturned = recalledNodeIds.has(nodeId) || recalledAssertionNodeIds.has(nodeId);
    const isAffected = selectedEpisodeNodeIds.has(nodeId) || previewNodeIds.has(nodeId) || previewAssertionNodeIds.has(nodeId);
    const highlightKind = graphNodeHighlightKind(
      selectedId === nodeId,
      selectedEdgeNodeIds.has(nodeId),
      isReturned,
      isAffected || highlightedNodeIds.has(nodeId),
    );
    const nodeRadius = graphPointRadius(node);
    const signature = `${text}|${showPersistentLabel ? "label" : "no-label"}|${highlightKind}|${nodeRadius.toFixed(2)}`;
    const cached = nodeOverlaysRef.current.get(nodeId);
    if (cached?.signature === signature) return cached.group;
    if (cached) {
      disposeNodeOverlay(cached.group);
    }
    const group = new Group();
    const highlightSprite = createNodeHighlightSprite(nodeRadius, highlightKind);
    if (highlightSprite) group.add(highlightSprite);
    if (!showPersistentLabel) {
      nodeOverlaysRef.current.set(nodeId, { signature, group });
      return group;
    }
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    if (!context) {
      nodeOverlaysRef.current.set(nodeId, { signature, group });
      return group;
    }
    // Keep labels comfortably inside the node while giving larger nodes a
    // proportionally larger label. The range is intentionally bounded so a
    // long label cannot dominate the graph.
    const labelScale = Math.min(1.5, Math.max(1.2, nodeRadius / 3.6));
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
    const labelMaterial = new SpriteMaterial({ map: new CanvasTexture(canvas), ...graphNodeLabelMaterialOptions() });
    const sprite = new Sprite(labelMaterial);
    sprite.scale.set((logicalWidth / 22) * labelScale, (logicalHeight / 22) * labelScale, 1);
    sprite.renderOrder = GRAPH_NODE_LABEL_RENDER_ORDER;
    sprite.position.set(0, 0, 0);
    sprite.onBeforeRender = (_renderer, _scene, camera) => {
      const parent = sprite.parent;
      if (!parent) return;
      const anchor = parent.parent ?? parent;
      const dx = camera.position.x - anchor.position.x;
      const dy = camera.position.y - anchor.position.y;
      const dz = camera.position.z - anchor.position.z;
      const distance = Math.hypot(dx, dy, dz);
      if (distance <= 0.0001) return;
      const offset = nodeRadius + 0.12;
      sprite.position.set((dx / distance) * offset, (dy / distance) * offset, (dz / distance) * offset);
    };
    group.add(sprite);
    nodeOverlaysRef.current.set(nodeId, { signature, group, labelSprite: sprite });
    return group;
  }

  useEffect(() => {
    if (webglStatus !== "available" || !ForceGraph3DComponent || !graphData.nodes.length) return undefined;
    graphFitRequestRef.current += 1;
    setGraphFitReady(false);
    graphFitPendingRef.current = true;
    if (graphFitFallbackTimerRef.current !== null) window.clearTimeout(graphFitFallbackTimerRef.current);
    graphFitFallbackTimerRef.current = window.setTimeout(() => {
      graphFitFallbackTimerRef.current = null;
      if (graphFitPendingRef.current) fitGraph();
    }, 700);
    return () => {
      if (graphFitFallbackTimerRef.current !== null) {
        window.clearTimeout(graphFitFallbackTimerRef.current);
        graphFitFallbackTimerRef.current = null;
      }
    };
  }, [ForceGraph3DComponent, graphData, webglStatus]);

  // The engine-stop callback is the fast path; the delayed fallback handles
  // the mount race where force-graph stops before the pending flag is set.
  // Manual fit remains available through the explicit toolbar action.

  function resetGraph(): void {
    setSelectedId("");
    setSelectedEdgeId("");
    setSelectedEpisodeId("");
    setSelectedEvidenceId("");
    setDetailSelection(null);
    setRecall(null);
    setTraceRecall(null);
    setQuery("");
    setShowOnlyRecallResults(false);
    setRecallPanelMode("results");
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

  function clearSearchFilters(): void {
    setRecallObjectValues([]);
    setOccurredFrom("");
    setOccurredTo("");
    setMinimumImportance(null);
    setSceneEmotionValues({});
    setSceneLocationId(undefined);
    setSceneVisibleCue("");
    setSceneTouchCue("");
    setSceneTemperature(null);
    setSceneHumidity(null);
    setSceneIlluminance(null);
  }

  function clearGraphDisplayFilters(): void {
    setSelectedTypeGroup("");
    setSelectedTypes([]);
    setSelectedPredicates([]);
    setLifecycleFilter("all");
    setConfidenceFilter("all");
  }

  function clearSearch(closeRecallPanel = tab === "recall", announce = true): void {
    setQuery("");
    setRecall(null);
    setTraceRecall(null);
    setShowOnlyRecallResults(false);
    setRecallPanelMode("results");
    setRecallResultFilter("all");
    if (closeRecallPanel) setLeftPanelOpen(false);
    if (announce) setMessage("已清除搜索结果。");
  }

  function openFilter(): void {
    setFilterOpen((open) => !open);
  }

  function openAddPanel(): void {
    setFilterOpen(false);
    setRecall(null);
    setTraceRecall(null);
    setPreview(null);
    setQuery("");
    setShowOnlyRecallResults(false);
    setRecallPanelMode("results");
    setTab("add");
    setLeftPanelOpen(true);
  }

  async function runRecall(): Promise<void> {
    if (occurredFrom && occurredTo && occurredFrom > occurredTo) {
      setMessage("时间范围无效：结束日期不能早于开始日期。");
      setFilterOpen(true);
      return;
    }
    setFilterOpen(false);
    setTab("recall");
    setLeftPanelOpen(true);
    if (!canRecall) {
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
    setRecallPanelMode("results");
    setRecallResultFilter("all");
    setMessage("正在执行真实 recall…");
    const response = await fetch("/api/memory-audit/recall", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildRecallRequestPayload(query, elfieId, {
        ...recallObjectFilters,
        placeNodeId: sceneLocationId,
        sense: sceneSense,
        occurredFrom,
        occurredTo,
        minimumImportance: minimumImportance == null ? null : minimumImportance / 100,
      })),
    });
    if (!response.ok) { setMessage(await response.text()); return; }
    const next = await response.json() as RecallReport;
    next.bundle.focus_nodes = next.bundle.focus_nodes.map((node) => normalizeNode(node as AuditItem & { node_id?: string }));
    next.search_time = next.snapshot.generated_at;
    setTraceRecall(null);
    setRecall(next);
    setMessage("");
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
  function selectEpisode(id: string): void {
    setSelectedEpisodeId(id);
    setSelectedId("");
    setSelectedEdgeId("");
    setSelectedEvidenceId("");
    setDetailSelection("episode");
    setDetailPanelOpen(true);
  }
  function showEpisode(id: string): void {
    const nextId = toggleEpisodeSelection(selectedEpisodeId, id);
    if (nextId) selectEpisode(nextId);
    else {
      setSelectedEpisodeId("");
      setSelectedId("");
      setSelectedEdgeId("");
      setSelectedEvidenceId("");
      setDetailSelection(null);
      setDetailPanelOpen(false);
    }
  }
  function showEvidence(id: string): void {
    setSelectedId("");
    setSelectedEdgeId("");
    setSelectedEpisodeId("");
    setSelectedEvidenceId(id);
    setDetailSelection("evidence");
    setDetailPanelOpen(true);
  }
  const renderedGraphEdges = [...graph.edges, ...previewGraphEdges];
  function graphEdgeIdForAssertion(assertionId: string): string {
    return renderedGraphEdges.find((edge) => edge.assertionIds.includes(assertionId))?.id ?? assertionId;
  }
  function showAssertion(id: string): void {
    setSelectedId("");
    setSelectedEpisodeId("");
    setSelectedEvidenceId("");
    setSelectedEdgeId(graphEdgeIdForAssertion(id));
    setDetailSelection("edge");
    setDetailPanelOpen(true);
  }
  const selectedEdge = renderedGraphEdges.find((edge) => edge.id === selectedEdgeId) ?? null;
  const selectedEdgeTargetId = selectedEdge ? endpointId(selectedEdge.target) : "";
  const selectedAssertionRecords = new Map<string, AuditRecord>([
    ...visibleAssertions.map((item) => [String(item.assertion_id), item] as const),
    ...(preview?.changes.affected.assertions ?? []).map((item) => [String(item.assertion_id), item] as const),
  ]);
  const selectedEdgeRecords = selectedEdge
    ? selectedEdge.assertionIds.map((id) => selectedAssertionRecords.get(id)).filter((item): item is AuditRecord => item !== undefined)
    : [];
  const selectedNodeAssertions = selected ? visibleAssertions.filter((item) => String(item.subject_id) === selected.id || String(item.object_node_id) === selected.id) : [];
  const selectedNodeEvidence = [...new Map(selectedNodeAssertions.flatMap((item) => (Array.isArray(item.evidence_ids) ? item.evidence_ids : []).map(String)).map((id) => [id, report?.data.evidence.find((item) => String(item.evidence_id) === id)]).filter((entry): entry is [string, AuditRecord] => entry[1] != null))].map(([, item]) => item);
  const selectedEpisodeSourceRefs = recordArray(selectedEpisode, "source_refs");
  const inspectorNodeById = new Map<string, InspectorNode>((report?.data.nodes ?? []).map((node) => [node.id, node as InspectorNode]));
  const selectedEdgeSourceLabel = selectedEdge ? inspectorNodeById.get(endpointId(selectedEdge.source))?.label ?? endpointId(selectedEdge.source) : "";
  const selectedEdgeTargetLabel = selectedEdge ? inspectorNodeById.get(selectedEdgeTargetId)?.label ?? selectedEdgeTargetId : "";
  const inspectorEvidenceById = new Map<string, AuditRecord>((report?.data.evidence ?? []).map((item) => [String(item.evidence_id), item]));
  const inspectorEpisodeById = new Map<string, AuditRecord>((report?.data.episodes ?? []).map((item) => [String(item.episode_id), item]));
  const inspectorRelationInput = {
    nodeById: inspectorNodeById,
    evidenceById: inspectorEvidenceById,
    episodes: report?.data.episodes ?? [],
    relationKind: (record: AuditRecord | null, fallback?: string) => relationKindFromRecord(record, fallback, report),
    relationLabel: (kind: string) => relationDisplayLabel(kind, report),
    relationSentence: (source: string, target: string, kind: string, sourceKind?: string, targetKind?: string) => relationSentence(source, target, kind, sourceKind, targetKind, report),
    nodeTypeLabel: (kind: string | undefined) => nodeTypeLabel(kind ?? "unknown", report),
  };
  const selectedNodeProjection = selected ? projectNodeDetail(selected, { ...inspectorRelationInput, assertions: visibleAssertions }) : null;
  const selectedAssertionProjections = selectedEdgeRecords.map((record) => ({
    record,
    projection: projectAssertionDetail({
      ...record,
      symmetric: relationIsSymmetric(relationKindFromRecord(record, "关系", report), report),
    }, inspectorRelationInput),
  }));
  const selectedEpisodeProjection = selectedEpisode
    ? projectEpisodeDetail(selectedEpisode, { assertions: visibleAssertions, evidence: report?.data.evidence ?? [], nodeById: inspectorNodeById, nodeTypeLabel: inspectorRelationInput.nodeTypeLabel })
    : null;
  const selectedEvidenceProjection = selectedEvidence
    ? projectEvidenceDetail(selectedEvidence, visibleAssertions, inspectorEpisodeById)
    : null;
  const selectedEdgeNodeIds = new Set([selectedEdge ? endpointId(selectedEdge.source) : "", selectedEdgeTargetId].filter(Boolean));
  // The initial node is only a detail-panel default; it must not turn the whole
  // library into a dimmed focus view before the developer performs an action.
  // Selection is an independent overlay. Only search/recall or an isolated
  // preview creates the background state that dims unrelated graph elements.
  const hasBackgroundHighlight = Boolean(recallView || preview);
  const highlightedNodeIds = new Set([
    ...selectedEpisodeNodeIds,
    ...selectedEdgeNodeIds,
    ...recalledNodeIds,
    ...recalledAssertionNodeIds,
    ...previewNodeIds,
    ...previewAssertionNodeIds,
  ]);
  const predicateFilterOptions = (report?.ontology?.predicates ?? [])
    .filter((item) => item.status === "active" && (report?.predicate_counts[item.predicate] ?? 0) > 0)
    .map((item) => ({ ...item, count: report?.predicate_counts[item.predicate] ?? 0 }));
  const predicateFilterSelectOptions = predicateFilterOptions.map((item) => ({
    value: item.predicate,
    label: <span className="memory-debug-filter-option"><span>{item.label} · {item.predicate}</span><b>{item.count}</b></span>,
    title: "",
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
  const recallDisplayResults = recallView ? buildRecallDisplayResults(recallView.bundle, recallView.selection.candidates) : [];
  const recallDisplayResultCounts = countRecallDisplayResults(recallDisplayResults);
  const visibleRecallDisplayResults = filterRecallDisplayResults(recallDisplayResults, recallResultFilter);
  const recallCandidates = recallView?.selection.candidates ?? [];
  const recallCandidateCounts = new Map<string, number>();
  recallCandidates.forEach((candidate) => {
    const key = recallCandidateKey(candidate);
    recallCandidateCounts.set(key, (recallCandidateCounts.get(key) ?? 0) + 1);
  });
  const recallUniqueCandidateCount = recallCandidateCounts.size;
  const recallDuplicateRowCount = Math.max(0, recallCandidates.length - recallUniqueCandidateCount);
  const recallKeptCandidates = recallCandidates.filter((candidate) => candidate.kept);
  const recallExcludedCandidates = recallCandidates.filter((candidate) => !candidate.kept);
  const recallSortedCandidates = sortRecallCandidates(recallKeptCandidates);
  const recallRequestText = recordText(recallView?.request ?? null, "text", "") || recordText(recallView?.request ?? null, "query", "") || "（无文本，按场景检索）";
  const recalledSense = recallView?.request?.sense as { emotion_label?: string; intensity?: number } | undefined;
  const recallFilterSummary = [
    ...recordStringArray(recallView?.request ?? null, "place_node_ids").map((id) => `地点：${report?.data.nodes.find((node) => node.id === id)?.label ?? id}`),
    ...(recalledSense?.emotion_label ? [`情绪：${SCENE_EMOTIONS.find(({ key }) => key === recalledSense.emotion_label)?.label ?? recalledSense.emotion_label}${recalledSense.intensity == null ? "" : ` ${Math.round(recalledSense.intensity * 100)}%`}`] : []),
    ...recordStringArray(recallView?.request ?? null, "record_kinds"),
    ...recordStringArray(recallView?.request ?? null, "node_types"),
    ...recordStringArray(recallView?.request ?? null, "relation_types"),
    ...["occurred_from", "occurred_to"].map((key) => recordText(recallView?.request ?? null, key, "")).filter(Boolean),
    ...(recordNumber(recallView?.request ?? null, "minimum_importance") == null ? [] : [`重要度 ≥ ${recordNumber(recallView?.request ?? null, "minimum_importance")}`]),
  ];
  const recallRouteSummaries = [...new Set((recallView?.selection.candidates ?? []).map((candidate) => recallRouteLabel(candidate.source)))];
  const observedRecallSources = new Set((recallView?.selection.candidates ?? []).map((candidate) => candidate.source).filter((source): source is string => Boolean(source)));
  const recallRouteStates = [
    {
      source: "lexical",
      label: "Query · 文本",
      active: Boolean(recallView && (recallRequestText !== "（无文本，按场景检索）" || observedRecallSources.has("lexical") || recallRouteSummaries.includes("Query · 文本"))),
    },
    {
      source: "sense",
      label: "Sense · 场景",
      active: Boolean(recallView && (recalledSense || observedRecallSources.has("sense") || recallRouteSummaries.includes("Sense · 场景"))),
    },
    {
      source: "kinship",
      label: "Graph · 亲属",
      active: Boolean(recallView && (recallView.request?.kinship != null || observedRecallSources.has("kinship") || recallRouteSummaries.includes("Graph · 亲属"))),
    },
  ];
  const recallRouteCandidates = recallRouteStates.map((route) => ({
    ...route,
    candidates: recallCandidates.filter((candidate) => candidate.source === route.source),
  }));
  const selectedRecallRouteSource = recallRouteCandidates.some((route) => route.source === selectedRecallRoute)
    ? selectedRecallRoute
    : recallRouteCandidates.find((route) => route.active)?.source ?? recallRouteCandidates[0]?.source ?? "lexical";
  const selectedRecallRouteData = recallRouteCandidates.find((route) => route.source === selectedRecallRouteSource) ?? recallRouteCandidates[0];
  const Graph3D = ForceGraph3DComponent;
  const recallProcess = [
    { label: RECALL_PROCESS_LABELS[0], detail: recallView ? recallRouteCandidates.map((route) => `${route.label}：${recallRouteStatusLabel(route.active, route.candidates.length)}`).join(" · ") : "等待执行", state: recallView ? "done" : "idle" },
    { label: RECALL_PROCESS_LABELS[1], detail: recallView ? `观测候选 ${recallCandidates.length} · 唯一候选 ${recallUniqueCandidateCount} · 重复行 ${recallDuplicateRowCount}` : "等待候选", state: recallView ? "done" : "idle" },
    { label: RECALL_PROCESS_LABELS[2], detail: recallView ? `保留 ${recallKeptCandidates.length} · 淘汰 ${recallExcludedCandidates.length}${recallFilterSummary.length ? ` · 条件：${recallFilterSummary.join("、")}` : " · 无显式过滤条件"}` : "等待候选", state: recallView ? "done" : "idle" },
    { label: RECALL_PROCESS_LABELS[3], detail: recallView ? `输出顺序 ${recallSortedCandidates.length} 条 · 优先使用 rank，再按 score 稳定排序` : "等待候选", state: recallView ? "done" : "idle" },
    { label: RECALL_PROCESS_LABELS[4], detail: recallView ? `${recallView.bundle.focus_nodes.length} Node · ${recallView.bundle.episodes.length} Episode · ${recallView.bundle.assertions.length} 关系 · ${recallView.bundle.evidence.length} Evidence` : "等待回执", state: recallView ? "done" : "idle" },
  ];

  function renderRecallProcessStage(index: number): ReactNode {
    if (!recallView) return <p className="memory-debug-stage-empty">等待 Recall 回执。</p>;
    if (index === 0) return <div className="memory-debug-recall-route-tabs-shell">
      <div className="memory-debug-recall-route-tabs" role="tablist" aria-label="三路搜索">
        {recallRouteCandidates.map((route) => {
          const selected = route.source === selectedRecallRouteSource;
          return <button
            type="button"
            role="tab"
            key={route.source}
            id={`memory-debug-recall-route-tab-${route.source}`}
            aria-selected={selected}
            aria-controls={`memory-debug-recall-route-panel-${route.source}`}
            data-route-source={route.source}
            className={`memory-debug-recall-route-tab ${route.active ? "is-active" : "is-inactive"} ${selected ? "is-selected" : ""}`}
            onClick={() => setSelectedRecallRoute(route.source)}
          >
            <span className="memory-debug-recall-route-tab-label">{route.label} <strong>({route.candidates.length})</strong></span>
            <small>{route.active ? "已执行" : "未执行"}</small>
          </button>;
        })}
      </div>
      {selectedRecallRouteData && <section
        className={`memory-debug-recall-route-panel ${selectedRecallRouteData.active ? "is-active" : "is-inactive"}`}
        role="tabpanel"
        id={`memory-debug-recall-route-panel-${selectedRecallRouteData.source}`}
        aria-labelledby={`memory-debug-recall-route-tab-${selectedRecallRouteData.source}`}
      >
        <div className="memory-debug-recall-route-stage-head">
          <strong>{selectedRecallRouteData.label}</strong>
          <span>{recallRouteStatusLabel(selectedRecallRouteData.active, selectedRecallRouteData.candidates.length)}</span>
        </div>
        <RecallStageCandidateList
          candidates={selectedRecallRouteData.candidates}
          stage="route"
          emptyText={selectedRecallRouteData.active ? "这一路已执行，但回执没有逐候选记录。" : "本次请求没有执行这一路。"}
        />
      </section>}
    </div>;
    if (index === 1) return <>
      <div className="memory-debug-stage-summary-grid" aria-label="合并去重统计">
        <div><span>输入候选</span><strong>{recallCandidates.length}</strong><small>三路回执中可见</small></div>
        <div><span>唯一候选</span><strong>{recallUniqueCandidateCount}</strong><small>按类型与 ID</small></div>
        <div><span>重复行</span><strong>{recallDuplicateRowCount}</strong><small>{recallDuplicateRowCount ? "进入去重" : "未发现重复"}</small></div>
      </div>
      <p className="memory-debug-stage-note">候选回执没有单独提供“合并前/合并后”快照，下面按当前回执中的候选键展示可比对结果。</p>
      <RecallStageCandidateList candidates={recallCandidates} stage="merge" duplicateCounts={recallCandidateCounts} emptyText="回执没有提供可比对的候选。" />
    </>;
    if (index === 2) return <>
      <div className="memory-debug-stage-summary-grid" aria-label="过滤统计">
        <div><span>保留</span><strong>{recallKeptCandidates.length}</strong><small>进入排序</small></div>
        <div><span>淘汰</span><strong>{recallExcludedCandidates.length}</strong><small>{recallExcludedCandidates.length ? "显示淘汰原因" : "本次没有候选被过滤"}</small></div>
      </div>
      <p className="memory-debug-stage-note">{recallFilterSummary.length ? `过滤条件：${recallFilterSummary.join("、")}` : "本次没有显式过滤条件。"}</p>
      <RecallStageCandidateList candidates={recallCandidates} stage="filter" emptyText="回执没有提供过滤阶段候选。" />
    </>;
    if (index === 3) return <>
      <p className="memory-debug-stage-note">按回执 rank 排列；没有 rank 的候选再按 score 从高到低排列，最后用候选键稳定排序。</p>
      <RecallStageCandidateList candidates={recallSortedCandidates} stage="sort" emptyText="回执没有提供可排序的候选。" />
    </>;
    return <>
      <div className="memory-debug-stage-summary-grid" aria-label="输出统计">
        <div><span>Node</span><strong>{recallView.bundle.focus_nodes.length}</strong><small>关联节点</small></div>
        <div><span>Episode</span><strong>{recallView.bundle.episodes.length}</strong><small>经历</small></div>
        <div><span>关系 / Evidence</span><strong>{recallView.bundle.assertions.length} / {recallView.bundle.evidence.length}</strong><small>可追溯输出</small></div>
      </div>
      <RecallStageOutputList results={recallDisplayResults} typeLabel={(nodeType) => nodeTypeLabel(nodeType, report)} />
    </>;
  }
  const searchMode = isMemoryDebugSearchMode(tab, leftPanelOpen);
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
      showAssertion(nodeId.replace(/^literal:/, ""));
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

  function graphLinkState(link: Graph3DLink): { linkId: string; isReturned: boolean; isAffected: boolean; isSelected: boolean; color: string } {
    const linkId = String(link.id ?? "");
    const isReturned = link.assertionIds.some((id) => recalledAssertionIds.has(id));
    const isAffected = link.assertionIds.some((id) => selectedEpisodeAssertionIds.has(id) || previewAssertionIds.has(id)) || link.kind === "preview-assertion";
    const isSelected = selectedEdgeId === linkId;
    return {
      linkId,
      isReturned,
      isAffected,
      isSelected,
      color: graphLinkArrowColor(hasBackgroundHighlight, selectedEdgeId, linkId, link.kind, isReturned, isAffected),
    };
  }

  const graphUnavailable = <div className="memory-debug-3d-loading" role="status">当前浏览器无法加载 3D 记忆图谱，请启用 WebGL。</div>;

  return <main className={`memory-debug-page${embedded ? " memory-debug-page-embedded" : ""}${filterOpen ? " memory-debug-filter-open" : ""}${leftPanelOpen ? " memory-debug-left-panel-open" : ""}${detailPanelOpen ? " memory-debug-right-panel-open" : ""}${leftPanelOpen && detailPanelOpen ? " memory-debug-two-drawers" : ""}`}>
    <div className="memory-debug-graph-canvas" ref={graphCanvasRef} aria-label="真实记忆来源链">
      <header className="memory-debug-topbar">
        <div className="memory-debug-topbar-left">
          <div className="memory-debug-search-group">
            <Input.Search
              aria-label="搜索记忆"
              className="memory-debug-query"
              value={query}
              onChange={(event) => {
                const nextQuery = event.target.value;
                if (!nextQuery) clearSearch();
                else setQuery(nextQuery);
              }}
              onSearch={() => { void runRecall(); }}
              placeholder="搜索 Node、Assertion、Episode…"
              prefix={<SearchOutlined aria-hidden="true" />}
              allowClear
              enterButton="搜索"
            />
            <Button ref={filterTriggerRef} type="default" className={`memory-debug-filter-trigger${filterOpen ? " is-active" : ""}`} aria-label="高级选项" aria-expanded={filterOpen} aria-haspopup="dialog" onClick={openFilter}>
              高级{activeFilterCount ? ` · ${activeFilterCount}` : ""}<DownOutlined className={`memory-debug-advanced-caret${filterOpen ? " is-open" : ""}`} />
            </Button>
            {filterOpen && <section ref={filterPopoverRef} className="memory-debug-filter-popover" aria-label="高级" role="dialog">
              <section className="memory-debug-options-block memory-debug-scene-inputs" aria-labelledby="memory-debug-scene-title">
                <div className="memory-debug-options-heading"><strong id="memory-debug-scene-title">场景</strong></div>
                <div className="memory-debug-options-row">
                  <span className="memory-debug-options-label" title="当前支持一种情绪及其强度；输入另一项会替换">情绪<br /><small>单选</small></span>
                  <div className="memory-debug-emotion-grid" role="group" aria-label="情绪强度">
                    {SCENE_EMOTIONS.map(({ key, label }) => <label className="memory-debug-emotion-control" key={key}>
                      <span>{label}</span>
                      <InputNumber
                        aria-label={`${label}强度`}
                        controls={false}
                        min={0}
                        max={100}
                        step={1}
                        precision={0}
                        value={sceneEmotionValues[key] ?? null}
                        onChange={(value) => setSceneEmotionValues(value == null ? {} : { [key]: value })}
                      />
                    </label>)}
                  </div>
                </div>
                <div className="memory-debug-options-row">
                  <label className="memory-debug-options-label" htmlFor="memory-debug-scene-location">地点</label>
                  <Select
                    id="memory-debug-scene-location"
                    className="memory-debug-scene-location-select"
                    aria-label="场景地点"
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    options={(report?.data.nodes ?? [])
                      .filter((node) => node.node_type === "place" || node.node_type === "cosmic_entity")
                      .map((node) => ({ label: node.label, value: node.id, title: "" }))}
                    value={sceneLocationId}
                    onChange={(value: string | undefined) => setSceneLocationId(value)}
                    placeholder="搜索并选择地点"
                    popupClassName="memory-debug-filter-select-dropdown"
                  />
                </div>
                <div className="memory-debug-options-row">
                  <span className="memory-debug-options-label">感知<br /><small>暂不支持</small></span>
                  <ConfigProvider componentDisabled><div className="memory-debug-perception-fields">
                    <label>看到<Input aria-label="看到的内容" value={sceneVisibleCue} onChange={(event) => setSceneVisibleCue(event.target.value)} /></label>
                    <label>触感<Input aria-label="触感内容" value={sceneTouchCue} onChange={(event) => setSceneTouchCue(event.target.value)} /></label>
                    <label>温度<InputNumber aria-label="环境温度" value={sceneTemperature} onChange={setSceneTemperature} min={-80} max={80} step={1} controls={false} addonAfter="°C" /></label>
                    <label>湿度<InputNumber aria-label="环境湿度" value={sceneHumidity} onChange={setSceneHumidity} min={0} max={100} step={1} controls={false} addonAfter="%" /></label>
                    <label>光照<InputNumber aria-label="环境光照" value={sceneIlluminance} onChange={setSceneIlluminance} min={0} step={1} controls={false} addonAfter="lx" /></label>
                  </div></ConfigProvider>
                </div>
              </section>
              <div className="memory-debug-options-divider" />
              <section className="memory-debug-options-block memory-debug-filter-section" aria-labelledby="memory-debug-filter-title">
                <div className="memory-debug-options-heading"><strong id="memory-debug-filter-title">过滤</strong></div>
                <div className="memory-debug-filter-controls-row">
                  <div className="memory-debug-filter-compact-field memory-debug-filter-object-field">
                    <label className="memory-debug-options-label" htmlFor="memory-debug-object-filter">对象</label>
                    <ConfigProvider theme={{ components: { TreeSelect: { titleHeight: 24, indentSize: 24 } } }}>
                      <TreeSelect
                        id="memory-debug-object-filter"
                        aria-label="搜索对象"
                        treeCheckable
                        showSearch
                        allowClear
                        showCheckedStrategy={TreeSelect.SHOW_PARENT}
                        maxTagCount={2}
                        treeData={buildRecallObjectTree(report?.ontology)}
                        value={recallObjectValues}
                        onChange={(values: string[]) => setRecallObjectValues(values ?? [])}
                        placeholder="全部对象"
                        popupClassName="memory-debug-object-tree-dropdown"
                        popupMatchSelectWidth={false}
                        treeDefaultExpandAll={false}
                        treeLine
                      />
                    </ConfigProvider>
                  </div>
                  <div className="memory-debug-filter-compact-field memory-debug-filter-time-field">
                    <span className="memory-debug-options-label">时间窗口</span>
                    <ConfigProvider locale={zhCN}>
                      <DatePicker.RangePicker
                        aria-label="记忆时间范围"
                        className="memory-debug-date-range-picker"
                        classNames={{ popup: { root: "memory-debug-date-picker-dropdown" } }}
                        defaultPickerValue={[latestMemoryDate, latestMemoryDate]}
                        format="YYYY-MM-DD"
                        inputReadOnly
                        locale={zhCN.DatePicker!}
                        maxDate={latestMemoryDate}
                        minDate={earliestMemoryDate}
                        onChange={(dates) => {
                          setOccurredFrom(dates?.[0]?.format("YYYY-MM-DD") ?? "");
                          setOccurredTo(dates?.[1]?.format("YYYY-MM-DD") ?? "");
                        }}
                        placeholder={["开始日期", "结束日期"]}
                        popupAlign={{ offset: [-80, 0], overflow: { adjustX: true, adjustY: true } }}
                        size="small"
                        suffixIcon={<CalendarOutlined />}
                        value={timeRangePickerValue}
                      />
                    </ConfigProvider>
                  </div>
                  <div className="memory-debug-filter-compact-field memory-debug-filter-importance-field">
                    <label className="memory-debug-options-label" htmlFor="memory-debug-min-importance">最低重要度</label>
                    <InputNumber id="memory-debug-min-importance" aria-label="最低重要度" className="memory-debug-importance-control" min={0} max={100} step={1} precision={0} controls={false} value={minimumImportance} onChange={(value) => setMinimumImportance(value)} placeholder="不限" addonAfter="%" />
                  </div>
                </div>
              </section>
              <div className="memory-debug-filter-actions"><button type="button" onClick={clearSearchFilters} disabled={!activeFilterCount}>重置</button><button type="button" className="is-primary" onClick={() => { void runRecall(); }} disabled={!canRecall}>应用并搜索</button></div>
            </section>}
          </div>
          <div className="memory-debug-operation-actions">
            <Button type="primary" className="memory-debug-command-button" icon={<PlusOutlined />} onClick={openAddPanel} aria-label="添加 Episode">添加</Button>
            <Button type="default" className="memory-debug-command-button memory-debug-consolidation-trigger" icon={<ThunderboltOutlined />} onClick={() => void runManualConsolidation()} disabled={!elfieId || consolidationRunning} aria-label="手动触发 Consolidation">{consolidationRunning ? "整理中…" : "手动整理"}</Button>
          </div>
        </div>
        <div className="memory-debug-top-actions">
          <button type="button" className={layoutLocked ? "is-active" : ""} aria-pressed={layoutLocked} aria-label={layoutLocked ? "允许拖拽节点" : "锁定节点"} onClick={() => setLayoutLocked((locked) => !locked)}>{layoutLocked ? "允许拖拽节点" : "锁定节点"}</button>
          <button type="button" onClick={() => fitGraph()} aria-label="适配当前图谱">适配当前图谱</button>
          <button type="button" onClick={resetGraph} aria-label="重置视图状态">重置视图</button>
          {embedded && onClose ? <button type="button" className="memory-debug-topbar-close" onClick={onClose} aria-label="关闭记忆图谱浮窗">×</button> : null}
        </div>
      </header>

      {readError && <div className={`memory-debug-read-notice memory-debug-read-notice-${readPhase}`} role="alert"><strong>{readPhase === "stale" ? "读取边界已过期" : readPhase === "error" ? "Memory 读取失败" : "Memory 读取状态"}</strong><span>{readError}</span><button onClick={() => void loadReport()}>重试</button></div>}
      {readPhase === "empty" && <div className="memory-debug-read-notice memory-debug-read-notice-empty" role="status"><strong>当前 Memory 为空</strong><span>没有可绘制的 Episode、Node、Assertion 或 Evidence；可以打开右侧“添加 Episode”做隔离预演。</span></div>}

      {loading && !report ? <div className="memory-debug-empty">正在读取真实 Memory…</div> : <>
          <div className="memory-debug-memory-cards" aria-label="Episode 时间线">{visibleEpisodes.map((episode) => {
            const episodeId = String(episode.episode_id);
            const isSelected = selectedEpisodeId === episodeId;
            const summary = episodeCardDisplayTitle(episode);
            const details = episodeCardTooltip(episode);
            return <button ref={(element) => { if (element) episodeCardRefs.current.set(episodeId, element); else episodeCardRefs.current.delete(episodeId); }} className={isSelected ? "is-active" : ""} key={episodeId} title={details} aria-label={details} onClick={() => showEpisode(episodeId)} aria-pressed={isSelected}>
              <span className="memory-debug-episode-time">{formatEpisodeTime(episode)}</span>
              <strong className="memory-debug-episode-title">{summary}</strong>
              <span className="memory-debug-episode-meta">{episodeEventKindLabel(episode.event_kind)} · {episodeMaintenanceLabel(episode)}</span>
            </button>;
          })}</div>
          <MemoryNodeFilter ontology={report?.ontology} group={selectedTypeGroup} selectedTypes={selectedTypes}
            onGroupChange={group => { setSelectedTypeGroup(group); setSelectedTypes([]); }}
            onTypesChange={types => setSelectedTypes(selectMemoryNodeTypes(types, selectedTypeGroup, report?.ontology?.node_types ?? []).nodeTypes)} />
          <details className="memory-debug-graph-filter-details memory-debug-graph-filter-outside">
            <summary>图谱显示条件{activeGraphFilterCount ? ` · ${activeGraphFilterCount}` : ""}</summary>
            <div className="memory-debug-graph-filter-grid">
              <label>关系类型<Select aria-label="图谱关系类型" mode="multiple" allowClear maxTagCount="responsive" onChange={(values: string[]) => setSelectedPredicates(values)} options={predicateFilterSelectOptions} placeholder="全部关系类型" popupClassName="memory-debug-filter-select-dropdown" popupMatchSelectWidth={false} value={selectedPredicates} /></label>
              <label>生命周期<Select aria-label="图谱生命周期" onChange={(value: string) => setLifecycleFilter(value || "all")} options={[{ label: "全部", value: "all", title: "" }, { label: "活动 active", value: "active", title: "" }, { label: "已归档 archived", value: "archived", title: "" }, { label: "已遗忘 forgotten", value: "forgotten", title: "" }, { label: "未知 unknown", value: "unknown", title: "" }]} popupClassName="memory-debug-filter-select-dropdown" popupMatchSelectWidth={false} value={lifecycleFilter} /></label>
              <label>最低置信度<Select aria-label="图谱最低置信度" onChange={(value: string) => setConfidenceFilter(value || "all")} options={[{ label: "全部", value: "all", title: "" }, { label: "≥ 50%", value: "0.5", title: "" }, { label: "≥ 80%", value: "0.8", title: "" }]} popupClassName="memory-debug-filter-select-dropdown" popupMatchSelectWidth={false} value={confidenceFilter} /></label>
              <button type="button" onClick={clearGraphDisplayFilters} disabled={!activeGraphFilterCount}>重置图谱条件</button>
            </div>
          </details>
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
            {webglStatus === "checking" ? <div className="memory-debug-3d-loading">正在加载 3D 记忆图谱…</div> : webglStatus === "available" && Graph3D ? <WebGLGraphErrorBoundary fallback={graphUnavailable}><Graph3D
              ref={graphRef}
              graphData={graphData}
              width={graphViewport.width || 800}
              height={graphViewport.height || 580}
              backgroundColor="#07131f"
              nodeRelSize={GRAPH_NODE_REL_SIZE}
              nodeResolution={24}
              nodeOpacity={1}
              nodeVal={(node) => node.val}
              nodeColor={(node) => {
                const nodeId = String(node.id ?? "");
                const isSelected = selectedId === nodeId;
                const isReturned = recalledNodeIds.has(nodeId);
                const isAffected = selectedEpisodeNodeIds.has(nodeId) || previewNodeIds.has(nodeId) || previewAssertionNodeIds.has(nodeId);
                const isRelated = selectedEdgeNodeIds.has(nodeId) || recalledAssertionNodeIds.has(nodeId);
                const isHighlighted = isSelected || isReturned || isAffected || isRelated || highlightedNodeIds.has(nodeId);
                if (node.preview) return "#ff9d57";
                if (hasBackgroundHighlight && !isHighlighted) return "#1f3b50";
                return node.color ?? graphNodeColor(node.kind, report);
              }}
              nodeLabel={(node) => `<strong>${escapeHtml(node.label)}</strong><br/><small>${escapeHtml(node.typeLabel ?? nodeTypeLabel(node.kind, report))} · ${node.degree} 条关系${node.preview ? " · 隔离预演" : ""}</small>`}
              nodeThreeObject={nodeLabelObject}
              nodeThreeObjectExtend
              linkLabel={(link) => `<strong>聚合关系</strong><br/>${escapeHtml(link.labels.join("、") || link.label)}<br/><small>${link.direction === "both" ? "双向" : "单向"} · ${link.assertionIds.length} 条 Assertion · 最高重要度 ${link.importance == null ? "未记录" : `${Math.round(link.importance * 100)}%`}</small>`}
              linkColor={(link) => graphRenderColor(graphLinkState(link).color)}
              linkWidth={(link) => graphLinkWidth(link.importance)}
              // Keep one deterministic source → target arrow for each
              // aggregated relation. A `both` relation is still reported as
              // 双向 in the label and inspector; the graph stays on the
              // library's native single-arrow path instead of adding a
              // second hand-positioned Cone.
              linkDirectionalArrowLength={(link) => {
                const state = graphLinkState(link);
                return graphLinkArrowLength(hasBackgroundHighlight, selectedEdgeId, state.linkId, link.kind, state.isReturned, state.isAffected);
              }}
              linkDirectionalArrowColor={(link) => {
                const state = graphLinkState(link);
                return graphRenderColor(graphLinkArrowColor(hasBackgroundHighlight, selectedEdgeId, state.linkId, link.kind, state.isReturned, state.isAffected));
              }}
              linkDirectionalArrowRelPos={MEMORY_DEBUG_GRAPH_ARROW_REL_POS}
              linkOpacity={GRAPH_LINK_OPACITY}
              linkResolution={8}
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
              onEngineStop={() => { updateTracePositions(); scheduleGraphLabelOcclusion(); if (graphFitPendingRef.current) fitGraph(); }}
              onNodeClick={handleGraphNodeClick}
              onLinkClick={handleGraphLinkClick}
            /></WebGLGraphErrorBoundary> : graphUnavailable}
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
        </>}
      <footer className="memory-debug-footer"><span className="memory-debug-counts">当前视图：{graph.nodes.filter((node) => !["episode", "evidence"].includes(node.kind)).length} Node · {graph.edges.filter((edge) => edge.kind === "assertion").length} 聚合关系 · {graph.edges.filter((edge) => edge.kind === "assertion").reduce((count, edge) => count + edge.assertionIds.length, 0)} Assertion · {visibleEpisodes.length} Episode · {loadedEvidenceCount} Evidence　|　全库：{totalNodeCount} Node · {report?.counts.assertions ?? 0} Assertion · {report?.counts.episodes ?? 0} Episode · {totalEvidenceCount} Evidence</span>
          <MemoryDebugLegend
            layoutLocked={layoutLocked}
            showSources={Boolean(selectedEpisode && [...selectedEpisodeNodeIds].some(id => graphNodeIds.has(id) && tracePositions[id]))}
          />
      </footer>

      {detailPanelOpen && <aside className="memory-debug-drawer memory-debug-drawer-right" aria-label="详情面板">
        <div className="memory-debug-drawer-head"><div><strong>详情</strong></div><div className="memory-debug-drawer-head-actions"><button type="button" aria-label="关闭详情面板" onClick={() => setDetailPanelOpen(false)}>×</button></div></div>
        <div className="memory-debug-inspector-context"><span>当前对象</span><strong>{detailSelection === "episode" && selectedEpisode ? "Episode 来源" : detailSelection === "edge" && selectedEdge ? `聚合关系 · ${selectedEdge.assertionIds.length} 条 Assertion` : detailSelection === "evidence" && selectedEvidence ? "Evidence 证据" : detailSelection === "node" && selected ? `${nodeLabel(selected)} Node` : "未选择"}</strong><small>{coverageLabel} · {coverageDetail}</small></div>
        <div className="memory-debug-drawer-scroll">
        <div className="memory-debug-panel">
          {detailSelection === "episode" && selectedEpisode && selectedEpisodeProjection ? <>
            <InspectorHeaderSummary header={selectedEpisodeProjection.header} className="memory-debug-episode-type" />
            <InspectorFieldGrid fields={projectedFields(selectedEpisodeProjection.fields)} />
            <h4>关联对象</h4>
            <InspectorConnections connections={selectedEpisodeProjection.connections} />
            <h4>来源证据 · {selectedEpisodeEvidence.length}</h4>
            {selectedEpisodeEvidence.length ? selectedEpisodeEvidence.map((item) => <button className="memory-debug-evidence-card" type="button" key={String(item.evidence_id)} onClick={() => showEvidence(String(item.evidence_id))}><strong>{String(item.evidence_id)}</strong><span>{String(item.excerpt ?? "没有摘录")}</span><small>{String(item.modality ?? "text")} · {String(item.attribution ?? item.stance ?? "未标注")} · {String(item.source_reliability_class ?? "可靠性未记录")}</small></button>) : <p>当前 Episode 尚未关联可见 Evidence。</p>}
            <h4>完整经历正文</h4><p className="memory-debug-long-content">{selectedEpisodeProjection.content}</p>
            <details className="memory-debug-raw-details"><summary>技术详情</summary><InspectorFieldGrid fields={projectedFields(selectedEpisodeProjection.technical)} /><div className="memory-debug-detail-list">{selectedEpisodeSourceRefs.map((source, index) => <div key={String(source.source_id ?? index)}><span>{recordText(source, "source_kind", "source")}</span><strong>{recordText(source, "source_id")}{source.locator ? ` · ${String(source.locator)}` : ""}</strong></div>)}</div></details>
          </> : detailSelection === "edge" && selectedEdge ? <>
            <div className="memory-debug-aggregate-header">
              <span className="memory-debug-type memory-debug-relation-type">聚合关系</span>
              <h2>{selectedEdge.labels.join("、") || selectedEdge.label}</h2>
              <p className="memory-debug-detail-copy memory-debug-relation-sentence">{selectedEdge.direction === "both" ? "双向关系" : "单向关系"} · {selectedEdgeSourceLabel} → {selectedEdgeTargetLabel}</p>
              <div className="memory-debug-inspector-stats" aria-label="聚合关系摘要">
                <div><span>底层 Assertion</span><strong>{selectedEdge.assertionIds.length}</strong></div>
                <div><span>最高重要度</span><strong>{selectedEdge.importance == null ? "未记录" : `${Math.round(selectedEdge.importance * 100)}%`}</strong></div>
                <div><span>方向</span><strong>{selectedEdge.direction === "both" ? "双向" : "单向"}</strong></div>
              </div>
            </div>
            <h4>关系明细 · {selectedEdge.assertionIds.length}</h4>
            {selectedAssertionProjections.length ? <div className="memory-debug-aggregate-assertions">{selectedAssertionProjections.map(({ record, projection }) => <article className="memory-debug-aggregate-assertion" key={String(record.assertion_id)}>
              <div className="memory-debug-aggregate-assertion-head"><strong>{projection.sentence}</strong><span>{projection.header.importance == null ? "重要度未记录" : `${Math.round(projection.header.importance * 100)}% 重要度`}</span></div>
              <InspectorFieldGrid fields={projectedFields(projection.fields)} />
              <h4>来源证据 · {projection.sources.length}</h4>
              {projection.sources.length ? projection.sources.map((source) => <button className="memory-debug-evidence-card" type="button" key={source.id} onClick={() => showEvidence(source.id)}><strong>{source.id}</strong><span>{source.excerpt || "没有摘录"}</span><small>{source.label}</small></button>) : <p>这条关系没有关联 Evidence。</p>}
              <details className="memory-debug-raw-details"><summary>技术详情与原始限定条件</summary><InspectorFieldGrid fields={projectedFields(projection.technical)} /></details>
            </article>)}</div> : <p>当前快照没有返回这些底层 Assertion 的完整记录。</p>}
          </> : detailSelection === "evidence" && selectedEvidence && selectedEvidenceProjection ? <>
            <InspectorHeaderSummary header={selectedEvidenceProjection.header} className="memory-debug-evidence-type" />
            <blockquote className="memory-debug-edge-evidence memory-debug-evidence-hero">{selectedEvidenceProjection.excerpt}</blockquote>
            <InspectorFieldGrid fields={projectedFields(selectedEvidenceProjection.fields)} />
            <h4>关联对象</h4>
            <InspectorConnections connections={selectedEvidenceProjection.connections} onAssertion={showAssertion} />
            <details className="memory-debug-raw-details"><summary>技术详情</summary><InspectorFieldGrid fields={projectedFields(selectedEvidenceProjection.technical)} /></details>
          </> : detailSelection === "node" && selected && selectedNodeProjection ? <>
            <InspectorHeaderSummary header={selectedNodeProjection.header} />
            <InspectorFieldGrid fields={projectedFields(selectedNodeProjection.fields)} />
            <h4>相关关系 · {selectedNodeProjection.connections.length}</h4>
            <InspectorConnections connections={selectedNodeProjection.connections} onAssertion={showAssertion} />
            <h4>来源证据 · {selectedNodeEvidence.length}</h4>
            {selectedNodeEvidence.length ? selectedNodeEvidence.map((item) => <button className="memory-debug-evidence-card" type="button" key={String(item.evidence_id)} onClick={() => showEvidence(String(item.evidence_id))}><strong>{String(item.evidence_id)}</strong><span>{String(item.excerpt ?? "没有摘录")}</span></button>) : <p>当前节点没有从可见关系追溯到 Evidence。</p>}
            <h4>被哪些 Episode 提到 · {selectedNodeProjection.sources.length}</h4>
            <InspectorSources sources={selectedNodeProjection.sources} onEpisode={showEpisode} />
            <details className="memory-debug-raw-details"><summary>技术详情</summary><InspectorFieldGrid fields={projectedFields(selectedNodeProjection.technical)} /></details>
          </> : <div className="memory-debug-empty-state"><strong>未选择对象</strong></div>}
        </div>
        </div>
      </aside>}

      {leftPanelOpen && <aside className="memory-debug-drawer memory-debug-drawer-left" aria-label={tab === "add" ? "添加 Episode 面板" : "搜索结果面板"}>
        <div className="memory-debug-drawer-head"><div><strong>{tab === "add" ? "添加 Episode" : <>{recallPanelMode === "details" ? "搜索详情" : "搜索结果"}{recallView && <><small className="memory-debug-drawer-count">· {recallDisplayResults.length} 条</small><small className="memory-debug-drawer-elapsed">· 总耗时 {formatRecallElapsed(recallView.elapsed_ms)}</small></>}</>}</strong></div><div className="memory-debug-drawer-head-actions">{searchMode && recallView && <><button type="button" className={`memory-debug-search-panel-toggle${recallPanelMode === "details" ? " is-active" : ""}`} aria-label={recallPanelMode === "details" ? "切换下方到搜索结果" : "切换下方到搜索详情"} title={recallPanelMode === "details" ? "切换下方到搜索结果" : "切换下方到搜索详情"} aria-pressed={recallPanelMode === "details"} onClick={() => setRecallPanelMode((mode) => mode === "results" ? "details" : "results")}><span aria-hidden="true">↓</span> {recallPanelMode === "details" ? "查看结果" : "查看详情"}</button><button type="button" className={`memory-debug-search-mode-toggle${showOnlyRecallResults ? " is-active" : ""}`} aria-label={showOnlyRecallResults ? "切换右侧到全部内容" : "切换右侧到仅看搜索结果"} title={showOnlyRecallResults ? "切换右侧到全部内容" : "切换右侧到仅看搜索结果"} aria-pressed={showOnlyRecallResults} onClick={() => setShowOnlyRecallResults((visible) => !visible)}><span aria-hidden="true">→</span> {showOnlyRecallResults ? "查看全部" : "查看结果"}</button></>}<button type="button" aria-label={tab === "add" ? "关闭添加 Episode 面板" : "关闭搜索结果面板"} onClick={() => { if (tab === "recall") clearSearch(true, false); else setLeftPanelOpen(false); }}>×</button></div></div>
        {tab === "add" && <div className="memory-debug-inspector-context"><span>当前操作</span><strong>隔离预演 · 不写生产库</strong><small>{coverageLabel} · {coverageDetail}</small></div>}
        <div className="memory-debug-drawer-scroll">
        {tab === "add" && <div className="memory-debug-panel">
          <h2>添加完整 Episode</h2>
          <div className="memory-debug-operation-banner"><strong>隔离预演</strong><span>不写生产库</span></div>
          <label className="memory-debug-field-label">Episode 内容<textarea value={episodeText} onChange={(event) => setEpisodeText(event.target.value)} rows={8} /></label>
          <button className="primary" disabled={previewLoading || !episodeText.trim()} onClick={() => void runEpisodePreview()}>{previewLoading ? "正在隔离预演…" : "开始隔离预演"}</button>
          <div className="memory-debug-process-rail memory-debug-process-rail-long" aria-label="添加 Episode 过程"><div className="memory-debug-process-caption"><strong>处理过程</strong></div>{addProcess.map((step) => <div className={`memory-debug-process-item is-${step.state}`} key={step.label}><span className="memory-debug-process-dot" /><strong>{step.label}</strong><small>{step.detail}</small></div>)}</div>
          {preview && <div className={`memory-debug-preview memory-debug-preview-${preview.operation.status}`}>
            <div className="memory-debug-preview-head"><strong>{preview.operation.status === "completed" ? "预演成功" : "预演未完成"}</strong><span>{preview.operation.elapsed_ms}ms · {preview.operation.mode}</span></div>
            <div className="memory-debug-operation-meta"><span>operation</span><strong>{preview.operation.operation_id}</strong><span>输入</span><strong>{preview.input.content_chars} chars</strong><span>生产写入</span><strong>{preview.operation.production_mutated ? "是 · 异常" : "否"}</strong></div>
            {preview.operation.production_mutated && <p>检测到生产写入，需立即停止审查。</p>}
            <div className="memory-debug-preview-counts">{(["episodes", "nodes", "assertions", "evidence_for_visible_assertions"] as const).map((key) => <div key={key}><span>{key}</span><strong>{preview.before.counts[key] ?? 0} → {preview.after.counts[key] ?? 0}</strong></div>)}</div>
            <h4>本次新增对象</h4>
            <div className="memory-debug-preview-ids">{Object.entries(preview.changes.added_ids).map(([key, ids]) => <span key={key}>{key}: {ids.length ? ids.join(", ") : "—"}</span>)}</div>
            {preview.error && <pre>{JSON.stringify(preview.error, null, 2)}</pre>}
            <details><summary>真实回执</summary><pre>{JSON.stringify(preview.receipt, null, 2)}</pre></details>
          </div>}
        </div>}
        {tab === "recall" && <div className="memory-debug-panel">
          {recallView && <>
            {recallPanelMode === "results" ? <div className="memory-debug-recall-result-surface" aria-label="Recall 返回摘要" data-recall-id={recallView.selection.recall_id ?? undefined}>
            <div className="memory-debug-recall-result-filters" role="group" aria-label="搜索结果统计与筛选">
              {(["all", "node", "episode", "assertion"] as const).map((filter) => {
                const labels: Record<RecallResultFilter, string> = { all: "全部", node: "节点", episode: "Episode", assertion: "关系 / 边" };
                return <button type="button" key={filter} className={recallResultFilter === filter ? "is-active" : undefined} aria-pressed={recallResultFilter === filter} onClick={() => setRecallResultFilter(filter)}><span>{labels[filter]}</span><strong>{recallDisplayResultCounts[filter]}</strong></button>;
              })}
            </div>
            {visibleRecallDisplayResults.length ? <div className="memory-debug-recall-result-list" aria-label="搜索结果列表">
              {visibleRecallDisplayResults.map((result, index) => <RecallResultCard
                key={result.key}
                result={result}
                index={index}
                typeLabel={(nodeType) => nodeTypeLabel(nodeType, report)}
                selected={
                  (result.kind === "node" && selectedId === result.id)
                  || (result.kind === "episode" && selectedEpisodeId === result.id)
                  || (result.kind === "assertion" && selectedEdgeId === graphEdgeIdForAssertion(result.id))
                }
                onOpenObject={(item) => {
                  if (item.kind === "node") showItem(item.id);
                  else if (item.kind === "episode") selectEpisode(item.id);
                  else showAssertion(item.id);
                }}
              />)}
            </div> : <p className="memory-debug-empty-result">本次 Recall 没有返回 Node、Episode 或关系结果。</p>}
            </div> : <div className="memory-debug-recall-details" aria-label="搜索详情">
            <div className="memory-debug-recall-step-list" aria-label="Recall 五步流水线">
              {recallProcess.map((step, index) => <details className={`memory-debug-recall-step is-${step.state}`} key={step.label}>
                <summary className="memory-debug-recall-step-summary">
                  <span className="memory-debug-recall-step-number">{index + 1}</span>
                  <span className="memory-debug-recall-step-copy"><strong>{step.label}</strong><small>{step.detail}</small></span>
                  <span className="memory-debug-recall-step-chevron" aria-hidden="true">⌄</span>
                </summary>
                <div className="memory-debug-recall-step-body">{renderRecallProcessStage(index)}</div>
              </details>)}
            </div>
            </div>}
          </>}
        </div>}
        </div>
      </aside>}
      {message && <p className="memory-debug-message" role="status">{message}</p>}
    </div>
  </main>;
}
