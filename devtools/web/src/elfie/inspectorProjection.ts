export type InspectorRecord = Record<string, unknown>;

export type InspectorNode = InspectorRecord & {
  id: string;
  label: string;
  node_type?: string;
  description?: string | null;
  status?: string | null;
  confidence?: number | null;
  importance?: number | null;
  freshness?: number | null;
  properties?: Record<string, unknown>;
};

export type InspectorField = {
  key: string;
  label: string;
  value: string;
  source: "property" | "description" | "assertion" | "episode" | "evidence" | "technical";
};

export type InspectorConnection = {
  id: string;
  label: string;
  detail: string;
  importance: number | null;
  confidence: number | null;
  kind: "relation" | "attribute" | "episode" | "evidence";
};

export type InspectorSource = {
  id: string;
  label: string;
  excerpt: string;
  kind: string;
};

export type InspectorHeader = {
  semanticType: string;
  label: string;
  summary: string;
  status: string;
  importance: number | null;
  confidence: number | null;
};

export type NodeInspectorDetail = {
  kind: "node";
  header: InspectorHeader;
  fields: InspectorField[];
  connections: InspectorConnection[];
  sources: InspectorSource[];
  technical: InspectorField[];
};

export type AssertionInspectorDetail = {
  kind: "assertion";
  header: InspectorHeader;
  sentence: string;
  fields: InspectorField[];
  connections: InspectorConnection[];
  sources: InspectorSource[];
  technical: InspectorField[];
};

export type EpisodeInspectorDetail = {
  kind: "episode";
  header: InspectorHeader;
  fields: InspectorField[];
  connections: InspectorConnection[];
  sources: InspectorSource[];
  technical: InspectorField[];
  content: string;
};

export type EvidenceInspectorDetail = {
  kind: "evidence";
  header: InspectorHeader;
  excerpt: string;
  fields: InspectorField[];
  connections: InspectorConnection[];
  sources: InspectorSource[];
  technical: InspectorField[];
};

export type InspectorDetail = NodeInspectorDetail | AssertionInspectorDetail | EpisodeInspectorDetail | EvidenceInspectorDetail;

const attributeLabels: Record<string, string> = {
  display_name: "显示名",
  aliases: "别名",
  species: "物种",
  species_id: "物种标识",
  species_name: "物种",
  place_kind: "地点类型",
  object_kind: "物体类型",
  kind: "类型",
  is_self: "当前精灵",
  is_owner: "主人标记",
  age_years_at_genesis: "创世年龄",
  life_stage: "生命阶段",
  vocation_id: "职业线索",
  competency_ids: "能力线索",
  familiarity: "熟悉度",
  trust_score: "信任度",
  visibility: "可见性",
  parent_id: "上级地点",
  shared_facts: "共同事实",
  unknown_facts: "未知边界",
  relation_role: "关系角色",
};

const attributeOrder = [
  "is_self", "species_name", "species", "species_id", "kind", "place_kind", "object_kind",
  "display_name", "life_stage", "age_years_at_genesis", "relation_role", "vocation_id", "competency_ids",
  "familiarity", "trust_score", "visibility", "parent_id", "shared_facts", "unknown_facts",
];

// These keys are identifiers, compiler metadata or adapter bookkeeping. They remain
// available in the technical disclosure but never become semantic attributes.
const technicalPropertyKeys = new Set([
  "elfie_id", "person_id", "relationship_id", "genesis_submission_id", "manifest_id", "schema_version",
  "semantic_revision", "projection_revision", "recall_eligible", "source_id", "source_ids", "output_ids",
  "compiler", "compiler_version", "content_sha256", "hash", "sha256", "adapter", "adapter_metadata",
  "lifecycle", "status", "importance", "confidence", "freshness", "half_life_days", "retention_profile",
  "entity_type", "relationship_label", "relationship_key", "relation_kind", "core_key",
]);

export function inspectorTypeLabel(kind: string | undefined): string {
  return kind ?? "未知类型";
}

