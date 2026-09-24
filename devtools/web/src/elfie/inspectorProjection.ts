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

export const inspectorTypeLabels: Record<string, string> = {
  elfie: "精灵",
  person: "人物",
  group: "群体/家庭",
  place: "地点",
  object: "物体",
  knowledge: "知识",
  event: "事件",
  self_model: "自我模型",
  literal: "字面值",
};

const attributeLabels: Record<string, string> = {
  display_name: "显示名",
  aliases: "别名",
  species: "物种",
  species_id: "物种标识",
  species_name: "物种",
  place_kind: "地点类型",
  object_kind: "物体类型",
  knowledge_kind: "知识类型",
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
  "is_self", "species_name", "species", "species_id", "kind", "place_kind", "object_kind", "knowledge_kind",
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
  return inspectorTypeLabels[kind ?? ""] ?? kind ?? "未知类型";
}

export function inspectorAttributeLabel(key: string): string {
  return attributeLabels[key] ?? key.replace(/_/g, " ");
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
    header: headerFor(node, inspectorTypeLabel(node.node_type), node.label, node.description ?? ""),
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
  input: { assertions: InspectorRecord[]; evidence: InspectorRecord[]; nodeById: ReadonlyMap<string, InspectorNode> },
): EpisodeInspectorDetail {
  const episodeId = recordId(episode, "episode_id");
  const evidence = input.evidence.filter((item) => String(item.source_id ?? "") === episodeId);
  const evidenceIds = new Set(evidence.map((item) => String(item.evidence_id)));
  const affectedAssertions = input.assertions.filter((item) => Array.isArray(item.evidence_ids) && item.evidence_ids.some((id) => evidenceIds.has(String(id))));
  const nodeIds = new Set(affectedAssertions.flatMap((item) => [String(item.subject_id ?? ""), String(item.object_node_id ?? "")]).filter(Boolean));
  return {
    kind: "episode",
    header: headerFor(episode, "Episode", "Episode", String(episode.content_text ?? "没有来源内容")),
    fields: [
      field("event_kind", episode.event_kind, "episode", "类型"),
      field("occurred_from", episode.occurred_from, "episode", "开始时间"),
      field("occurred_to", episode.occurred_to, "episode", "结束时间"),
      field("attribution", episode.attribution, "episode", "归因"),
      field("detail_level", episode.detail_level, "episode", "细节级别"),
    ],
    connections: [
      ...[...nodeIds].map((id) => ({ id, label: "受影响 Node", detail: input.nodeById.get(id)?.label ?? id, importance: null, confidence: null, kind: "episode" as const })),
      ...affectedAssertions.map((item) => ({ id: String(item.assertion_id), label: "受影响 Assertion", detail: String(item.predicate ?? "关系"), importance: score(item.importance), confidence: score(item.confidence), kind: "relation" as const })),
    ],
    sources: evidence.map((item) => sourceFor(item, "Evidence", String(item.evidence_id))),
    technical: [field("episode_id", episodeId, "technical", "ID"), field("metadata", episode.metadata, "technical", "元数据")],
    content: String(episode.content_text ?? "没有来源内容"),
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
