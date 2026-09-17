import { useEffect, useState, type ReactNode } from "react";
import { Button } from "antd";

import type { ElfieSession, ElfieTurn } from "./contracts";
import type { DetailFocus } from "./viewModel";

type PreviewResult = Readonly<{
  readonly turnId: string;
  readonly intentId: string;
  readonly status: "completed" | "unsupported";
  readonly reason: string;
}>;
type Props = Readonly<{
  readonly session: ElfieSession | null;
  readonly selectedTurn: ElfieTurn | null;
  readonly open: boolean;
  readonly initialTab: string;
  readonly focus: DetailFocus;
  readonly previewResult: PreviewResult | null;
  readonly onClose: () => void;
  // Test seam: stage and known nested detail ids opened on mount so
  // static-render tests can assert nested views without DOM interaction.
  // Interactive clicks keep the single-open stage accordion behavior.
  readonly defaultOpenDetails?: readonly string[] | undefined;
}>;

type JsonRecord = Record<string, unknown>;
type TraceNode = JsonRecord;
type TraceStatus = string;

const statusLabels: Readonly<Record<string, string>> = {
  completed: "已完成",
  recorded: "已完成",
  compiled: "已编译",
  parsed: "已解析",
  observed: "已产生观察",
  returned: "已返回",
  accepted: "已接受",
  revision_required: "要求修订",
  fallback: "终止回退",
  safe_noop: "安全无操作",
  committed: "已提交",
  recalled: "已召回",
  received: "已收到",
  loaded: "已加载",
  repair_returned: "修订已返回",
  invalid_output: "输出无效",
  activity_preflight: "Activity 预检",
  pending: "待处理",
  degraded: "已降级",
  deferred: "已延期",
  rejected: "已拒绝",
  unavailable: "未采集",
  missing: "未采集",
  skipped: "已跳过",
  empty: "无输出",
  failed: "失败",
  continued: "继续",
  stopped: "停止",
};

// Stage descriptions ride on data-tip attributes of the trace triggers: detail-modal.css
// renders an instant CSS tooltip anchored just below each trigger (no native title delay,
// no double popup).
const STAGE_DESCRIPTIONS: Readonly<Record<string, string>> = {
  event_admission: "本轮输入：确认输入通道与处理内容",
  context_workspace: "上下文工作区：查看分区内的历史、摘要与待处理状态",
  setup: "运行准备：冻结外部状态与记忆版本，确定推理模式与预算",
  reasoning_run: "推理执行：循环“编译→调用→行动→观察→守卫→判定”，产出最终决策",
  turn_decision: "回合决策：把接受的草稿固化为唯一的类型化决策",
  governance_delivery: "治理与交付：治理检查后交付到目标通道，产出回执",
  settlement: "结算：提交状态候选与记忆写回，落持久化证据",
};

const SUB_STEP_DESCRIPTIONS: Readonly<Record<string, string>> = {
  context_build: "上下文编译：按预算重新编译模型上下文，裁剪低相关材料",
  model_call: "模型调用：发送上下文，取回模型响应",
  action: "行动解析：把响应解析为类型化行动",
  observation: "观察记录：把行动结果结构化为下一轮观察",
  guard: "守卫判断：检查剩余预算与时间，决定是否继续",
  judge: "完成判定：判定回复是否合格，接受或要求修订",
};

function record(value: unknown): JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? Object.fromEntries(Object.entries(value))
    : {};
}

function list(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? value : [];
}

function hasContent(value: unknown): boolean {
  if (value === undefined || value === null || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(record(value)).length > 0;
  return true;
}

function pretty(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === undefined) return "未记录";
  const serialized = JSON.stringify(value, null, 2);
  return serialized ?? String(value);
}

function statusOf(value: unknown): TraceStatus {
  return typeof value === "string" && value ? value : "unavailable";
}

function statusLabel(value: unknown): string {
  const status = statusOf(value);
  return statusLabels[status] ?? status;
}

function Status({ value }: Readonly<{ readonly value: unknown }>): React.JSX.Element {
  const status = statusOf(value);
  const glyph = status === "failed" || status === "revision_required" ? "!" : status === "unavailable" ? "?" : status === "skipped" ? "–" : "✓";
  return <span className={`trace-status trace-status-${status}`}><span aria-hidden="true">{glyph}</span>{statusLabel(status)}</span>;
}

function formatDuration(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "未记录";
  return value < 1000 ? `${value < 1 ? value.toFixed(2) : Math.round(value)} ms` : `${(value / 1000).toFixed(2)} s`;
}

// Guard legacy receipts persisted before the lab's clock was anchored away
// from the UNIX epoch; their 1970-era timestamps render as "未记录".
const epochishYearCutoff = 1971;

function isEpochishTimestamp(value: unknown): boolean {
  if (typeof value !== "string") return false;
  const year = /^(\d{4})-/.exec(value)?.[1];
  return year !== undefined && Number.parseInt(year, 10) <= epochishYearCutoff;
}

function occurredAtValue(value: unknown): unknown {
  return isEpochishTimestamp(value) ? "未记录" : value;
}

function fieldLabel(key: string): string {
  const labels: Readonly<Record<string, string>> = {
    source_domain: "来源",
    message: "消息",
    modalities: "模态",
    turn_id: "Turn",
    frame_id: "Frame",
    interaction_scope: "交互范围",
    response_scope: "响应范围",
    status: "状态",
    model_mode: "模型模式",
    error_code: "错误码",
    timeout_reason: "超时原因",
    stale_reason: "过期原因",
    user_prompt: "模型用户消息",
    system_prompt: "模型系统消息",
    context_revision: "上下文版本",
    capability_revision: "能力版本",
    deadline: "截止时间",
    captured_at: "读取时点",
    reasoning_mode: "推理模式",
    response_mode: "响应模式",
    processing_mode: "处理方式",
    response_schema: "响应结构",
    response_schema_definition: "响应结构定义",
    temperature: "采样温度",
    max_tokens: "最大输出 Token",
    timeout_seconds: "单次请求超时（秒）",
    allowed_tools: "允许工具",
    tool_definition_count: "工具定义",
    skill_count: "技能数量",
    tool_definitions: "工具定义详情",
    available_skills: "可用技能",
    provider: "Provider",
    model: "模型",
    selected_mode: "Host 解析模式",
    verdict: "判定",
    action_type: "行动类型",
    revision_requested: "是否要求修订",
    external_claim_replaced: "是否替换外部声明",
    current_nest_sanitized: "是否校正巢状态",
    memory_use_count: "记忆使用次数",
    prompt_sections: "上下文段落",
    conversation: "对话上下文",
    current_observations: "当前观察",
    current_run_observations: "本轮观察",
    plan_id: "计划",
    speech_texts: "语音文本",
    message_texts: "消息文本",
    speech_intents: "语音意图",
    message_intents: "消息意图",
    motion_intents: "动作意图",
    expression_intents: "表情意图",
    action_intents: "动作意图",
    activity_intents: "Activity 意图",
    noop_intents: "No-op 意图",
    source_record: "输入来源",
    recorded_turn_id: "记录的 Turn",
    receipt_count: "回执数量",
    warnings: "警告",
    failure_reason: "失败原因",
    fallback_reason: "降级原因",
    run_reason: "失败/回退原因",
    model_calls: "模型调用次数",
    tool_calls: "工具调用次数",
    skill_calls: "技能调用次数",
    text: "文本",
    action: "动作",
    content: "内容",
    claim: "事实",
    relation: "关系",
    evidence: "证据",
    confidence: "置信度",
    detail: "详情",
    model_key: "模型标识",
    supports_json_schema: "JSON Schema",
    supports_tool_calling: "工具调用",
    supports_json_mode: "JSON 模式",
    supports_plain_text: "普通文本",
    max_output_tokens: "最大输出 Token",
    revision: "版本",
    freshness: "新鲜度",
    location: "位置",
    location_source: "位置来源",
    position: "坐标",
    heading_degrees: "朝向",
    body_id: "身体",
    primary_emotion: "主情绪",
    secondary_emotion: "次情绪",
    emotions: "情绪值",
    active_emotions: "活跃情绪",
    trends: "情绪趋势",
    energy: "能量",
    normal_budget_available: "普通认知配额",
    emergency_reserve_available: "紧急储备",
    reserved_cognitive_budget: "已预留认知配额",
    energy_revision: "能量版本",
    fatigue: "疲劳",
    is_sleeping: "睡眠中",
    sleeping: "睡眠中",
    cognitive_mode: "认知模式",
    emotion_revision: "情绪版本",
    recovery_status: "恢复状态",
    recovery_pressure: "恢复压力",
    cooldown_until: "冷却截止",
    satisfaction_until: "满足截止",
    last_trigger_id: "最近触发",
    constitution_version: "人格规则版本",
    context_captured_at: "冻结时点",
    requires_model: "需要模型",
    structured_owner_reply: "结构化回复",
    fast_owner_reply: "快速回复",
    long_reasoning_allowed: "允许深入推理",
    identity_core: "身份核心",
    interaction_tendencies: "互动倾向",
    coping_tendencies: "应对倾向",
    expression_tendencies: "表达倾向",
    values: "价值规范",
    speech_markers: "表达标记",
    reason: "原因",
    skip_reason: "跳过原因",
    evidence_basis: "判定依据",
    query: "检索查询",
    occurred_at: "发生时间",
    error: "错误",
    depth: "推理深度",
    depth_basis: "深度依据",
    max_steps: "最大步数",
    max_model_calls: "最大模型调用",
    max_planned_model_calls: "计划模型调用上限",
    max_tool_calls: "最大工具调用",
    deadline_seconds: "预算截止（秒）",
    hard_deadline_seconds: "硬截止（秒）",
    absolute_deadline: "绝对截止",
    max_context_tokens: "上下文 Token 预算",
    message_count: "追加消息数",
    retained_message_count: "保留消息数",
    topic_message_count: "活动状态消息数",
    active_topic_message_count: "活跃话题消息数",
    summary_count: "压缩摘要数",
    channel_id: "频道",
    conversation_id: "会话",
    summary_id: "摘要 ID",
    unresolved_count: "未回填来源数",
    admitted: "已准入",
    trigger_reason: "触发原因",
    cutoff_seq: "截断序号",
    event_count: "事件数",
    max_event_salience: "最高显著性",
    saliences: "事件显著性",
    routed: "路由结果",
    interaction_scope_kind: "交互范围类型",
    response_domain: "响应域",
    response_channel_id: "响应频道",
    response_conversation_id: "响应会话",
    memory_eligible: "可入记忆",
    prompt_tokens: "输入 Token",
    completion_tokens: "输出 Token",
    provider_latency_ms: "Provider 延迟",
    reserved: "预留 Token",
    memory_budget: "记忆预算",
    content_budget: "内容预算",
    event_budget: "事件预算",
    observation_budget: "观察预算",
    truncated: "发生裁剪",
    memory_truncated: "记忆被裁剪",
    event_truncated_count: "裁剪事件数",
    history_truncated_count: "裁剪历史行数",
    run_observation_truncated_count: "裁剪观察数",
    affected_sections: "受影响内容",
    memory_query: "记忆查询",
    memory_status: "记忆状态",
    returned_count: "返回记忆点",
    candidates: "编码候选",
    commits: "编码提交",
    reinforcements: "记忆强化",
    candidate_id: "候选 ID",
    base_revision: "基线版本",
    source_event_ids: "来源事件",
    unresolved_items: "未解决事项",
    intensity: "强度",
    content_chars: "内容字符数",
    episode_id: "Episode",
    revision_before: "变更前版本",
    revision_after: "变更后版本",
    target_kind: "目标类型",
    target_id: "目标 ID",
    outcome_kind: "结果类型",
    event_id: "事件 ID",
    stage: "阶段",
    dimensions: "情绪维度",
    changed_dimensions: "变化维度",
    name: "名称",
    before: "变更前",
    after: "变更后",
    consumed: "消耗",
    charged: "实扣",
    released: "已释放",
    energy_state: "能量状态",
    state: "状态",
    participants: "参与者",
    started_at: "开始时间",
    last_activity_at: "最近活动",
    pending_close: "待关闭",
    thread_count: "上下文分区数",
    pending_reply_count: "待结算回复数",
    pending_memory_count: "待写入 Memory 数",
    prepared_at: "准备时间",
    occurred_from: "起始时间",
    occurred_to: "结束时间",
    event_kind: "事件类型",
    content_text: "完整内容",
    summary_text: "精简摘要",
    stimulus: "触发输入",
    sensory: "感知记录",
    metadata: "附加信息",
    identity_core_text: "身份核心投影",
    adaptive_self_text: "自适应自我投影",
    emotion: "情绪",
    kind: "类型",
    external_domain: "外部域",
    available_cognitive_budget: "可用认知配额",
    cognitive_consolidation: "认知整理",
    motivation: "动机",
    orientation: "定位",
    affordances: "可用交互",
    body_generation: "身体世代",
    body_snapshot: "身体快照",
    journal: "日志",
  };
  return labels[key] ?? key;
}