export function inspectorAttributeLabel(key: string): string {
  return attributeLabels[key] ?? key.replace(/_/g, " ");
}

const episodeEventKindLabels: Record<string, string> = {
  conversation: "对话交流",
  activity: "活动",
  outing: "出行",
  learning: "学习成长",
  life_event: "生活事件",
  observation: "观察",
  reflection: "反思",
  unclassified: "待分类",
};

const episodeMaintenanceLabels: Record<string, string> = {
  pending: "待整理",
  processing: "整理中",
  completed: "已整理",
  failed: "整理失败",
  skipped: "已跳过",
  unknown: "进度未记录",
};
const episodePrecisionLabels: Record<string, string> = { exact: "精确时间", range: "时间范围", unknown: "具体时间未知" };
const episodeAttributionLabels: Record<string, string> = { observed: "亲历或观察", told: "他人告知", inferred: "推断", felt: "主观感受" };
const episodeDetailLevelLabels: Record<string, string> = { full: "完整", compressed: "压缩", digest: "摘要", incomplete: "不完整" };
const episodeSourceKindLabels: Record<string, string> = { conversation: "对话", genesis_source: "Genesis 知识资料", personal_memory: "个人经历资料", adoption_decision: "领养来源" };

export function episodeCardDisplayTitle(episode: InspectorRecord): string {
  const summary = String(episode.summary_text ?? "").trim();
  if (summary) return summary;
  const content = String(episode.content_text ?? "").trim();
  if (!content) return "";
  const characters = Array.from(content);
  return characters.length > 180 ? `${characters.slice(0, 179).join("")}…` : content;
}

export function episodeEventKindLabel(value: unknown): string {
  const kind = String(value ?? "");
  return episodeEventKindLabels[kind] ?? (kind ? "未知类型" : "类型未记录");
}

export function episodeMaintenanceLabel(episode: InspectorRecord): string {
  const maintenance = episode.maintenance;
  const state = maintenance && typeof maintenance === "object" && !Array.isArray(maintenance)
    ? String((maintenance as InspectorRecord).state ?? "unknown")
    : "unknown";
  return episodeMaintenanceLabels[state] ?? "进度未记录";
}

function episodeTimestampLabel(value: unknown): string {
  if (value == null || value === "") return "未记录";
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

function episodeTemporalContextLabel(value: unknown): string {
  const context = String(value ?? "").trim();
  if (!context) return "未记录";
  const labels: Record<string, string> = { before_arrival: "抵达前", on_arrival: "抵达时", arrival: "抵达时" };
  return labels[context] ?? context;
}

function formatValue(value: unknown): string {
  if (value == null || value === "") return "未记录";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) return value.map((item) => formatValue(item)).join("、");
  if (typeof value === "object") {
    const json = JSON.stringify(value);
    return json.length > 240 ? `${json.slice(0, 237)}…` : json;
  }
  return String(value);
}

