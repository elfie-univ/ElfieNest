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
}>;

type JsonRecord = Record<string, unknown>;
type TraceNode = JsonRecord;
type TraceStatus = string;

const statusLabels: Readonly<Record<string, string>> = {
  completed: "已记录",
  recorded: "已记录",
  returned: "已返回",
  accepted: "已接受",
  unavailable: "未采集",
  missing: "未采集",
  skipped: "Skip",
  empty: "无输出",
  failed: "失败",
  continued: "继续",
  stopped: "停止",
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
  const glyph = status === "failed" ? "!" : status === "unavailable" ? "?" : status === "skipped" ? "–" : "✓";
  return <span className={`trace-status trace-status-${status}`}><span aria-hidden="true">{glyph}</span>{statusLabel(status)}</span>;
}

function formatDuration(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "未记录";
  return value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(2)} s`;
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
    reasoning_mode: "推理强度",
    response_mode: "响应模式",
    response_schema: "响应结构",
    temperature: "Temperature",
    max_tokens: "Max tokens",
    allowed_tools: "允许工具",
    tool_definition_count: "工具定义",
    skill_count: "技能数量",
    provider: "Provider",
    model: "模型",
    selected_mode: "解析模式",
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
    detail: "记忆处理结果",
    model_key: "模型标识",
    supports_json_schema: "JSON Schema",
    supports_tool_calling: "工具调用",
    supports_json_mode: "JSON 模式",
    supports_plain_text: "普通文本",
    max_output_tokens: "最大输出 Token",
    revision: "版本",
    freshness: "新鲜度",
    location: "位置",
    primary_emotion: "主情绪",
    emotions: "情绪值",
    energy: "能量",
    normal_budget_available: "普通认知配额",
    emergency_reserve_available: "紧急储备",
    reserved_cognitive_budget: "已预留认知配额",
    energy_revision: "能量版本",
    fatigue: "疲劳",
    is_sleeping: "睡眠中",
    cognitive_mode: "认知模式",
    emotion_revision: "情绪版本",
    recovery_status: "恢复状态",
    recovery_pressure: "恢复压力",
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
  };
  return labels[key] ?? key;
}

function FieldValue({ value }: Readonly<{ readonly value: unknown }>): React.JSX.Element {
  if (!hasContent(value)) return <span className="trace-muted">未记录</span>;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return <span className="trace-value-text">{String(value)}</span>;
  }
  return <pre className="trace-code trace-code-inline">{pretty(value)}</pre>;
}

function Fields({ values, omit = [] }: Readonly<{ readonly values: JsonRecord; readonly omit?: readonly string[] }>): React.JSX.Element {
  const excluded = new Set(omit);
  const entries = Object.entries(values).filter(([key, value]) => !excluded.has(key) && hasContent(value));
  if (!entries.length) return <p className="trace-muted">未采集</p>;
  return <dl className="trace-fields">{entries.map(([key, value]) => <div className="trace-field" key={key}><dt>{fieldLabel(key)}</dt><dd><FieldValue value={value} /></dd></div>)}</dl>;
}

function Evidence({ title, value, emptyLabel = "未采集" }: Readonly<{ readonly title: string; readonly value: unknown; readonly emptyLabel?: string }>): React.JSX.Element {
  const objectValue = typeof value === "object" && value !== null && !Array.isArray(value) ? record(value) : null;
  const textList = Array.isArray(value) && value.length > 0 && value.every((item) => typeof item === "string");
  return <section className="trace-evidence"><h4>{title}</h4>{hasContent(value) ? objectValue !== null ? <Fields values={objectValue} /> : textList ? <div className="trace-text-list">{value.map((item, index) => <p key={`${String(item)}-${index}`}>{item}</p>)}</div> : <pre className="trace-code">{pretty(value)}</pre> : <p className="trace-muted">{emptyLabel}</p>}</section>;
}

function readableSettlementValue(value: unknown, key = ""): unknown {
  if (Array.isArray(value)) {
    const items = value.map((item) => readableSettlementValue(item)).filter(hasContent);
    return items.length ? items : undefined;
  }
  if (typeof value !== "object" || value === null) return value;
  const hiddenKeys = new Set(["body_snapshot", "captured_at", "elapsed_time", "journal", "profile_anchor", "source_event_ids", "unknown_fields"]);
  const entries = Object.entries(record(value))
    .filter(([childKey]) => !hiddenKeys.has(childKey) && !childKey.endsWith("_id") && !childKey.endsWith("_ids"))
    .map(([childKey, childValue]) => [childKey, readableSettlementValue(childValue, childKey)] as const)
    .filter(([, childValue]) => hasContent(childValue));
  return entries.length || key === "" ? Object.fromEntries(entries) : undefined;
}

function MemoryEvidence({ points, fallback }: Readonly<{ readonly points: readonly unknown[]; readonly fallback: unknown }>): React.JSX.Element {
  if (!points.length) return <Evidence title="模型收到的记忆证据" value={fallback} />;
  return <section className="trace-evidence"><h4>模型收到的记忆证据</h4><div className="trace-memory-list">{points.map((value, index) => {
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
    return <article className="trace-intent" key={`${title}-${index}`}><header><strong>{title}</strong><Status value={intent.status ?? "recorded"} /></header>{hasContent(text) ? <p>{String(text)}</p> : <p className="trace-muted">未提供可读内容</p>}</article>;
  }))}</div></section>;
}

function ReceiptEvidence({ receipts }: Readonly<{ readonly receipts: readonly unknown[] }>): React.JSX.Element | null {
  if (!receipts.length) return null;
  return <section className="trace-evidence"><h4>执行回执</h4><div className="trace-receipt-list">{receipts.map((value, index) => {
    const receipt = record(value);
    return <article className="trace-receipt" key={`${String(receipt.status ?? "receipt")}-${index}`}><header><strong>{String(receipt.executor ?? "执行器")}</strong><Status value={receipt.status} /></header><Fields values={{ occurred_at: receipt.occurred_at, error: receipt.error }} /></article>;
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
}>): React.JSX.Element {
  const [rawMode, setRawMode] = useState(false);
  const hasRaw = hasContent(raw);
  const visibleMeta = statusOf(status) === "skipped" ? undefined : meta;
  return <section className={`trace-disclosure${open ? " is-open" : ""}`}>
    <div className="trace-disclosure-header">
      <button aria-expanded={open} className="trace-disclosure-trigger" onClick={() => onToggle(id)} type="button">
        <span aria-hidden="true" className="trace-disclosure-chevron">{open ? "⌄" : "›"}</span>
        {number ? <span className="trace-disclosure-number">{number}</span> : null}
        <span className="trace-disclosure-title"><strong>{title}</strong>{visibleMeta ? <small>{visibleMeta}</small> : null}</span>
        <Status value={status} />
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

function nodeMeta(node: TraceNode): string {
  const id = String(node.id ?? "");
  if (id === "reasoning_run") return `${list(node.iterations).length} 个迭代`;
  if (id === "setup") return `${list(node.owner_snapshots).length} 个快照`;
  if (id === "governance_delivery") return `${list(record(node.output).receipts).length} 个回执`;
  if (id === "settlement") return formatDuration(node.duration_ms ?? record(node.output).duration_ms);
  const output = record(node.output);
  return typeof output.context_revision === "number" ? `revision ${output.context_revision}` : "";
}

function ownerOutput(moduleId: string, value: unknown): JsonRecord {
  const source = record(value);
  if (moduleId === "orientation") return {
    revision: source.revision,
    freshness: source.freshness,
    location: source.location,
    body_id: source.body_id,
    active_channel_id: source.active_channel_id,
    active_conversation_id: source.active_conversation_id,
    activity_id: source.activity_id,
    affordances: source.affordances,
  };
  if (moduleId === "selfhood") {
    const identity = record(source.identity_core);
    const adaptive = record(source.adaptive_self);
    return {
      revision: source.revision,
      identity_core: {
        display_name: identity.display_name,
        species_name: identity.species_name,
        resident_role: identity.resident_role,
      },
      interaction_tendencies: adaptive.interaction_tendency_ids,
      coping_tendencies: adaptive.coping_tendency_ids,
      expression_tendencies: adaptive.expression_tendency_ids,
      values: adaptive.value_ids,
      speech_markers: adaptive.speech_marker_ids,
    };
  }
  if (moduleId === "emotion") return {
    primary_emotion: source.primary_emotion,
    emotions: source.emotions,
    emotion_revision: source.emotion_revision,
  };
  if (moduleId === "energy") return {
    energy: source.energy,
    fatigue: source.fatigue,
    is_sleeping: source.is_sleeping,
    cognitive_mode: source.cognitive_mode,
    normal_budget_available: source.normal_budget_available,
    emergency_reserve_available: source.emergency_reserve_available,
    reserved_cognitive_budget: source.reserved_cognitive_budget,
    energy_revision: source.energy_revision,
  };
  if (moduleId === "motivation") return {
    revision: source.revision,
    recovery_pressure: source.recovery_pressure,
    recovery_status: source.recovery_status,
    last_trigger_id: source.last_trigger_id,
  };
  return source;
}

function SetupNode({ node }: Readonly<{ readonly node: TraceNode }>): React.JSX.Element {
  const [openChildren, setOpenChildren] = useState<ReadonlySet<string>>(() => new Set());
  const output = record(node.output);
  const owners = list(node.owner_snapshots).map(record);
  const baseline = record(node.baseline_memory);
  const toggle = (id: string): void => {
    setOpenChildren((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  return <>
    <Fields values={output} omit={["turn_id", "capabilities", "allowed_tools", "temperature", "max_tokens", "tool_definition_count", "skill_count"]} />
    {owners.length ? <section className="trace-owner-section"><h4>模块快照</h4><div className="trace-owner-list">{owners.map((owner, index) => {
      const id = `setup-${String(owner.id ?? index)}`;
      return <OwnerSnapshot key={id} id={id} number={`3.${index + 1}`} onToggle={toggle} open={openChildren.has(id)} owner={owner} />;
    })}</div></section> : null}
    {hasContent(baseline) ? <TraceDisclosure
      id="setup-baseline-memory"
      number="3.6"
      title="Baseline Memory Recall"
      meta={statusOf(baseline.status) === "skipped" ? undefined : String(baseline.status ?? "")}
      onToggle={toggle}
      open={openChildren.has("setup-baseline-memory")}
      raw={baseline.raw ?? baseline}
      status={baseline.status}
    >
      {statusOf(baseline.status) === "skipped" ? <SkipDetails node={baseline} fallbackEvidence="MEMORY_RECALL_STATUS" /> : <>
        <Fields values={baseline} omit={["returned_evidence", "returned_points", "raw", "evidence_basis"]} />
        <MemoryEvidence points={list(baseline.returned_points)} fallback={baseline.returned_evidence} />
      </>}
    </TraceDisclosure> : null}
  </>;
}

function OwnerSnapshot({
  id,
  number,
  onToggle,
  open,
  owner,
}: Readonly<{
  readonly id: string;
  readonly number: string;
  readonly onToggle: (id: string) => void;
  readonly open: boolean;
  readonly owner: TraceNode;
}>): React.JSX.Element {
  const output = ownerOutput(String(owner.id ?? ""), owner.output);
  return <TraceDisclosure
    id={id}
    number={number}
    title={String(owner.title ?? owner.id ?? "模块")}
    onToggle={onToggle}
    open={open}
    raw={owner.raw}
    status={owner.status}
  >
    <Evidence title="快照来源" value={owner.input} />
    <Evidence title="冻结快照" value={output} />
  </TraceDisclosure>;
}

function modelInput(call: TraceNode): string {
  const input = record(call.input);
  const request = record(call.request);
  const system = input.system_prompt ?? request.system_prompt;
  const user = input.user_prompt ?? request.user_prompt;
  return `SYSTEM\n${pretty(system)}\n\nUSER\n${pretty(user)}`;
}

function ModelCallBody({ call }: Readonly<{ readonly call: TraceNode }>): React.JSX.Element {
  const effective = record(call.effective_parameters);
  const capabilities = record(call.capabilities);
  const output = record(call.output);
  const parsed = output.parsed_result;
  return <article className="trace-model-call">
    <header className="trace-subcard-heading"><strong>{String(call.number ?? "")}{call.number ? " · " : ""}Model Call</strong><Status value={call.status} /><span>{formatDuration(call.duration_ms)}</span></header>
    <section className="trace-evidence"><h4>有效参数</h4><Fields values={{ ...effective, provider: effective.provider ?? output.provider, model: effective.model ?? output.model }} /></section>
    {hasContent(capabilities) ? <section className="trace-evidence"><h4>模型能力</h4><Fields values={capabilities} /></section> : null}
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
  const model = effective.model ?? output.model;
  const duration = formatDuration(call.duration_ms);
  const identity = provider && model ? `${String(provider)}/${String(model)}` : "";
  return [identity, duration === "未记录" ? "" : duration].filter(Boolean).join(" · ") || undefined;
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
  return <TraceDisclosure
    id={id}
    number={String(build.number ?? "")}
    title="Context Build"
    meta={String(record(build.output).context_revision ?? "") || undefined}
    onToggle={onToggle}
    open={open}
    raw={build.raw ?? build}
    status={build.status}
  >
    <Evidence title="输入" value={build.input} />
    <Evidence title="输出" value={build.output} />
  </TraceDisclosure>;
}

function ActionBody({ action }: Readonly<{ readonly action: TraceNode }>): React.JSX.Element {
  return <>
    <Evidence title="输入" value={action.input} />
    <Evidence title="输出" value={action.output} />
  </>;
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
  return <Evidence title={completion ? "判断结果" : "输出"} value={step.summary} />;
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
    const itemTitle = completion ? "Completion Judge" : step.operation === "memory_recall" ? "Memory Recall" : String(step.operation ?? step.kind ?? `Step ${index + 1}`);
    return <TraceDisclosure
      id={id}
      key={id}
      number={`${numberPrefix}.${numberStart + index}`}
      title={itemTitle}
      meta={String(step.status ?? "")}
      onToggle={onToggle}
      open={openChildren.has(id)}
      raw={step}
      status={step.status}
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
  readonly stage: TraceNode;
  readonly observations: readonly unknown[];
  readonly id: string;
  readonly onToggle: (id: string) => void;
  readonly open: boolean;
  readonly openChildren: ReadonlySet<string>;
}>): React.JSX.Element {
  const status = statusOf(stage.status);
  return <TraceDisclosure
    id={id}
    number={String(stage.number ?? "")}
    title="Observations"
    onToggle={onToggle}
    open={open}
    raw={stage.raw ?? stage}
    status={stage.status}
  >
    {status === "skipped" || !observations.length ? <SkipDetails node={stage} fallbackReason="no observation record in this iteration" fallbackEvidence="ReasoningRun.steps" /> : <StepList
      idPrefix={`${id}-record`}
      numberStart={1}
      numberPrefix={String(stage.number ?? "4.1.4")}
      onToggle={onToggle}
      openChildren={openChildren}
      steps={observations}
      title="记录"
    />}
  </TraceDisclosure>;
}

function ReasoningNode({ node }: Readonly<{ readonly node: TraceNode }>): React.JSX.Element {
  const [openChildren, setOpenChildren] = useState<ReadonlySet<string>>(() => new Set());
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
    <Fields values={record(node.output)} />
    <div className="trace-iteration-list">{iterations.map((iteration) => {
      const iterationId = `reasoning-${String(iteration.number)}`;
      const observations = list(iteration.observations);
      const completion = list(iteration.completion);
      const context = record(iteration.context_build);
      const modelCall = record(iteration.model_call);
      const action = record(iteration.action);
      const observationStage = hasContent(iteration.observation_stage) ? record(iteration.observation_stage) : {
        number: `${String(iteration.number)}.4`,
        status: observations.length ? "recorded" : "skipped",
        raw: { source: "production_turn_record", observations },
        skip_reason: observations.length ? undefined : "no observation record in this iteration",
        evidence_basis: "ReasoningRun.steps",
      };
      const guard = record(iteration.guard);
      const completionStart = 5;
      const guardNumber = `${String(iteration.number)}.${completionStart + completion.length}`;
      return <TraceDisclosure
        id={iterationId}
        key={iterationId}
        number={String(iteration.number)}
        title="Iteration"
        meta={String(record(iteration.input).context_revision ?? "") ? `context v${String(record(iteration.input).context_revision)}` : undefined}
        onToggle={toggle}
        open={openChildren.has(iterationId)}
        raw={iteration.raw}
        status={iteration.status}
      >
        <Evidence title="迭代输入" value={iteration.input} />
        {hasContent(context) ? <ContextBuild build={context} id={`${iterationId}-context`} onToggle={toggle} open={openChildren.has(`${iterationId}-context`)} /> : null}
        {hasContent(modelCall) ? <ModelCall call={modelCall} id={`${iterationId}-model`} onToggle={toggle} open={openChildren.has(`${iterationId}-model`)} /> : null}
        {hasContent(action) ? <TraceDisclosure
          id={`${iterationId}-action`}
          number={`${String(iteration.number)}.3`}
          title="Cognitive Action"
          meta="Host 解析"
          onToggle={toggle}
          open={openChildren.has(`${iterationId}-action`)}
          raw={action.raw ?? action}
          status={action.status}
        >
          <ActionBody action={action} />
        </TraceDisclosure> : null}
        <ObservationStage
          id={`${iterationId}-observations`}
          onToggle={toggle}
          open={openChildren.has(`${iterationId}-observations`)}
          openChildren={openChildren}
          observations={observations}
          stage={observationStage}
        />
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

function SettlementNode({ node }: Readonly<{ readonly node: TraceNode }>): React.JSX.Element {
  const output = record(node.output);
  const state = record(output.state_after);
  const stateDiff = readableSettlementValue(output.state_diff);
  const cognitiveTurn = record(output.cognitive_turn);
  const cognitiveSummary = Object.fromEntries(["status", "model_mode", "error_code", "fallback_reason", "stale_reason", "timeout_reason"]
    .map((key) => [key, cognitiveTurn[key]] as const)
    .filter(([, value]) => hasContent(value)));
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
    <Evidence title="状态变化" value={stateDiff} />
    {hasContent(cognitiveSummary) ? <Evidence title="认知回合" value={cognitiveSummary} /> : null}
  </>;
}

function NodeBody({ node, preview }: Readonly<{ readonly node: TraceNode; readonly preview: PreviewResult | null }>): React.JSX.Element {
  const id = String(node.id ?? "");
  if (id === "setup") return <SetupNode node={node} />;
  if (id === "reasoning_run") return <ReasoningNode node={node} />;
  if (id === "turn_decision") return <DecisionNode node={node} />;
  if (id === "governance_delivery") return <GovernanceNode node={node} preview={preview} />;
  if (id === "settlement") return <SettlementNode node={node} />;
  return <><TraceIO node={node} omitOutput={id === "context_workspace" ? ["conversation"] : []} />{id === "context_workspace" && hasContent(record(node.output).conversation) ? <Evidence title="对话上下文" value={record(node.output).conversation} /> : null}</>;
}

function NodeRaw({ node }: Readonly<{ readonly node: TraceNode }>): React.JSX.Element {
  return hasContent(node.raw)
    ? <pre className="trace-code trace-node-raw-view">{pretty(node.raw)}</pre>
    : <div className="trace-unavailable"><span>原始记录</span><Status value="unavailable" /></div>;
}

function NodeCard({ node, open, onToggle, preview }: Readonly<{ readonly node: TraceNode; readonly open: boolean; readonly onToggle: () => void; readonly preview: PreviewResult | null }>): React.JSX.Element {
  const [rawMode, setRawMode] = useState(false);
  const toggleRaw = () => {
    if (!open) onToggle();
    setRawMode((current) => !current);
  };
  return <article className={`trace-node${open ? " is-open" : ""}`}>
    <div className="trace-node-header">
      <button aria-expanded={open} className="trace-node-trigger" onClick={onToggle} type="button">
        <span className="trace-node-number">{String(node.number ?? "")}</span>
        <span className="trace-node-title"><strong>{String(node.title ?? node.id ?? "未命名阶段")}</strong><small>{nodeMeta(node)}</small></span>
        <span className="trace-node-aside"><Status value={node.status} /><span aria-hidden="true" className="trace-node-chevron">{open ? "⌃" : "⌄"}</span></span>
      </button>
      <button aria-pressed={rawMode} className="trace-node-mode" onClick={toggleRaw} type="button">{rawMode ? "摘要" : "原始记录"}</button>
    </div>
    {open ? <div className="trace-node-body">{rawMode ? <NodeRaw node={node} /> : <NodeBody node={node} preview={preview} />}</div> : null}
  </article>;
}

function TurnInspector({ session, turn, preview, openNode, onToggle }: Readonly<{ readonly session: ElfieSession | null; readonly turn: ElfieTurn; readonly preview: PreviewResult | null; readonly openNode: string; readonly onToggle: (id: string) => void }>): React.JSX.Element {
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
      <div className="trace-turn-meta"><span>{new Date(turn.timestamp).toLocaleTimeString("zh-CN")}</span><span>{stimulus.source_domain === "embodied" ? "现场" : stimulus.source_domain === "activity" ? "Activity" : "消息"}</span><code>{turn.turn_id}</code></div>
    </section>
    <dl className="trace-stat-row"><div><dt>耗时</dt><dd>{formatDuration(turn.duration_ms)}</dd></div><div><dt>迭代</dt><dd>{iterations}</dd></div><div><dt>模型调用</dt><dd>{calls}</dd></div><div><dt>记录来源</dt><dd>{projected.source === "production_turn_record" ? "生产链路" : "未采集"}</dd></div></dl>
    <section className="trace-chain" aria-label="Turn 处理链路">{nodes.map((node) => <NodeCard key={`${turn.turn_id}:${String(node.id)}`} node={node} onToggle={() => onToggle(String(node.id))} open={openNode === String(node.id)} preview={preview} />)}</section>
  </>;
}

export function DetailPanel({ session, selectedTurn, open, initialTab, focus, previewResult, onClose }: Props): React.JSX.Element {
  const [openNode, setOpenNode] = useState(() => defaultNodeId(focus, initialTab));
  useEffect(() => { setOpenNode(defaultNodeId(focus, initialTab)); }, [focus, initialTab, selectedTurn?.turn_id]);
  if (selectedTurn === null) return <></>;
  return <aside aria-hidden={!open} className={open ? "detail-panel" : "detail-panel is-closed"}>
    <div className="detail-heading"><div><h2>Turn 检查器</h2></div><Button aria-label="收起回合详情" onClick={onClose} shape="circle" type="text">×</Button></div>
    <div className="detail-content inspector-content"><TurnInspector onToggle={(id) => setOpenNode((current) => current === id ? "" : id)} openNode={openNode} preview={previewResult} session={session} turn={selectedTurn} /></div>
  </aside>;
}