const modalityLabels: Readonly<Record<string, string>> = {
  text: "文字",
  audio: "音频",
  image: "图像",
  attachment: "附件",
  hearing: "听觉",
  vision: "视觉",
  environment: "环境",
  touch: "触碰",
};

const sourceDomainLabels: Readonly<Record<string, string>> = {
  communication: "消息",
  embodied: "现场",
  activity: "Activity",
};

function modalitiesText(value: unknown): unknown {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) return value;
  return value.map((item) => modalityLabels[item] ?? item).join("、");
}

function isPrimitive(value: unknown): boolean {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

function primitiveJoin(value: unknown): string | null {
  if (!Array.isArray(value) || value.length === 0 || !value.every(isPrimitive)) return null;
  return value.map((item) => String(item)).join("、");
}

function FieldValue({ value }: Readonly<{ readonly value: unknown }>): React.JSX.Element {
  if (!hasContent(value)) return <span className="trace-muted">未记录</span>;
  if (isPrimitive(value)) {
    return <span className="trace-value-text">{String(value)}</span>;
  }
  const joined = primitiveJoin(value);
  if (joined !== null) return <span className="trace-value-text">{joined}</span>;
  return <pre className="trace-code trace-code-inline">{pretty(value)}</pre>;
}

// These values are retained in every raw record for correlation and replay,
// but they are not useful in the default human-facing trace.  Keeping the
// filter here also prevents the same opaque metadata from reappearing in
// nested evidence tables while the raw-record toggle remains lossless.
const INTERNAL_FIELD_KEYS: ReadonlySet<string> = new Set([
  "id",
  "turn_id",
  "frame_id",
  "event_id",
  "plan_id",
  "intent_id",
  "call_id",
  "trace_id",
  "channel_id",
  "conversation_id",
  "actor_id",
  "source_ids",
  "source_event_ids",
  "input_event_ids",
  "cause_event_ids",
  "reply_event_id",
  "summary_id",
  "candidate_id",
  "episode_id",
  "target_id",
  "scope_id",
  "revision",
  "context_revision",
  "capability_revision",
  "memory_recall_revision",
  "base_revision",
  "revision_before",
  "revision_after",
  "owner_revision",
  "energy_revision",
  "emotion_revision",
  "constitution_version",
  "recorded_turn_id",
  "captured_at",
  "created_at",
  "prepared_at",
  "started_at",
  "last_activity_at",
  "occurred_at",
  "occurred_from",
  "occurred_to",
  "deadline",
  "absolute_deadline",
]);

function Fields({ values, omit = [] }: Readonly<{ readonly values: JsonRecord; readonly omit?: readonly string[] }>): React.JSX.Element {
  const excluded = new Set(omit);
  const entries = Object.entries(values)
    .filter(([key, value]) => !excluded.has(key) && !INTERNAL_FIELD_KEYS.has(key) && hasContent(value))
    .map(([key, value]) => [key, key === "modalities" ? modalitiesText(value) : value] as const);
  if (!entries.length) return <p className="trace-muted">未采集</p>;
  return <dl className="trace-fields">{entries.map(([key, value]) => <div className="trace-field" key={key}><dt>{fieldLabel(key)}</dt><dd><FieldValue value={value} /></dd></div>)}</dl>;
}

function BlockList({ items, omit = [] }: Readonly<{ readonly items: readonly unknown[]; readonly omit?: readonly string[] }>): React.JSX.Element | null {
  if (!items.length) return null;
  return <div className="trace-memory-list">{items.map((value, index) => {
    const point = record(value);
    return <article className="trace-memory-point" key={`${String(point.summary_id ?? point.candidate_id ?? point.event_id ?? point.target_id ?? "item")}-${index}`}><Fields values={point} omit={omit} /></article>;
  })}</div>;
}

function Evidence({ title, value, emptyLabel = "未采集" }: Readonly<{ readonly title: string; readonly value: unknown; readonly emptyLabel?: string }>): React.JSX.Element {
  const objectValue = typeof value === "object" && value !== null && !Array.isArray(value) ? record(value) : null;
  const textList = Array.isArray(value) && value.length > 0 && value.every((item) => typeof item === "string");
  return <section className="trace-evidence"><h4>{title}</h4>{hasContent(value) ? objectValue !== null ? <Fields values={objectValue} /> : textList ? <div className="trace-text-list">{value.map((item, index) => <p key={`${String(item)}-${index}`}>{item}</p>)}</div> : <pre className="trace-code">{pretty(value)}</pre> : <p className="trace-muted">{emptyLabel}</p>}</section>;
}

const compactIdLength = 14;
const noisyDiffKeys: ReadonlySet<string> = new Set(["captured_at", "unknown_fields"]);

function compactId(item: string): string {
  return item.length > compactIdLength ? `${item.slice(0, compactIdLength)}…` : item;
}

function compactStringArray(value: unknown): string | null {
  if (!Array.isArray(value) || value.length <= 3 || !value.every((item) => typeof item === "string")) return null;
  return `${value.slice(0, 2).map(compactId).join("、")}… (${value.length} 项)`;
}

function readableDiffValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "未记录";
  if (isPrimitive(value)) return String(value);
  const compacted = compactStringArray(value);
  if (compacted !== null) return compacted;
  return JSON.stringify(value) ?? String(value);
}

function diffLeafText(value: unknown): string {
  const source = record(value);
  return `${readableDiffValue(source.before)} → ${readableDiffValue(source.after)}`;
}

function readableStateDiff(value: unknown, path = ""): JsonRecord {
  const source = record(value);
  if (source.before !== undefined || source.after !== undefined) {
    return { [path || "状态"]: diffLeafText(source) };
  }
  const rows: JsonRecord = {};
  for (const [key, child] of Object.entries(source)) {
    if (noisyDiffKeys.has(key)) continue;
    Object.assign(rows, readableStateDiff(child, path ? `${path} ${fieldLabel(key)}` : fieldLabel(key)));
  }
  return rows;
}

function MemoryEvidence({ points, fallback }: Readonly<{ readonly points: readonly unknown[]; readonly fallback: unknown }>): React.JSX.Element {
  if (!points.length) return <Evidence title="记忆引用（仅 ID）" value={fallback} />;
  return <section className="trace-evidence"><h4>记忆引用（仅 ID）</h4><div className="trace-memory-list">{points.map((value, index) => {
    const point = record(value);
    return <article className="trace-memory-point" key={`${String(point.kind ?? "point")}-${index}`}>
      {hasContent(point.claim) ? <p><strong>事实</strong>{String(point.claim)}</p> : null}
      {hasContent(point.relation) ? <p><strong>关系</strong>{String(point.relation)}</p> : null}
      {hasContent(point.evidence) ? <p><strong>证据</strong>{String(point.evidence)}</p> : null}
      <Fields values={{ status: point.status, confidence: point.confidence }} />
    </article>;
  })}</div></section>;
}