function score(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function statusOf(record: InspectorRecord): string {
  return String(record.status ?? record.lifecycle ?? "unknown");
}

function headerFor(record: InspectorRecord, semanticType: string, label: string, summary: string): InspectorHeader {
  return {
    semanticType,
    label,
    summary: summary || "没有摘要",
    status: statusOf(record),
    importance: score(record.importance),
    confidence: score(record.confidence),
  };
}

function field(key: string, value: unknown, source: InspectorField["source"], label = inspectorAttributeLabel(key)): InspectorField {
  return { key, label, value: formatValue(value), source };
}

function recordId(record: InspectorRecord, key: string): string {
  return String(record[key] ?? "");
}

function excerptOf(record: InspectorRecord): string {
  return String(record.excerpt ?? record.summary_text ?? record.content_text ?? "");
}

function sourceFor(record: InspectorRecord, kind: string, fallback = "来源未记录"): InspectorSource {
  const id = recordId(record, "evidence_id") || recordId(record, "episode_id") || recordId(record, "source_id") || fallback;
  return { id, label: kind, excerpt: excerptOf(record) || fallback, kind };
}

function sortFields(fields: InspectorField[]): InspectorField[] {
  return [...fields].sort((left, right) => {
    const leftIndex = attributeOrder.indexOf(left.key);
    const rightIndex = attributeOrder.indexOf(right.key);
    if (leftIndex >= 0 && rightIndex >= 0) return leftIndex - rightIndex;
    if (leftIndex >= 0) return -1;
    if (rightIndex >= 0) return 1;
    return left.label.localeCompare(right.label, "zh-CN");
  });
}

export function projectVisibleNodeProperties(node: InspectorNode): { fields: InspectorField[]; technical: InspectorField[] } {
  const properties = node.properties ?? {};
  const fields: InspectorField[] = [];
  const technical: InspectorField[] = [];
  Object.entries(properties).forEach(([key, value]) => {
    const registeredAttribute = Object.prototype.hasOwnProperty.call(attributeLabels, key);
    const target = !registeredAttribute || technicalPropertyKeys.has(key) ? technical : fields;
    target.push(field(key, value, target === technical ? "technical" : "property"));
  });
  return { fields: sortFields(fields), technical: sortFields(technical) };
}

export type RelationProjectionInput = {
  assertions: InspectorRecord[];
  episodes?: InspectorRecord[];
  evidenceById?: ReadonlyMap<string, InspectorRecord>;
  nodeById: ReadonlyMap<string, InspectorNode>;
  relationKind: (record: InspectorRecord) => string;
  relationLabel: (kind: string) => string;
  relationSentence: (source: string, target: string, kind: string, sourceKind?: string, targetKind?: string) => string;
  nodeTypeLabel?: (nodeType: string | undefined) => string;
  selectedNodeId?: string;
};

function stringValues(value: unknown): string[] {
  if (typeof value === "string") return value.trim() ? [value.trim()] : [];
  if (Array.isArray(value)) return value.flatMap(stringValues);
  return [];
}

function metadataOf(record: InspectorRecord): InspectorRecord {
  const value = record.metadata ?? record.metadata_json;
  if (value && typeof value === "object" && !Array.isArray(value)) return value as InspectorRecord;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value) as unknown;
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as InspectorRecord : {};
    } catch {
      return {};
    }
  }
  return {};
}

type NodeEpisodeMatch = { episode: InspectorRecord; metadataMatch: boolean; lexicalMatches: number };

function nodeEpisodeMatch(node: InspectorNode, episode: InspectorRecord): NodeEpisodeMatch | null {
  const properties = node.properties ?? {};
  const metadata = metadataOf(episode);
  const metadataTerms = [
    ...stringValues(metadata.place_ids),
    ...stringValues(metadata.person_ids),
    ...stringValues(metadata.node_ids),
    ...stringValues(metadata.entity_ids),
  ].map((value) => value.toLocaleLowerCase());
  const identityTerms = [
    node.label,
    ...stringValues(properties.display_name),
    ...stringValues(properties.aliases),
    ...stringValues(properties.place_id),
    ...stringValues(properties.person_id),
    ...stringValues(properties.source_ref),
  ]
    .map((value) => value.trim().toLocaleLowerCase())
    .filter((value) => value.length >= 2);
  if (!identityTerms.length) return null;
  const metadataMatch = identityTerms.some((term) => metadataTerms.some((metadataTerm) => (
    metadataTerm === term || metadataTerm.startsWith(`${term}_`) || metadataTerm.startsWith(`${term}:`)
  )));
  const text = `${String(episode.content_text ?? "")} ${String(episode.summary_text ?? "")}`.toLocaleLowerCase();
  const lexicalMatches = identityTerms.filter((term) => text.includes(term)).length;
  if (!metadataMatch && lexicalMatches === 0) return null;
  return { episode, metadataMatch, lexicalMatches };
}