function SkipDetails({
  node,
  fallbackReason,
  fallbackEvidence,
}: Readonly<{
  readonly node: TraceNode;
  readonly fallbackReason?: string;
  readonly fallbackEvidence?: string;
}>): React.JSX.Element {
  const output = record(node.output);
  const reason = [node.skip_reason, node.reason, output.skip_reason, output.reason, fallbackReason].find(hasContent);
  const evidence = [node.evidence_basis, output.evidence_basis, fallbackEvidence].find(hasContent);
  return <Fields values={{ skip_reason: reason, evidence_basis: evidence }} />;
}

function IntentEvidence({ groups }: Readonly<{ readonly groups: Readonly<Record<string, readonly unknown[]>> }>): React.JSX.Element | null {
  const entries = Object.entries(groups).filter(([, values]) => values.length > 0);
  if (!entries.length) return null;
  return <section className="trace-evidence"><h4>意图</h4><div className="trace-intent-list">{entries.flatMap(([title, values]) => values.map((value, index) => {
    const intent = record(value);
    const text = intent.content ?? intent.text ?? intent.message ?? intent.action ?? intent.motion ?? intent.expression;
    return <article className="trace-intent" key={`${title}-${index}`}><header><strong>{title}</strong><Status value={intent.status ?? "completed"} /></header>{hasContent(text) ? <p>{String(text)}</p> : <p className="trace-muted">未提供可读内容</p>}</article>;
  }))}</div></section>;
}

function ReceiptEvidence({ receipts }: Readonly<{ readonly receipts: readonly unknown[] }>): React.JSX.Element | null {
  if (!receipts.length) return null;
  return <section className="trace-evidence"><h4>执行回执</h4><div className="trace-receipt-list">{receipts.map((value, index) => {
    const receipt = record(value);
    return <article className="trace-receipt" key={`${String(receipt.status ?? "receipt")}-${index}`}><header><strong>{String(receipt.executor ?? "执行器")}</strong><Status value={receipt.status} /></header><Fields values={{ occurred_at: occurredAtValue(receipt.occurred_at), error: receipt.error }} /></article>;
  })}</div></section>;
}

function TraceDisclosure({
  children,
  id,
  number,
  title,
  meta,
  open,
  onToggle,
  status,
  raw,
  tooltip,
  showStatus = true,
  showRaw = true,
}: Readonly<{
  readonly children: ReactNode;
  readonly id: string;
  readonly number?: string;
  readonly title: string;
  readonly meta?: string | undefined;
  readonly open: boolean;
  readonly onToggle: (id: string) => void;
  readonly status: unknown;
  readonly raw?: unknown;
  readonly tooltip?: string | undefined;
  readonly showStatus?: boolean;
  readonly showRaw?: boolean;
}>): React.JSX.Element {
  const [rawMode, setRawMode] = useState(false);
  const hasRaw = showRaw && hasContent(raw);
  const visibleMeta = showStatus && statusOf(status) !== "skipped" ? meta : undefined;
  return <section className={`trace-disclosure${open ? " is-open" : ""}`}>
    <div className="trace-disclosure-header">
      <button aria-expanded={open} className="trace-disclosure-trigger" data-tip={tooltip} onClick={() => onToggle(id)} type="button">
        <span aria-hidden="true" className="trace-disclosure-chevron">{open ? "⌄" : "›"}</span>
        {number ? <span className="trace-disclosure-number">{number}</span> : null}
        <span className="trace-disclosure-title"><strong>{title}</strong>{visibleMeta ? <small>{visibleMeta}</small> : null}</span>
        {showStatus ? <Status value={status} /> : null}
      </button>
      {hasRaw ? <button aria-pressed={rawMode} className="trace-disclosure-mode" onClick={(event) => { event.stopPropagation(); if (!open) onToggle(id); setRawMode((current) => !current); }} type="button">{rawMode ? "摘要" : "原始记录"}</button> : null}
    </div>
    {open ? <div className="trace-disclosure-content">{rawMode ? <pre className="trace-code trace-node-raw-view">{pretty(raw)}</pre> : children}</div> : null}
  </section>;
}

function TraceIO({ node, omitOutput = [] }: Readonly<{ readonly node: TraceNode; readonly omitOutput?: readonly string[] }>): React.JSX.Element {
  const omitted = new Set(omitOutput);
  const output = Object.fromEntries(Object.entries(record(node.output)).filter(([key]) => !omitted.has(key)));
  return <>
    <Evidence title="输入" value={node.input} />
    <Evidence title="输出" value={output} />
  </>;
}

function ConversationList({ rows }: Readonly<{ readonly rows: readonly unknown[] }>): React.JSX.Element {
  return <dl aria-label="历史交互" className="trace-fields">{rows.map((value, index) => {
    if (typeof value === "string") {
      return <div className="trace-field" key={`line-${index}`}><dt>记录</dt><dd><span className="trace-value-text">{value}</span></dd></div>;
    }
    const row = record(value);
    const speaker = conversationSpeaker(row);
    const content = [row.content, row.text, row.message].find(hasContent);
    const at = occurredAtValue(row.occurred_at);
    return <div className="trace-field" key={`${speaker}-${index}`}><dt>{speaker}</dt><dd>{hasContent(content) ? <span className="trace-value-text">{String(content)}</span> : <span className="trace-muted">未记录</span>}{typeof at === "string" && at !== "未记录" ? <span className="trace-muted"> · {at}</span> : null}</dd></div>;
  })}</dl>;
}

const conversationSpeakerLabels: Readonly<Record<string, string>> = {
  owner: "开发者",
  elfie: "elfie",
  developer_tool: "开发者",
  human: "开发者",
  system: "系统",
  activity: "Activity",
  microphone: "麦克风",
  vision: "视觉输入",
  touch: "触觉输入",
  environment: "环境输入",
  body: "身体输入",
  internal: "内部事件",
};

const genericSpeakerNames: ReadonlySet<string> = new Set([
  "主人",
  "其他参与者",
  "人类参与者",
  "Elfie",
  "精灵",
  "小精灵",
  "未命名精灵",
  "调试输入",
  "开发者输入",
]);

function looksLikeOpaqueSpeaker(value: string): boolean {
  return /^(?:turn|frame|event|intent|channel|conversation|elfie)[_:-]/i.test(value)
    || /^\d{6,}$/.test(value);
}

function legacySpeakerKind(value: string): string | undefined {
  const normalized = value.trim().toLowerCase();
  if (normalized === "主人" || /(?:^|[-_:])owner$/.test(normalized)) return "owner";
  if (normalized === "精灵" || normalized === "小精灵" || /^elfie(?:[-_:]|$)/.test(normalized)) return "elfie";
  return undefined;
}

function usableSpeakerName(value: unknown): value is string {
  return typeof value === "string"
    && value.trim().length > 0
    && !looksLikeOpaqueSpeaker(value.trim())
    && !genericSpeakerNames.has(value.trim());
}

function conversationSpeaker(row: JsonRecord): string {
  const named = [row.display_name, row.speaker]
    .find((candidate): candidate is string => usableSpeakerName(candidate));
  if (named) return named.trim();

  const kind = [row.speaker_kind, row.source_kind, row.role]
    .find((candidate): candidate is string => typeof candidate === "string" && candidate.trim().length > 0);
  const normalizedKind = typeof kind === "string" ? kind.trim().toLowerCase() : "";
  const legacyKind = [row.display_name, row.speaker]
    .find((candidate): candidate is string => typeof candidate === "string" && legacySpeakerKind(candidate) !== undefined);
  const resolvedKind = normalizedKind || (legacyKind ? legacySpeakerKind(legacyKind) ?? "" : "");
  if (resolvedKind === "elfie") return conversationSpeakerLabels.elfie || "elfie";
  if (resolvedKind === "owner" || resolvedKind === "human") return conversationSpeakerLabels.owner || "开发者";
  if (resolvedKind && conversationSpeakerLabels[resolvedKind]) return conversationSpeakerLabels[resolvedKind];
  // The Lab conversation projection has only the developer and the current
  // Elfie. Older rows can lose their source kind, so keep them attached to
  // the current Elfie instead of exposing an abstract participant label.
  return "elfie";
}

function admissionValue(input: JsonRecord, modality: string): unknown {
  const projectedValues = record(input.modality_values);
  if (hasContent(projectedValues[modality])) return projectedValues[modality];

  const message = typeof input.message === "string" ? input.message.trim() : "";
  if ((modality === "text" || modality === "hearing") && message) return message;

  if (modality === "attachment") {
    const attachments = list(input.message_attachments).map(record);
    const filenames = attachments
      .map((item) => item.filename)
      .filter((value): value is string => typeof value === "string" && value !== "");
    if (filenames.length) return filenames.join("、");
    if (attachments.length) return `${attachments.length} 个附件`;
  }

  if (modality === "vision" && hasContent(input.vision_media)) return "已提供视觉输入";
  if (modality === "environment" && hasContent(input.temperature)) return `温度 ${String(input.temperature)}°C`;
  if (modality === "touch" && (hasContent(input.impact_force) || hasContent(input.gentle_stroke))) return "已提供触觉输入";
  return undefined;
}

function admissionModalities(input: JsonRecord, sourceDomain: string): readonly string[] {
  const names = list(input.modalities).filter((item): item is string => typeof item === "string");
  const projectedNames = Object.keys(record(input.modality_values));
  const inferred = names.length ? names : projectedNames;
  if (inferred.length) return Array.from(new Set(inferred));

  const message = typeof input.message === "string" ? input.message.trim() : "";
  if (message) return [sourceDomain === "embodied" ? "hearing" : "text"];
  return [];
}