/**
 * Project the reverse Episode lookup for a Node detail.
 *
 * Metadata matches are explicit participant/place references. Text matches
 * are deliberately labelled as source text hits by the UI; they do not become
 * a hidden Assertion or claim a structured relation that Memory did not store.
 */
export function projectNodeSources(
  node: InspectorNode,
  episodes: readonly InspectorRecord[] = [],
): InspectorSource[] {
  const matches = episodes
    .map((episode) => nodeEpisodeMatch(node, episode))
    .filter((match): match is NodeEpisodeMatch => match !== null)
    .sort((left, right) => (
      Number(right.metadataMatch) - Number(left.metadataMatch)
      || right.lexicalMatches - left.lexicalMatches
      || (score(right.episode.importance) ?? 0) - (score(left.episode.importance) ?? 0)
      || String(right.episode.occurred_from ?? right.episode.occurred_at ?? "").localeCompare(String(left.episode.occurred_from ?? left.episode.occurred_at ?? ""))
    ));
  const seen = new Set<string>();
  return matches.flatMap(({ episode, metadataMatch }) => {
    const id = recordId(episode, "episode_id");
    if (!id || seen.has(id)) return [];
    seen.add(id);
    const kind = String(episode.event_kind ?? "Episode");
    return [{
      id,
      label: metadataMatch ? `Episode · ${kind} · 明确提及` : `Episode · ${kind} · 原文命中`,
      excerpt: excerptOf(episode) || "没有来源内容",
      kind: "episode",
    }];
  }).slice(0, 24);
}

export function projectRelationConnections(input: RelationProjectionInput): InspectorConnection[] {
  const selectedId = input.selectedNodeId;
  return input.assertions
    .filter((record) => !selectedId || String(record.subject_id ?? "") === selectedId || String(record.object_node_id ?? "") === selectedId)
    .map((record) => {
      const subjectId = String(record.subject_id ?? "");
      const objectId = String(record.object_node_id ?? "");
      const subject = input.nodeById.get(subjectId);
      const object = input.nodeById.get(objectId);
      const kind = input.relationKind(record);
      const source = subject?.label ?? subjectId;
      const target = object?.label ?? (objectId || String(record.object_literal ?? "字面值"));
      return {
        id: String(record.assertion_id ?? `${subjectId}:${kind}:${objectId}`),
        label: input.relationLabel(kind),
        detail: input.relationSentence(source, target, kind, subject?.node_type, object?.node_type),
        importance: score(record.importance),
        confidence: score(record.confidence),
        kind: "relation" as const,
      };
    })
    .sort((left, right) => (right.importance ?? 0) - (left.importance ?? 0) || left.label.localeCompare(right.label, "zh-CN"));
}

export function projectNodeDetail(
  node: InspectorNode,
  input: Omit<RelationProjectionInput, "selectedNodeId">,
): NodeInspectorDetail {
  const projected = projectVisibleNodeProperties(node);
  return {
    kind: "node",
    header: headerFor(node, input.nodeTypeLabel?.(node.node_type) ?? inspectorTypeLabel(node.node_type), node.label, node.description ?? ""),
    fields: projected.fields,
    connections: projectRelationConnections({ ...input, selectedNodeId: node.id }),
    sources: projectNodeSources(node, input.episodes),
    technical: [field("id", node.id, "technical", "ID"), ...projected.technical],
  };
}

export function projectAssertionDetail(
  assertion: InspectorRecord,
  input: Omit<RelationProjectionInput, "assertions" | "selectedNodeId">,
): AssertionInspectorDetail {
  const subjectId = String(assertion.subject_id ?? "");
  const objectId = String(assertion.object_node_id ?? "");
  const subject = input.nodeById.get(subjectId);
  const object = input.nodeById.get(objectId);
  const kind = input.relationKind(assertion);
  const source = subject?.label ?? subjectId;
  const target = object?.label ?? (objectId || String(assertion.object_literal ?? "字面值"));
  const sentence = input.relationSentence(source, target, kind, subject?.node_type, object?.node_type);
  const evidenceIds = Array.isArray(assertion.evidence_ids) ? assertion.evidence_ids.map(String) : [];
  return {
    kind: "assertion",
    header: headerFor(assertion, "Assertion 关系", input.relationLabel(kind), `${source} ${assertion.symmetric ? "↔" : "→"} ${target} · ${input.relationLabel(kind)}`),
    sentence,
    fields: [
      field("predicate", input.relationLabel(kind), "assertion", "关系类型"),
      field("direction", assertion.symmetric ? `${source} ↔ ${target}` : `${source} → ${target}`, "assertion", assertion.symmetric ? "关系方向" : "方向"),
      field("validity", assertion.valid_from || assertion.valid_to ? `${formatValue(assertion.valid_from)} → ${formatValue(assertion.valid_to)}` : "未记录", "assertion", "有效时间"),
      field("polarity", assertion.polarity, "assertion", "极性"),
      field("epistemic_status", assertion.epistemic_status, "assertion", "认识状态"),
    ],
    connections: [],
    sources: evidenceIds.map((id) => sourceFor(input.evidenceById?.get(id) ?? { evidence_id: id }, "Evidence", id)),
    technical: [field("assertion_id", assertion.assertion_id, "technical", "ID"), field("qualifiers", assertion.qualifiers, "technical", "原始限定条件")],
  };
}