function AdmissionNode({ node }: Readonly<{ readonly node: TraceNode }>): React.JSX.Element {
  const input = record(node.input);
  const sourceDomain = typeof input.source_domain === "string" ? input.source_domain : "";
  const sourceLabel = sourceDomainLabels[sourceDomain] ?? sourceDomain;
  const rows = admissionModalities(input, sourceDomain)
    .map((modality) => ({
      modality,
      label: modalityLabels[modality] ?? modality,
      value: admissionValue(input, modality),
    }))
    .filter(({ value }) => hasContent(value));
  return <dl aria-label="本轮输入" className="trace-fields">
    <div className="trace-field"><dt>输入通道</dt><dd><FieldValue value={sourceLabel || undefined} /></dd></div>
    {rows.map(({ modality, label, value }) => <div className="trace-field" key={modality}><dt>{label}</dt><dd><FieldValue value={value} /></dd></div>)}
  </dl>;
}

function workspaceRecords(value: unknown): readonly JsonRecord[] {
  return list(value).map(record);
}

function workspaceCurrentThread(
  threads: readonly JsonRecord[],
  appended: JsonRecord,
): JsonRecord | null {
  const match = threads.find((thread) => (
    hasContent(appended.channel_id)
    && hasContent(appended.conversation_id)
    && String(thread.channel_id) === String(appended.channel_id)
    && String(thread.conversation_id) === String(appended.conversation_id)
  ));
  return match ?? null;
}

function workspacePartitionRows(
  threads: readonly JsonRecord[],
  appended: JsonRecord,
): readonly JsonRecord[] {
  return threads.map((thread) => {
    const current = (
      hasContent(appended.channel_id)
      && hasContent(appended.conversation_id)
      && String(thread.channel_id) === String(appended.channel_id)
      && String(thread.conversation_id) === String(appended.conversation_id)
    );
    return {
      channel_id: thread.channel_id,
      conversation_id: thread.conversation_id,
      state: current ? "当前分区" : "已保留",
      retained_message_count: workspaceRecords(thread.messages).length,
      summary_count: workspaceRecords(thread.summaries).length,
    };
  });
}

function workspaceHistoryRows(
  workspace: JsonRecord,
  output: JsonRecord,
  appended: JsonRecord,
): readonly unknown[] {
  const threads = workspaceRecords(workspace.threads);
  const current = workspaceCurrentThread(threads, appended);
  if (current) {
    return workspaceRecords(current.messages).filter((row) => row.is_current !== true);
  }
  return list(output.conversation).filter((value) => record(value).is_current !== true);
}

function workspaceSummaryRows(
  workspace: JsonRecord,
  appended: JsonRecord,
): readonly JsonRecord[] {
  const threads = workspaceRecords(workspace.threads);
  const current = workspaceCurrentThread(threads, appended);
  if (current) return workspaceRecords(current.summaries);
  return workspaceRecords(appended.summaries).filter((summary) => (
    hasContent(summary.content)
    || hasContent(summary.unresolved_items)
    || hasContent(summary.occurred_from)
    || hasContent(summary.occurred_to)
  ));
}

function workspaceStateRows(
  workspace: JsonRecord,
  appended: JsonRecord,
): readonly JsonRecord[] {
  const threads = workspaceRecords(workspace.threads);
  const current = workspaceCurrentThread(threads, appended);
  if (!current) return [];
  const active = record(current.active_state);
  return [
    ...(hasContent(active) ? [active] : []),
    ...workspaceRecords(current.pending_states),
  ];
}

function WorkspaceSummaryList({ items }: Readonly<{ readonly items: readonly unknown[] }>): React.JSX.Element | null {
  if (!items.length) return null;
  return <div className="trace-memory-list">{items.map((value, index) => {
    const summary = record(value);
    return <article className="trace-memory-point" key={`${String(summary.summary_id ?? "summary")}-${index}`}>
      <Fields values={{
        occurred_from: summary.occurred_from,
        occurred_to: summary.occurred_to,
        content: summary.content,
        unresolved_items: summary.unresolved_items,
      }} />
    </article>;
  })}</div>;
}

function WorkspaceStateList({ items }: Readonly<{ readonly items: readonly unknown[] }>): React.JSX.Element | null {
  if (!items.length) return null;
  return <div className="trace-memory-list">{items.map((value, index) => {
    const state = record(value);
    return <article className="trace-memory-point" key={`workspace-state-${index}`}>
      <Fields values={{
        state: state.state,
        participants: state.participants,
        started_at: state.started_at,
        last_activity_at: state.last_activity_at,
        topic_message_count: state.message_count,
        summary_count: state.summary_count,
      }} />
    </article>;
  })}</div>;
}

function WorkspacePendingReplyList({ items }: Readonly<{ readonly items: readonly unknown[] }>): React.JSX.Element | null {
  if (!items.length) return null;
  return <div className="trace-memory-list">{items.map((value, index) => {
    const reply = record(value);
    return <article className="trace-memory-point" key={`pending-reply-${index}`}>
      <Fields values={{
        status: reply.status,
        channel_id: reply.channel_id,
        conversation_id: reply.conversation_id,
        content: reply.content,
        prepared_at: reply.prepared_at,
        memory_eligible: reply.memory_eligible,
      }} />
    </article>;
  })}</div>;
}

function WorkspacePendingMemoryList({ items }: Readonly<{ readonly items: readonly unknown[] }>): React.JSX.Element | null {
  if (!items.length) return null;
  return <div className="trace-memory-list">{items.map((value, index) => {
    const episode = record(value);
    return <article className="trace-memory-point" key={`pending-memory-${index}`}>
      <Fields values={{
        status: episode.status,
        event_kind: episode.event_kind,
        occurred_from: episode.occurred_from,
        occurred_to: episode.occurred_to,
        content_text: episode.content_text,
        summary_text: episode.summary_text,
        stimulus: episode.stimulus,
        sensory: episode.sensory,
        metadata: episode.metadata,
      }} />
    </article>;
  })}</div>;
}

function WorkspaceNode({ node, mountOpenIds }: Readonly<{
  readonly node: TraceNode;
  readonly mountOpenIds?: ReadonlySet<string> | undefined;
}>): React.JSX.Element {
  const baseId = String(node.id ?? "context_workspace");
  const [openChildren, setOpenChildren] = useState<ReadonlySet<string>>(() => new Set(
    Array.from(mountOpenIds ?? []).filter((id) => id.startsWith(`${baseId}-`)),
  ));
  const output = record(node.output);
  const appended = record(node.appended);
  const stageRaw = record(node.raw);
  const workspace = record(output.workspace);
  const threads = workspaceRecords(workspace.threads);
  const partitions = threads.length
    ? workspacePartitionRows(threads, appended)
    : hasContent(appended.channel_id) || hasContent(appended.conversation_id)
      ? [{
        channel_id: appended.channel_id,
        conversation_id: appended.conversation_id,
        state: "当前分区",
        retained_message_count: undefined,
        summary_count: undefined,
      }]
      : [];
  const history = workspaceHistoryRows(workspace, output, appended);
  const summaries = workspaceSummaryRows(workspace, appended);
  const states = workspaceStateRows(workspace, appended);
  const pendingReplies = workspaceRecords(workspace.pending_replies);
  const pendingMemory = workspaceRecords(workspace.pending_memory);
  const checkpoint = record(workspace.checkpoint);
  const toggle = (id: string): void => {
    setOpenChildren((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const details = [
    {
      id: `${baseId}-summaries`,
      title: "压缩摘要",
      raw: summaries,
      content: summaries.length ? <WorkspaceSummaryList items={summaries} /> : null,
      visible: summaries.length > 0,
    },
    {
      id: `${baseId}-state`,
      title: "工作区活动状态",
      raw: states,
      content: states.length ? <WorkspaceStateList items={states} /> : null,
      visible: states.length > 0,
    },
    {
      id: `${baseId}-pending-replies`,
      title: "待结算回复",
      raw: pendingReplies,
      content: pendingReplies.length ? <WorkspacePendingReplyList items={pendingReplies} /> : null,
      visible: pendingReplies.length > 0,
    },
    {
      id: `${baseId}-pending-memory`,
      title: "待写入 Memory",
      raw: pendingMemory,
      content: pendingMemory.length ? <WorkspacePendingMemoryList items={pendingMemory} /> : null,
      visible: pendingMemory.length > 0,
    },
    {
      id: `${baseId}-checkpoint`,
      title: "恢复检查点",
      raw: stageRaw.workspace_checkpoint ?? workspace,
      content: hasContent(checkpoint) ? <Fields values={checkpoint} /> : null,
      visible: hasContent(checkpoint),
    },
  ];
  const visibleDetails = details.filter((detail) => detail.visible);
  return <>
    {partitions.length ? <section className="trace-evidence"><h4>上下文分区</h4><BlockList items={partitions} /></section> : null}
    {history.length ? <section className="trace-evidence"><h4>历史交互</h4><ConversationList rows={history} /></section> : null}
    {visibleDetails.length ? <div className="trace-workspace-sections">{visibleDetails.map((detail) => <TraceDisclosure
      id={detail.id}
      key={detail.id}
      title={detail.title}
      onToggle={toggle}
      open={openChildren.has(detail.id)}
      raw={detail.raw}
      status="recorded"
      showStatus={false}
    >
      {detail.content}
    </TraceDisclosure>)}</div> : null}
  </>;
}

function traceStages(turn: ElfieTurn): JsonRecord {
  return record(record(turn.trace).stages);
}

function projectedNodes(turn: ElfieTurn): readonly TraceNode[] {
  const projected = record(traceStages(turn).observability);
  return list(projected.chain).map(record);
}

function defaultNodeId(focus: DetailFocus, initialTab: string): string {
  if (focus === "input") return "event_admission";
  if (focus === "output") return "governance_delivery";
  if (initialTab === "快照") return "setup";
  if (initialTab === "原始") return "settlement";
  return "reasoning_run";
}

// Stage header meta rule: duration by default; reasoning_run keeps "N 个迭代";
// anomalies add one short reason. Counts/revision summaries are gone by design.
const stageAnomalyLabels: Readonly<Record<string, string>> = {
  failed: "失败",
  degraded: "降级",
  skipped: "跳过",
};

function stageAnomaly(node: TraceNode): string {
  const id = String(node.id ?? "");
  const output = record(node.output);
  if (id === "setup") {
    const baselineStatus = statusOf(record(node.baseline_memory).status);
    if (baselineStatus === "degraded") return "Memory degraded";
  }
  if (id === "event_admission") {
    const admission = String(output.status ?? "");
    if (admission === "deferred") return "admission deferred";
    if (admission === "rejected") return "admission rejected";
  }
  if (id === "governance_delivery") {
    if (record(output.result).success === false) return "交付失败";
    if (statusOf(record(node.delivery).status) === "failed") return "交付失败";
  }
  if (id === "settlement") {
    const warningCount = list(output.warnings).length;
    if (warningCount > 0) return `warning ${warningCount}`;
  }
  const status = statusOf(node.status);
  if (status === "failed" || status === "degraded" || status === "skipped") {
    const reason = [output.failure_reason, output.error_code].find(hasContent);
    return reason ? String(reason) : stageAnomalyLabels[status] ?? status;
  }
  return "";
}

function nodeMeta(node: TraceNode): string {
  const detail = String(node.id ?? "") === "reasoning_run"
    ? `${list(node.iterations).length} 个迭代`
    : "";
  const anomaly = stageAnomaly(node);
  // Setup's previous duration mixed memory/selection work with snapshots
  // taken before the immutable BrainContext existed.  Until the stage gets a
  // dedicated measured boundary, do not present that partial number as the
  // freeze cost.
  const duration = String(node.id ?? "") === "setup"
    ? "未记录"
    : formatDuration(
      node.duration_ms
        ?? record(node.timing).duration_ms
        ?? record(node.output).duration_ms,
    );
  return [detail, anomaly, duration === "未记录" ? "" : `耗时 ${duration}`]
    .filter(Boolean)
    .join(" · ");
}

function ownerOutput(moduleId: string, value: unknown): JsonRecord {
  const source = record(value);
  if (moduleId === "orientation") return {
    location: source.location,
    location_source: source.location_source,
    body_id: source.body_id,
    body_generation: source.body_generation,
    position: source.position,
    heading_degrees: source.heading_degrees,
    activity_id: source.activity_id,
    affordances: source.affordances,
    freshness: source.freshness,
  };
  if (moduleId === "selfhood") {
    // The Lab's default view is the model-facing projection.  Legacy
    // identity_core/adaptive_self payloads stay available only through the
    // explicit raw record so the UI never presents internal state as final text.
    return {
      identity_core_text: source.identity_core_text,
      adaptive_self_text: source.adaptive_self_text,
    };
  }
  if (moduleId === "emotion") {
    const values = list(source.values);
    const emotions = values.length && values.every((item) => {
      const point = record(item);
      return hasContent(point.name) && point.intensity !== undefined;
    })
      ? Object.fromEntries(values.map((item) => {
        const point = record(item);
        return [String(point.name), point.intensity];
      }))
      : source.emotions;
    const active = list(source.active);
    const activeEmotions = active.length && active.every((item) => hasContent(record(item).name))
      ? active.map((item) => record(item).name)
      : source.active_emotions;
    const trends = list(source.trends);
    const trendValues = trends.length && trends.every((item) => Array.isArray(item) && item.length >= 2)
      ? Object.fromEntries(trends.map((item) => {
        const pair = Array.isArray(item) ? item : [];
        return [String(pair[0]), pair[1]];
      }))
      : source.trends;
    return {
      primary_emotion: source.primary_emotion ?? source.primary,
      secondary_emotion: source.secondary_emotion ?? source.secondary,
      emotions,
      active_emotions: activeEmotions,
      trends: trendValues,
      freshness: source.freshness,
    };
  }
  if (moduleId === "energy") return {
    energy: source.energy,
    fatigue: source.fatigue,
    is_sleeping: source.is_sleeping ?? source.sleeping,
    cognitive_mode: source.cognitive_mode,
    long_reasoning_allowed: source.long_reasoning_allowed,
    available_cognitive_budget: source.available_cognitive_budget,
    normal_budget_available: source.normal_budget_available,
    emergency_reserve_available: source.emergency_reserve_available,
    reserved_cognitive_budget: source.reserved_cognitive_budget,
  };
  if (moduleId === "motivation") return {
    recovery_pressure: source.recovery_pressure,
    recovery_status: source.recovery_status,
    cooldown_until: source.cooldown_until,
    satisfaction_until: source.satisfaction_until,
  };
  return source;
}

function setupProcessingMode(output: JsonRecord): string | undefined {
  const responseMode = String(output.response_mode ?? "");
  const reasoningMode = String(output.reasoning_mode ?? "");
  const responseLabel: Readonly<Record<string, string>> = {
    direct_reply: "直接回复",
    decision_plan: "决策计划",
  };
  const reasoningLabel: Readonly<Record<string, string>> = {
    fast: "快速处理",
    long: "深入处理",
  };
  const labels = [responseLabel[responseMode] ?? responseMode, reasoningLabel[reasoningMode] ?? reasoningMode]
    .filter(Boolean);
  return labels.length ? labels.join(" · ") : undefined;
}

function SetupNode({ node, mountOpenIds }: Readonly<{
  readonly node: TraceNode;
  readonly mountOpenIds?: ReadonlySet<string> | undefined;
}>): React.JSX.Element {
  const [openChildren, setOpenChildren] = useState<ReadonlySet<string>>(() => new Set(
    Array.from(mountOpenIds ?? []).filter((id) => id.startsWith("setup-")),
  ));
  const output = record(node.output);
  const owners = list(node.owner_snapshots).map(record);
  const selfhoodProjection = record(node.selfhood_projection);
  const budget = record(node.budget);
  const baseline = record(node.baseline_memory);
  const baselineStatus = statusOf(baseline.status);
  const baselineReason = String(baseline.reason ?? baseline.skip_reason ?? "");
  const normalMemorySkip = baselineStatus === "skipped" && baselineReason === "baseline_recall_not_relevant";
  const overview: JsonRecord = {
    processing_mode: setupProcessingMode(output),
    depth: output.depth,
    depth_basis: output.depth_basis,
    cognitive_mode: budget.cognitive_mode,
    max_steps: budget.max_steps,
    max_model_calls: budget.max_model_calls,
    max_planned_model_calls: budget.max_planned_model_calls,
    max_tool_calls: budget.max_tool_calls,
    deadline_seconds: budget.deadline_seconds ?? budget.hard_deadline_seconds,
    max_context_tokens: budget.max_context_tokens,
  };
  const toggle = (id: string): void => {
    setOpenChildren((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  return <>
    <Fields values={overview} />
    {owners.length ? <section className="trace-owner-section"><h4>进入推理时冻结状态</h4><div className="trace-owner-list">{owners.map((owner, index) => {
      const id = `setup-${String(owner.id ?? index)}`;
      return <OwnerSnapshot
        key={id}
        id={id}
        onToggle={toggle}
        open={openChildren.has(id)}
        owner={owner}
        projection={String(owner.id ?? "") === "selfhood" ? selfhoodProjection : undefined}
      />;
    })}</div></section> : null}
    {hasContent(baseline) && !normalMemorySkip ? <TraceDisclosure
      id="setup-baseline-memory"
      title="基础记忆"
      onToggle={toggle}
      open={openChildren.has("setup-baseline-memory")}
      raw={undefined}
      status={baseline.status}
      showStatus={false}
      showRaw={false}
    >
      <Fields values={{
        status: baselineStatus === "recalled" ? undefined : baseline.status,
        query: baseline.query,
        revision: baseline.revision,
        returned_count: list(baseline.returned_points).length,
        reason: baselineReason,
      }} />
      <MemoryEvidence points={list(baseline.returned_points)} fallback={baseline.returned_evidence} />
    </TraceDisclosure> : null}
  </>;
}

function OwnerSnapshot({
  id,
  number,
  onToggle,
  open,
  owner,
  projection,
}: Readonly<{
  readonly id: string;
  readonly number?: string;
  readonly onToggle: (id: string) => void;
  readonly open: boolean;
  readonly owner: TraceNode;
  readonly projection?: JsonRecord | undefined;
}>): React.JSX.Element {
  const outputSource = projection !== undefined && hasContent(projection) ? projection : owner.output;
  const output = ownerOutput(String(owner.id ?? ""), outputSource);
  return <TraceDisclosure
    id={id}
    {...(number !== undefined ? { number } : {})}
    title={String(owner.title ?? owner.id ?? "模块")}
    onToggle={onToggle}
    open={open}
    raw={owner.raw}
    status={owner.status}
    showStatus={false}
    showRaw={false}
  >
    <Fields values={output} />
  </TraceDisclosure>;
}

function modelInput(call: TraceNode): string {
  const input = record(call.input);
  const request = record(call.request);
  const system = input.system_prompt ?? request.system_prompt;
  const user = input.user_prompt ?? request.user_prompt;
  return `SYSTEM\n${pretty(system)}\n\nUSER\n${pretty(user)}`;
}

function modelCallParameters(call: TraceNode): JsonRecord {
  const effective = record(call.effective_parameters);
  const output = record(call.output);
  const value = (key: string, fallback: unknown = "未采集"): unknown => {
    const candidate = effective[key] ?? output[key];
    return candidate === undefined || candidate === null ? fallback : candidate;
  };
  const allowedTools = effective.allowed_tools;
  return {
    provider: value("provider"),
    model: value("model"),
    reasoning_mode: value("reasoning_mode"),
    response_mode: value("response_mode"),
    response_schema: value("response_schema"),
    selected_mode: value("selected_mode"),
    temperature: value("temperature"),
    max_tokens: value("max_tokens"),
    timeout_seconds: value("timeout_seconds"),
    allowed_tools: Array.isArray(allowedTools)
      ? (allowedTools.length ? allowedTools : "无")
      : value("allowed_tools"),
    tool_definition_count: value("tool_definition_count"),
    skill_count: value("skill_count"),
  };
}

function ModelCallBody({ call }: Readonly<{ readonly call: TraceNode }>): React.JSX.Element {
  const capabilities = record(call.capabilities);
  const responseSchema = record(call.effective_parameters).response_schema_definition;
  const toolDefinitions = capabilities.tool_definitions;
  const availableSkills = capabilities.available_skills;
  const output = record(call.output);
  const parsed = output.parsed_result;
  return <article className="trace-model-call">
    <section className="trace-evidence"><h4>有效参数</h4><Fields values={modelCallParameters(call)} /></section>
    {hasContent(responseSchema) ? <Evidence title="响应结构定义" value={responseSchema} /> : null}
    {hasContent(toolDefinitions) ? <Evidence title="工具定义" value={toolDefinitions} /> : null}
    {hasContent(availableSkills) ? <Evidence title="技能清单" value={availableSkills} /> : null}
    <Evidence title="用量" value={{ prompt_tokens: call.prompt_tokens, completion_tokens: call.completion_tokens, provider_latency_ms: call.provider_latency_ms }} />
    <Evidence title="模型输入（完整消息）" value={modelInput(call)} />
    <Evidence title="模型原始输出" value={call.response ?? output.response} />
    {hasContent(parsed) ? <Evidence title="模型结果（Host 解析）" value={parsed} /> : <div className="trace-unavailable"><span>模型结果（Host 解析）</span><Status value="unavailable" /></div>}
    {hasContent(call.provider_raw) ? <Evidence title="Provider 原始包" value={call.provider_raw} /> : null}
  </article>;
}

function modelCallMeta(call: TraceNode): string | undefined {
  const effective = record(call.effective_parameters);
  const output = record(call.output);
  const provider = effective.provider ?? output.provider;
  const fullModel = String(effective.model ?? output.model ?? "");
  const duration = formatDuration(call.duration_ms);
  // Show only the short model label (last path segment) in the trigger meta;
  // the full provider/model identity is in the expanded body's 有效参数
  // section. The trigger title "Model Call" must stay fully visible, so meta
  // is kept compact.
  const shortModel = fullModel.includes("/") ? fullModel.split("/").pop() ?? fullModel : fullModel;
  const modelPart = shortModel || (provider ? String(provider) : "");
  return [modelPart, duration === "未记录" ? "" : duration].filter(Boolean).join(" · ") || undefined;
}

function ModelCall({
  call,
  id,
  onToggle,
  open,
}: Readonly<{
  readonly call: TraceNode;
  readonly id: string;
  readonly onToggle: (id: string) => void;
  readonly open: boolean;
}>): React.JSX.Element {
  return <TraceDisclosure
    id={id}
    number={String(call.number ?? "")}
    title="Model Call"
    meta={modelCallMeta(call)}
    onToggle={onToggle}
    open={open}
    raw={call.raw ?? call}
    status={call.status}
    tooltip={SUB_STEP_DESCRIPTIONS.model_call}
  >
    <ModelCallBody call={call} />
  </TraceDisclosure>;
}

function ContextBuild({
  build,
  id,
  onToggle,
  open,
}: Readonly<{
  readonly build: TraceNode;
  readonly id: string;
  readonly onToggle: (id: string) => void;
  readonly open: boolean;
}>): React.JSX.Element {
  const output = record(build.output);
  const systemPrompt = output.system_prompt;
  const userPrompt = output.user_prompt;
  const compiledPrompt = hasContent(systemPrompt) || hasContent(userPrompt)
    ? `SYSTEM\n${pretty(systemPrompt)}\n\nUSER\n${pretty(userPrompt)}`
    : undefined;
  const trim = record(output.trim);
  const trimSummary = trim.truncated || trim.memory_truncated
    || Number(trim.event_truncated_count ?? 0) > 0
    || Number(trim.history_truncated_count ?? 0) > 0
    || Number(trim.run_observation_truncated_count ?? 0) > 0
    ? {
      status: "已裁剪",
      affected_sections: [
        trim.memory_truncated ? "记忆" : null,
        Number(trim.event_truncated_count ?? 0) > 0 ? "事件" : null,
        Number(trim.history_truncated_count ?? 0) > 0 ? "历史" : null,
        Number(trim.run_observation_truncated_count ?? 0) > 0 ? "本轮观察" : null,
      ].filter((item): item is string => item !== null),
      max_context_tokens: trim.max_tokens,
    }
    : undefined;
  return <TraceDisclosure
    id={id}
    number={String(build.number ?? "")}
    title="Context Build"
    onToggle={onToggle}
    open={open}
    raw={build.raw ?? build}
    status={build.status}
    tooltip={SUB_STEP_DESCRIPTIONS.context_build}
  >
    <Evidence title="编译结果（完整消息）" value={compiledPrompt} />
    {trimSummary ? <Evidence title="上下文裁剪" value={trimSummary} /> : null}
  </TraceDisclosure>;
}

function ActionBody({ action }: Readonly<{ readonly action: TraceNode }>): React.JSX.Element {
  return <>
    <Evidence title="输入" value={action.input} />
    <Evidence title="输出" value={action.output} />
  </>;
}

function reasoningOverview(node: TraceNode): JsonRecord {
  const output = record(node.output);
  const failure = output.failure_reason;
  const fallback = output.fallback_reason;
  const reason = hasContent(failure) && hasContent(fallback) && String(failure) !== String(fallback)
    ? `${String(failure)}；回退：${String(fallback)}`
    : failure ?? fallback;
  return {
    model_calls: output.model_calls ?? "未采集",
    tool_calls: output.tool_calls ?? "未采集",
    skill_calls: output.skill_calls ?? "未采集",
    run_reason: hasContent(reason) ? reason : undefined,
  };
}

const COGNITIVE_ACTION_LABELS: Readonly<Record<string, string>> = {
  recall_memory: "回忆记忆",
  answer: "回答草稿",
  clarification: "澄清草稿",
  noop: "无操作草稿",
};

function cognitiveActionMeta(action: TraceNode): string | undefined {
  const output = record(action.output);
  const type = typeof output.type === "string" ? output.type : "";
  if (!type) return "Host 解析";
  const label = COGNITIVE_ACTION_LABELS[type] ?? type;
  return `${label} · Host 解析`;
}

function GuardBody({ guard }: Readonly<{ readonly guard: TraceNode }>): React.JSX.Element {
  return <>
    <Evidence title="输入" value={guard.input} />
    <Evidence title="输出" value={guard.output} />
  </>;
}

function StepBody({ step, completion }: Readonly<{ readonly step: TraceNode; readonly completion: boolean }>): React.JSX.Element {
  const memoryRecall = step.operation === "memory_recall";
  if (memoryRecall) {
    return <>
      <Fields values={{ query: step.query, reason: step.reason, status: step.status, detail: step.detail }} />
      <Evidence title="记忆记录" value={step.returned_evidence ?? step.summary} />
    </>;
  }
  if (completion) {
    return <>
      <Fields values={{
        verdict: step.verdict,
        action_type: step.action_type,
        revision_requested: step.revision_requested,
        external_claim_replaced: step.external_claim_replaced,
        current_nest_sanitized: step.current_nest_sanitized,
        memory_use_count: step.memory_use_count,
      }} />
      <Evidence title="判断结果" value={step.content ?? step.summary} />
    </>;
  }
  return <Evidence title="输出" value={step.summary} />;
}

function StepList({
  title,
  steps,
  numberStart,
  numberPrefix,
  idPrefix,
  openChildren,
  onToggle,
  completion = false,
}: Readonly<{
  readonly title?: string;
  readonly steps: readonly unknown[];
  readonly numberStart: number;
  readonly numberPrefix: string;
  readonly idPrefix: string;
  readonly openChildren: ReadonlySet<string>;
  readonly onToggle: (id: string) => void;
  readonly completion?: boolean;
}>): React.JSX.Element | null {
  if (!steps.length) return null;
  const list = <div className="trace-step-list">{steps.map((value, index) => {
    const step = record(value);
    const id = `${idPrefix}-${String(step.ordinal ?? index)}`;
    const fallback = completion && ["fallback", "safe_noop"].includes(statusOf(step.status));
    const itemTitle = completion ? (fallback ? "终止回退" : "完成判定") : step.operation === "memory_recall" ? "Memory Recall" : String(step.operation ?? step.kind ?? `Step ${index + 1}`);
    return <TraceDisclosure
      id={id}
      key={id}
      number={`${numberPrefix}.${numberStart + index}`}
      title={itemTitle}
      meta={undefined}
      onToggle={onToggle}
      open={openChildren.has(id)}
      raw={step}
      status={step.status}
      showStatus={!fallback}
      tooltip={completion ? SUB_STEP_DESCRIPTIONS.judge : SUB_STEP_DESCRIPTIONS[String(step.operation ?? step.kind ?? "")]}
    >
      <StepBody completion={completion} step={step} />
    </TraceDisclosure>;
  })}</div>;
  return title ? <section className="trace-step-section"><h4>{title}</h4>{list}</section> : list;
}

function ObservationStage({
  stage,
  observations,
  id,
  onToggle,
  open,
  openChildren,
}: Readonly<{
  readonly stage: TraceNode | undefined;
  readonly observations: readonly unknown[];
  readonly id: string;
  readonly onToggle: (id: string) => void;
  readonly open: boolean;
  readonly openChildren: ReadonlySet<string>;
}>): React.JSX.Element | null {
  if (!observations.length) return null;
  const effectiveStage = stage ?? {
    number: "4.1.4",
    status: "observed",
    raw: { source: "production_turn_record", observations },
  };
  return <TraceDisclosure
    id={id}
    number={String(effectiveStage.number ?? "")}
    title="Observations"
    onToggle={onToggle}
    open={open}
    raw={effectiveStage.raw ?? effectiveStage}
    status={effectiveStage.status}
    tooltip={SUB_STEP_DESCRIPTIONS.observation}
  >
    <StepList
      idPrefix={`${id}-record`}
      numberStart={1}
      numberPrefix={String(effectiveStage.number ?? "4.1.4")}
      onToggle={onToggle}
      openChildren={openChildren}
      steps={observations}
      title="记录"
    />
  </TraceDisclosure>;
}

function ReasoningNode({ node, mountOpenIds }: Readonly<{ readonly node: TraceNode; readonly mountOpenIds?: ReadonlySet<string> | undefined }>): React.JSX.Element {
  const [openChildren, setOpenChildren] = useState<ReadonlySet<string>>(() => new Set(mountOpenIds ?? []));
  const iterations = list(node.iterations).map(record);
  const toggle = (id: string): void => {
    setOpenChildren((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  return <>
    <Fields values={reasoningOverview(node)} />
    <div className="trace-iteration-list">{iterations.map((iteration) => {
      const iterationId = `reasoning-${String(iteration.number)}`;
      const observations = list(iteration.observations);
      const completion = list(iteration.completion);
      const context = record(iteration.context_build);
      const modelCall = record(iteration.model_call);
      const action = record(iteration.action);
      const observationStage = hasContent(iteration.observation_stage) ? record(iteration.observation_stage) : undefined;
      const candidateGuard = record(iteration.guard);
      const guard = statusOf(candidateGuard.status) === "skipped" ? {} : candidateGuard;
      const completionStart = 5;
      const guardNumber = `${String(iteration.number)}.${completionStart + completion.length}`;
      return <TraceDisclosure
        id={iterationId}
        key={iterationId}
        number={String(iteration.number)}
        title="Iteration"
        onToggle={toggle}
        open={openChildren.has(iterationId)}
        raw={iteration.raw}
        status={iteration.status}
      >
        {hasContent(iteration.input) ? <Evidence title="迭代输入" value={iteration.input} /> : null}
        {hasContent(context) ? <ContextBuild build={context} id={`${iterationId}-context`} onToggle={toggle} open={openChildren.has(`${iterationId}-context`)} /> : null}
        {hasContent(modelCall) ? <ModelCall call={modelCall} id={`${iterationId}-model`} onToggle={toggle} open={openChildren.has(`${iterationId}-model`)} /> : null}
        {hasContent(action) ? <TraceDisclosure
          id={`${iterationId}-action`}
          number={`${String(iteration.number)}.3`}
          title="Cognitive Action"
          meta={cognitiveActionMeta(record(action))}
          onToggle={toggle}
          open={openChildren.has(`${iterationId}-action`)}
          raw={action.raw ?? action}
          status={action.status}
          tooltip={SUB_STEP_DESCRIPTIONS.action}
        >
          <ActionBody action={action} />
        </TraceDisclosure> : null}
        {observationStage || observations.length ? <ObservationStage
          id={`${iterationId}-observations`}
          onToggle={toggle}
          open={openChildren.has(`${iterationId}-observations`)}
          openChildren={openChildren}
          observations={observations}
          stage={observationStage}
        /> : null}
        <StepList
          completion
          idPrefix={`${String(iteration.number)}.completion`}
          numberStart={completionStart}
          numberPrefix={String(iteration.number)}
          onToggle={toggle}
          openChildren={openChildren}
          steps={completion}
        />
        {hasContent(guard) ? <TraceDisclosure
          id={`${iterationId}-guard`}
          number={guard.number ? String(guard.number) : guardNumber}
          title="Guard"
          meta={String(record(guard.output).decision ?? "") || undefined}
          onToggle={toggle}
          open={openChildren.has(`${iterationId}-guard`)}
          raw={guard.raw ?? guard}
          status={guard.status}
          tooltip={SUB_STEP_DESCRIPTIONS.guard}
        >
          {statusOf(guard.status) === "skipped" ? <SkipDetails node={guard} fallbackReason="separate Guard record is not persisted" fallbackEvidence="ReasoningRun.status + ordered steps" /> : <GuardBody guard={guard} />}
        </TraceDisclosure> : null}
      </TraceDisclosure>;
    })}</div>
    {!iterations.length ? <div className="trace-unavailable"><span>迭代</span><Status value="unavailable" /></div> : null}
  </>;
}

function DecisionNode({ node }: Readonly<{ readonly node: TraceNode }>): React.JSX.Element {
  const output = record(node.output);
  const textOutput = [...list(output.speech_texts), ...list(output.message_texts)];
  const intentOutput = {
    speech_intents: list(output.speech_intents),
    message_intents: list(output.message_intents),
    motion_intents: list(output.motion_intents),
    expression_intents: list(output.expression_intents),
    action_intents: list(output.action_intents),
    activity_intents: list(output.activity_intents),
    noop_intents: list(output.noop_intents),
  };
  return <>
    {textOutput.length ? <Evidence title="输出文本" value={textOutput} /> : null}
    <IntentEvidence groups={{
      "语音": intentOutput.speech_intents,
      "消息": intentOutput.message_intents,
      "动作": [...intentOutput.motion_intents, ...intentOutput.action_intents],
      "表情": intentOutput.expression_intents,
      "Activity": intentOutput.activity_intents,
      "No-op": intentOutput.noop_intents,
    }} />
  </>;
}

function GovernanceNode({ node, preview }: Readonly<{ readonly node: TraceNode; readonly preview: PreviewResult | null }>): React.JSX.Element {
  const [openChildren, setOpenChildren] = useState<ReadonlySet<string>>(() => new Set());
  const output = record(node.output);
  const result = record(output.result);
  const receipts = list(output.receipts);
  const delivery = record(node.delivery);
  const deliveryOutput = record(delivery.output);
  const activityRequest = record(delivery.activity_request);
  const deliveryId = `${String(node.id ?? "governance")}-delivery`;
  const routingId = `${String(node.id ?? "governance")}-routing`;
  const toggle = (id: string): void => {
    setOpenChildren((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const resultSummary = {
    success: result.success,
    speech: result.speech,
    message: result.message,
    error: result.error,
  };
  return <>
    <Evidence title="实际结果" value={resultSummary} />
    <ReceiptEvidence receipts={receipts} />
    {hasContent(record(node.routing)) ? <TraceDisclosure
      id={routingId}
      title="路由明细"
      onToggle={toggle}
      open={openChildren.has(routingId)}
      raw={node.routing}
      status="recorded"
      showStatus={false}
    >
      <Fields values={record(node.routing)} />
    </TraceDisclosure> : null}
    {list(output.activity_proposals).length ? <Evidence title="Activity 提案" value={output.activity_proposals} /> : null}
    {hasContent(delivery) ? <TraceDisclosure
      id={deliveryId}
      number={String(delivery.number ?? "6.1")}
      title={String(delivery.title ?? "Delivery / Activity request")}
      meta={`${list(deliveryOutput.receipts).length} 个回执`}
      onToggle={toggle}
      open={openChildren.has(deliveryId)}
      raw={delivery.raw ?? delivery}
      status={delivery.status}
    >
      <Evidence title="交付输入" value={delivery.input} />
      <Evidence title="交付结果" value={deliveryOutput.result} />
      <ReceiptEvidence receipts={list(deliveryOutput.receipts)} />
      {list(deliveryOutput.activity_proposals).length ? <Evidence title="Activity 提案" value={deliveryOutput.activity_proposals} /> : null}
      {hasContent(activityRequest) ? <TraceDisclosure
        id={`${deliveryId}-activity-request`}
        title={String(activityRequest.title ?? "Activity request")}
        onToggle={toggle}
        open={openChildren.has(`${deliveryId}-activity-request`)}
        raw={activityRequest.raw ?? activityRequest}
        status={activityRequest.status}
      >
        {statusOf(activityRequest.status) === "skipped" ? <SkipDetails node={activityRequest} fallbackReason="no activity request in TurnDecision" fallbackEvidence="TurnDecision.activity_intents" /> : <>
          <Evidence title="输入" value={activityRequest.input} />
          <Evidence title="输出" value={activityRequest.output} />
        </>}
      </TraceDisclosure> : null}
    </TraceDisclosure> : null}
    {preview !== null ? <div className="trace-preview"><strong>动作回放</strong><span>{preview.status === "completed" ? "已完成" : "不支持"}</span><p>{preview.reason}</p></div> : null}
  </>;
}

function WritebackBody({ writeback }: Readonly<{ readonly writeback: TraceNode }>): React.JSX.Element {
  const candidates = list(writeback.candidates);
  const commits = list(writeback.commits);
  const reinforcements = list(writeback.reinforcements);
  return <>
    {candidates.length ? <section className="trace-evidence"><h4>编码候选</h4><BlockList items={candidates} /></section> : null}
    {commits.length ? <section className="trace-evidence"><h4>编码提交</h4><BlockList items={commits} /></section> : null}
    {reinforcements.length ? <section className="trace-evidence"><h4>记忆强化</h4><BlockList items={reinforcements} /></section> : null}
  </>;
}

function SettlementNode({ node }: Readonly<{ readonly node: TraceNode }>): React.JSX.Element {
  const [openChildren, setOpenChildren] = useState<ReadonlySet<string>>(() => new Set());
  const toggle = (id: string): void => {
    setOpenChildren((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const output = record(node.output);
  const writeback = record(node.memory_writeback);
  const emotionChanges = record(node.emotion_changes);
  const energySettlement = record(node.energy_settlement);
  const writebackId = `${String(node.id ?? "settlement")}-memory-writeback`;
  const emotionId = `${String(node.id ?? "settlement")}-emotion-changes`;
  const energyId = `${String(node.id ?? "settlement")}-energy-settlement`;
  const state = record(output.state_after);
  const stateDiffRows = readableStateDiff(output.state_diff);
  const cognitiveTurn = record(output.cognitive_turn);
  const cognitiveSummary = Object.fromEntries(["status", "model_mode", "error_code", "fallback_reason", "stale_reason", "timeout_reason"]
    .map((key) => [key, cognitiveTurn[key]] as const)
    .filter(([, value]) => hasContent(value)));
  const emotionRows: JsonRecord = {};
  for (const item of list(emotionChanges.dimensions)) {
    const point = record(item);
    const name = String(point.name ?? point.dimension ?? "");
    if (!name || (!hasContent(point.before) && !hasContent(point.after))) continue;
    emotionRows[name] = diffLeafText(point);
  }
  const energyRows: JsonRecord = {
    ...Object.fromEntries(Object.entries(energySettlement).filter(([key]) => key !== "energy_state")),
    ...record(energySettlement.energy_state),
  };
  const stateCore = {
    energy: state.energy,
    fatigue: state.fatigue,
    primary_emotion: state.primary_emotion,
    is_sleeping: state.is_sleeping,
    cognitive_mode: state.cognitive_mode,
    normal_budget_available: state.normal_budget_available,
    emergency_reserve_available: state.emergency_reserve_available,
    reserved_cognitive_budget: state.reserved_cognitive_budget,
  };
  return <>
    <Evidence title="警告" value={output.warnings} emptyLabel="无" />
    <Evidence title="处理后状态" value={stateCore} />
    <Evidence title="状态变化" value={stateDiffRows} />
    {hasContent(cognitiveSummary) ? <Evidence title="认知回合" value={cognitiveSummary} /> : null}
    {hasContent(writeback) ? <TraceDisclosure
      id={writebackId}
      title="记忆写回"
      onToggle={toggle}
      open={openChildren.has(writebackId)}
      raw={node.memory_writeback}
      status="recorded"
      showStatus={false}
    >
      <WritebackBody writeback={writeback} />
    </TraceDisclosure> : null}
    {hasContent(emotionChanges) ? <TraceDisclosure
      id={emotionId}
      title="情绪变化"
      onToggle={toggle}
      open={openChildren.has(emotionId)}
      raw={node.emotion_changes}
      status="recorded"
      showStatus={false}
    >
      <Fields values={{ stage: emotionChanges.stage, changed_dimensions: emotionChanges.changed_dimensions }} />
      {Object.keys(emotionRows).length ? <section className="trace-evidence"><h4>维度变化</h4><Fields values={emotionRows} /></section> : null}
    </TraceDisclosure> : null}
    {hasContent(energySettlement) ? <TraceDisclosure
      id={energyId}
      title="能量结算"
      onToggle={toggle}
      open={openChildren.has(energyId)}
      raw={node.energy_settlement}
      status="recorded"
      showStatus={false}
    >
      <Fields values={energyRows} />
    </TraceDisclosure> : null}
  </>;
}

function NodeBody({ node, preview, mountOpenIds }: Readonly<{
  readonly node: TraceNode;
  readonly preview: PreviewResult | null;
  readonly mountOpenIds?: ReadonlySet<string> | undefined;
}>): React.JSX.Element {
  const id = String(node.id ?? "");
  if (id === "event_admission") return <AdmissionNode node={node} />;
  if (id === "context_workspace") return <WorkspaceNode mountOpenIds={mountOpenIds} node={node} />;
  if (id === "setup") return <SetupNode mountOpenIds={mountOpenIds} node={node} />;
  if (id === "reasoning_run") return <ReasoningNode node={node} mountOpenIds={mountOpenIds} />;
  if (id === "turn_decision") return <DecisionNode node={node} />;
  if (id === "governance_delivery") return <GovernanceNode node={node} preview={preview} />;
  if (id === "settlement") return <SettlementNode node={node} />;
  return <TraceIO node={node} />;
}

function NodeRaw({ node }: Readonly<{ readonly node: TraceNode }>): React.JSX.Element {
  return hasContent(node.raw)
    ? <pre className="trace-code trace-node-raw-view">{pretty(node.raw)}</pre>
    : <div className="trace-unavailable"><span>原始记录</span><Status value="unavailable" /></div>;
}

function NodeCard({ node, open, onToggle, preview, mountOpenIds }: Readonly<{
  readonly node: TraceNode;
  readonly open: boolean;
  readonly onToggle: () => void;
  readonly preview: PreviewResult | null;
  readonly mountOpenIds?: ReadonlySet<string> | undefined;
}>): React.JSX.Element {
  const [rawMode, setRawMode] = useState(false);
  const stageTip = STAGE_DESCRIPTIONS[String(node.id ?? "")];
  const toggleRaw = () => {
    if (!open) onToggle();
    setRawMode((current) => !current);
  };
  return <article className={`trace-node${open ? " is-open" : ""}`}>
    <div className="trace-node-header">
      <button aria-expanded={open} className="trace-node-trigger" data-tip={stageTip} onClick={onToggle} type="button">
        <span className="trace-node-number">{String(node.number ?? "")}</span>
        <span className="trace-node-title"><strong>{String(node.title ?? node.id ?? "未命名阶段")}</strong><small>{nodeMeta(node)}</small></span>
        <span className="trace-node-aside"><Status value={node.status} /></span>
      </button>
      <button aria-pressed={rawMode} className="trace-node-mode" onClick={toggleRaw} type="button">{rawMode ? "摘要" : "原始记录"}</button>
    </div>
    {open ? <div className="trace-node-body">{rawMode ? <NodeRaw node={node} /> : <NodeBody mountOpenIds={mountOpenIds} node={node} preview={preview} />}</div> : null}
  </article>;
}

function TurnInspector({ session, turn, preview, openNodes, onToggle }: Readonly<{ readonly session: ElfieSession | null; readonly turn: ElfieTurn; readonly preview: PreviewResult | null; readonly openNodes: ReadonlySet<string>; readonly onToggle: (id: string) => void }>): React.JSX.Element {
  const nodes = projectedNodes(turn);
  const index = session?.turns.findIndex((item) => item.turn_id === turn.turn_id) ?? -1;
  const stimulus = record(turn.stimulus_bundle);
  const reasoning = record(traceStages(turn).reasoning);
  const projected = record(traceStages(turn).observability);
  const reasoningNode = record(nodes.find((node) => node.id === "reasoning_run"));
  const stimulusMessage = typeof stimulus.message === "string" ? stimulus.message : "";
  const iterations = list(reasoningNode.iterations).length || list(reasoning.steps).length ? list(reasoningNode.iterations).length || 1 : 0;
  const calls = typeof reasoning.model_calls === "number" ? reasoning.model_calls : list(traceStages(turn).model_calls).length;
  const overallStatus = turn.result.success === false || turn.error ? "failed" : turn.result.success === true ? "completed" : "unavailable";
  return <>
    <section className="trace-turn-header">
      <div className="trace-turn-title-row"><h3>{index >= 0 ? `Turn ${String(index + 1).padStart(2, "0")}` : "Turn"}</h3><Status value={overallStatus} /></div>
      <p className="trace-turn-message">{stimulusMessage || "非文字刺激"}</p>
      <div className="trace-turn-meta"><span>{new Date(turn.timestamp).toLocaleTimeString("zh-CN")}</span><span>{stimulus.source_domain === "embodied" ? "现场" : stimulus.source_domain === "activity" ? "Activity" : "消息"}</span></div>
    </section>
    <dl className="trace-stat-row"><div><dt>耗时</dt><dd>{formatDuration(turn.duration_ms)}</dd></div><div><dt>迭代</dt><dd>{iterations}</dd></div><div><dt>模型调用</dt><dd>{calls}</dd></div><div><dt>记录来源</dt><dd>{projected.source === "production_turn_record" ? "生产链路" : "未采集"}</dd></div></dl>
    <section className="trace-chain" aria-label="Turn 处理链路">{nodes.map((node) => <NodeCard key={`${turn.turn_id}:${String(node.id)}`} mountOpenIds={openNodes} node={node} onToggle={() => onToggle(String(node.id))} open={openNodes.has(String(node.id))} preview={preview} />)}</section>
  </>;
}

export function DetailPanel({ session, selectedTurn, open, initialTab, focus, previewResult, onClose, defaultOpenDetails }: Props): React.JSX.Element {
  const [openNode, setOpenNode] = useState<ReadonlySet<string>>(() => new Set(defaultOpenDetails ?? [defaultNodeId(focus, initialTab)]));
  useEffect(() => { setOpenNode(new Set(defaultOpenDetails ?? [defaultNodeId(focus, initialTab)])); }, [defaultOpenDetails, focus, initialTab, selectedTurn?.turn_id]);
  if (selectedTurn === null) return <></>;
  return <aside aria-hidden={!open} className={open ? "detail-panel" : "detail-panel is-closed"}>
    <div className="detail-heading"><div><h2>Turn 检查器</h2></div><Button aria-label="收起回合详情" onClick={onClose} shape="circle" type="text">×</Button></div>
    <div className="detail-content inspector-content"><TurnInspector
      onToggle={(id) => setOpenNode((current) => {
        const next = new Set(current);
        if (next.has(id)) next.delete(id);
        else {
          next.clear();
          next.add(id);
        }
        return next;
      })}
      openNodes={openNode}
      preview={previewResult}
      session={session}
      turn={selectedTurn}
    /></div>
  </aside>;
}