export function projectEpisodeDetail(
  episode: InspectorRecord,
  input: { assertions: InspectorRecord[]; evidence: InspectorRecord[]; nodeById: ReadonlyMap<string, InspectorNode>; nodeTypeLabel?: (nodeType: string | undefined) => string },
): EpisodeInspectorDetail {
  const episodeId = recordId(episode, "episode_id");
  const evidence = input.evidence.filter((item) => String(item.source_id ?? "") === episodeId);
  const evidenceIds = new Set(evidence.map((item) => String(item.evidence_id)));
  const affectedAssertions = input.assertions.filter((item) => Array.isArray(item.evidence_ids) && item.evidence_ids.some((id) => evidenceIds.has(String(id))));
  const nodeIds = new Set(affectedAssertions.flatMap((item) => [String(item.subject_id ?? ""), String(item.object_node_id ?? "")]).filter(Boolean));
  const metadata = metadataOf(episode);
  for (const key of ["person_ids", "place_ids", "related_ids"]) {
    for (const id of stringValues(metadata[key])) {
      if (input.nodeById.has(id)) nodeIds.add(id);
    }
  }
  const sourceRefs = Array.isArray(episode.source_refs)
    ? episode.source_refs.filter((item): item is InspectorRecord => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
  const body = String(episode.content_text ?? "没有来源内容");
  const summary = String(episode.summary_text ?? "").trim();
  const maintenance = episode.maintenance && typeof episode.maintenance === "object" && !Array.isArray(episode.maintenance)
    ? episode.maintenance as InspectorRecord
    : {};
  const header = headerFor(episode, "经历", summary, "");
  // Episode summary is independent from its content. Keep this slot empty when
  // no summary was generated instead of displaying the body as a substitute.
  header.summary = "";
  header.status = episodeMaintenanceLabel(episode);
  return {
    kind: "episode",
    header,
    fields: [
      field("occurred_from", episodeTimestampLabel(episode.occurred_from), "episode", "发生时间"),
      field("occurred_to", episodeTimestampLabel(episode.occurred_to), "episode", "结束时间"),
      field("occurrence_precision", episodePrecisionLabels[String(episode.occurrence_precision ?? "unknown")] ?? "时间精度未记录", "episode", "时间精度"),
      field("event_kind", episodeEventKindLabel(episode.event_kind), "episode", "经历类型"),
      field("maintenance_state", episodeMaintenanceLabel(episode), "episode", "整理进度"),
      field("maintenance_attempts", maintenance.attempts, "episode", "整理尝试次数"),
      field("maintenance_updated_at", maintenance.updated_at, "episode", "整理进度更新时间"),
      field("attribution", episodeAttributionLabels[String(episode.attribution ?? "")] ?? "来源归因未记录", "episode", "来源归因"),
      field("source_refs", sourceRefs.length ? sourceRefs.map((item) => episodeSourceKindLabels[String(item.source_kind ?? "")] ?? "其他来源") : "未记录", "episode", "来源"),
      field("topic", metadata.topic, "episode", "话题"),
      field("scope", metadata.scope, "episode", "范围"),
      field("temporal_label", episodeTemporalContextLabel(episode.temporal_label), "episode", "时间背景"),
      field("life_stage", episode.life_stage, "episode", "生命阶段"),
      field("detail_level", episodeDetailLevelLabels[String(episode.detail_level ?? "")] ?? "内容细致级别未记录", "episode", "内容细致级别"),
      field("emotion", episode.emotion, "episode", "情绪"),
      field("emotion_intensity", episode.emotion_intensity, "episode", "情绪强度"),
    ],
    connections: [
      ...[...nodeIds].map((id) => {
        const node = input.nodeById.get(id);
        const nodeKind = input.nodeTypeLabel?.(node?.node_type) ?? inspectorTypeLabel(node?.node_type);
        return { id, label: `相关${nodeKind}`, detail: node?.label ?? id, importance: null, confidence: node?.confidence ?? null, kind: "attribute" as const };
      }),
      ...affectedAssertions.map((item) => ({ id: String(item.assertion_id), label: "受影响 Assertion", detail: String(item.predicate ?? "关系"), importance: score(item.importance), confidence: score(item.confidence), kind: "relation" as const })),
    ],
    sources: evidence.map((item) => sourceFor(item, "Evidence", String(item.evidence_id))),
    technical: [field("episode_id", episodeId, "technical", "ID"), field("metadata", episode.metadata, "technical", "元数据")],
    content: body,
  };
}

export function projectEvidenceDetail(
  evidence: InspectorRecord,
  assertions: InspectorRecord[],
  episodesById?: ReadonlyMap<string, InspectorRecord>,
): EvidenceInspectorDetail {
  const evidenceId = recordId(evidence, "evidence_id");
  const supported = assertions.filter((item) => Array.isArray(item.evidence_ids) && item.evidence_ids.map(String).includes(evidenceId));
  const sourceId = recordId(evidence, "source_id");
  return {
    kind: "evidence",
    header: headerFor(evidence, "Evidence 证据", evidenceId, `${String(evidence.source_type ?? "来源")} · ${String(evidence.modality ?? "text")}`),
    excerpt: String(evidence.excerpt ?? "没有摘录"),
    fields: [
      field("source_id", sourceId, "evidence", "来源 ID"),
      field("source_type", evidence.source_type, "evidence", "来源类型"),
      field("modality", evidence.modality, "evidence", "模态"),
      field("attribution", evidence.attribution ?? evidence.stance, "evidence", "归因/立场"),
      field("source_reliability_class", evidence.source_reliability_class, "evidence", "可靠性"),
    ],
    connections: [
      ...(sourceId && episodesById?.has(sourceId) ? [{ id: sourceId, label: "来源 Episode", detail: String(episodesById.get(sourceId)?.content_text ?? sourceId), importance: null, confidence: null, kind: "episode" as const }] : []),
      ...supported.map((item) => ({ id: String(item.assertion_id), label: "支持 Assertion", detail: String(item.predicate ?? "关系"), importance: score(item.importance), confidence: score(item.confidence), kind: "relation" as const })),
    ],
    sources: [sourceFor(evidence, "Evidence", evidenceId)],
    technical: [field("evidence_id", evidenceId, "technical", "ID"), field("viewpoint", evidence.viewpoint, "technical", "视角"), field("media", evidence.media, "technical", "媒体")],
  };
}
