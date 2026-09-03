import { useEffect, useState } from "react";
import { Button, Card, Descriptions, Empty, Tabs, Typography } from "antd";

import type { ElfieSession, ElfieTurn } from "./contracts";
import { detailTitle, type DetailFocus } from "./viewModel";

type PreviewResult = Readonly<{ readonly turnId: string; readonly intentId: string; readonly status: "completed" | "unsupported"; readonly reason: string }>;
type Props = Readonly<{
  readonly session: ElfieSession | null;
  readonly selectedTurn: ElfieTurn | null;
  readonly open: boolean;
  readonly initialTab: string;
  readonly focus: DetailFocus;
  readonly previewResult: PreviewResult | null;
  readonly onClose: () => void;
}>;

const tabs = ["摘要", "链路", "快照", "原始"] as const;
const emotionLabels: Readonly<Record<string, string>> = { happiness: "快乐", sadness: "悲伤", anger: "愤怒", fear: "恐惧", surprise: "惊讶", disgust: "厌恶" };

function record(value: unknown): Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value) ? Object.fromEntries(Object.entries(value)) : {}; }
function text(value: unknown): string { return typeof value === "string" ? value : JSON.stringify(value, null, 2); }
function stageValue(turn: ElfieTurn, name: string): unknown { return record(record(turn.trace).stages)[name]; }

function StageCard({ label, value, meta }: Readonly<{ label: string; value: unknown; meta: string }>): React.JSX.Element {
  return <Card className="detail-card" extra={<Typography.Text type="secondary">{meta}</Typography.Text>} size="small" title={label}>
    <Typography.Paragraph>{text(value)}</Typography.Paragraph>
  </Card>;
}

function List({ values, diff = false }: Readonly<{ values: Readonly<Record<string, unknown>>; diff?: boolean }>): React.JSX.Element {
  const entries = Object.entries(values);
  return entries.length ? <Descriptions
    className="detail-list"
    column={1}
    items={entries.map(([key, value]) => ({
      key,
      label: key,
      children: typeof value === "object" && value !== null
        ? <Typography.Paragraph className="detail-value-json" ellipsis={{ rows: 3, expandable: "collapsible", symbol: "展开" }}>{text(value)}</Typography.Paragraph>
        : <strong className={diff ? (String(value).includes("+") ? "diff-positive" : "diff-negative") : ""}>{text(value)}</strong>,
    }))}
    size="small"
  /> : <Empty description="本轮没有状态变化" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
}

function snapshot(value: unknown): Record<string, unknown> {
  const state = record(value);
  const primary = typeof state.primary_emotion === "string" ? state.primary_emotion : "";
  return { "能量": state.energy, "疲劳": state.fatigue, "睡眠": state.is_sleeping === true ? "是" : "否", "认知模式": state.cognitive_mode, "普通认知配额": state.normal_budget_available, "紧急储备": state.emergency_reserve_available, "已预留认知配额": state.reserved_cognitive_budget, "主导情绪": emotionLabels[primary] ?? primary, "注意力": state.attention_network, "自我定位": state.orientation, "自我认知": state.selfhood, "Profile 锚点": state.profile_anchor, "动作意图": state.action_intent, "恢复驱力": state.motivation, "心智整理": state.cognitive_consolidation, "认知日志": state.journal, "记忆数": state.memory_count, "活动数": state.activity_count, "活动": state.activities, "情绪全景": state.emotions };
}

function liveSummary(value: unknown): Record<string, unknown> {
  const state = snapshot(value);
  return Object.fromEntries(["能量", "疲劳", "睡眠", "认知模式", "主导情绪", "动作意图"].map((key) => [key, state[key]]));
}

function difference(value: unknown, prefix = ""): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, change] of Object.entries(record(value))) {
    const label = prefix ? `${prefix}.${key}` : key;
    const row = record(change);
    if ("before" in row && "after" in row) {
      const before = row.before;
      const after = row.after;
      const delta = typeof before === "number" && typeof after === "number" ? ` (${after - before >= 0 ? "+" : ""}${after - before})` : "";
      result[label] = `${text(before)} → ${text(after)}${delta}`;
    } else if (Object.keys(row).length) Object.assign(result, difference(row, label));
  }
  return result;
}

function Section({ title, children }: Readonly<{ title: string; children: React.ReactNode }>): React.JSX.Element {
  return <section className="detail-section"><h3>{title}</h3>{children}</section>;
}

function DecisionSection({ turn }: Readonly<{ turn: ElfieTurn }>): React.JSX.Element {
  const groups: readonly (readonly [string, readonly unknown[]])[] = [["Speech", turn.decision.speech_intents], ["Message", turn.decision.message_intents], ["Motion", turn.decision.motion_intents], ["Expression", turn.decision.expression_intents], ["Action", turn.decision.action_intents], ["Activity", turn.decision.activity_intents], ["No-op", turn.decision.noop_intents]];
  const cards = groups.flatMap(([label, intents]) => intents.map((intent) => <StageCard key={`${label}-${text(intent)}`} label={label} meta={typeof record(intent).status === "string" ? String(record(intent).status) : "pending"} value={intent} />));
  return <Section title="决策意图">{cards.length ? cards : <StageCard label="无决策计划" meta="只读" value="本轮没有持久化 typed intent" />}</Section>;
}

function ReceiptSection({ turn }: Readonly<{ turn: ElfieTurn }>): React.JSX.Element {
  const receipts = stageValue(turn, "output_receipts");
  const rows = Array.isArray(receipts) ? receipts : [];
  return <Section title="执行回执">{rows.length ? rows.map((item, index) => { const value = record(item); return <StageCard key={`${String(value.intent_id)}-${index}`} label={typeof value.intent_id === "string" ? value.intent_id : "未知 intent"} meta={typeof value.status === "string" ? value.status : "unknown"} value={record(value.error).message ?? "无错误"} />; }) : <StageCard label="无执行回执" meta="只读" value="本轮没有持久化回执" />}</Section>;
}

function ReasoningSection({ turn }: Readonly<{ turn: ElfieTurn }>): React.JSX.Element {
  const reasoning = record(stageValue(turn, "reasoning"));
  const steps = Array.isArray(reasoning.steps) ? reasoning.steps : [];
  return <Section title="思考步骤">{steps.length ? steps.map((item, index) => {
    const step = record(item);
    return <StageCard key={`${String(step.kind)}-${index}`} label={String(step.kind ?? "step")} meta={String(step.status ?? "unknown")} value={step.summary ?? step} />;
  }) : <StageCard label="无思考步骤" meta="只读" value={reasoning.status ?? "本轮未记录思考轨迹"} />}</Section>;
}

function Summary({ turn, preview }: Readonly<{ turn: ElfieTurn; preview: PreviewResult | null }>): React.JSX.Element {
  const previewCard = preview !== null && preview.turnId === turn.turn_id ? <Section title="动作回放"><StageCard label={preview.intentId} meta={preview.status === "completed" ? "已播放" : "不支持"} value={preview.reason || (preview.status === "completed" ? "Godot 已完成该动作回放" : "Godot 未支持该动作")} /></Section> : null;
  return <><Section title="本轮输入"><StageCard label="开发者刺激" meta={typeof turn.food_key === "string" ? turn.food_key : "mock"} value={turn.stimulus_bundle.message || "非文字刺激"} />{turn.used_state_injection ? <StageCard label="状态注入" meta="已永久标记" value={turn.stimulus_bundle.state_injection} /> : null}</Section><Section title="历史状态"><StageCard label="处理前" meta="state_before" value={turn.state_before} /><StageCard label="字段变化" meta="state_diff" value={turn.state_diff} /><StageCard label="处理后" meta="state_after" value={turn.state_after} /></Section><DecisionSection turn={turn} />{previewCard}<ReceiptSection turn={turn} /></>;
}

function Chain({ turn }: Readonly<{ turn: ElfieTurn }>): React.JSX.Element {
  const stages = record(record(turn.trace).stages);
  const labels: Readonly<Record<string, string>> = { state_injection: "状态注入", sleep_gate: "睡眠门控", brainstem_reflex: "脑干反射", sensory_filter: "感知过滤", thalamus_context: "丘脑上下文", reasoning: "思考步骤", decision: "注意力与决策", action_validation: "动作校验", execution: "身体执行", memory_write: "记忆写入" };
  const model = record(turn.model_call);
  return <><ReasoningSection turn={turn} /><Section title="执行阶段">{Object.entries(stages).map(([name, value]) => <StageCard key={name} label={labels[name] ?? name} meta={name} value={value} />)}</Section><Section title="模型调用"><StageCard label={model.skipped === true ? "未调用模型" : `${String(model.provider ?? "unknown")} · ${String(model.model ?? "unknown")}`} meta={typeof model.duration_ms === "number" ? `${model.duration_ms} ms` : "跳过"} value={model.skipped === true ? model.reason : model.prompt} /></Section></>;
}

export function DetailPanel({ session, selectedTurn, open, initialTab, focus, previewResult, onClose }: Props): React.JSX.Element {
  const [tab, setTab] = useState(initialTab);
  useEffect(() => { setTab(initialTab); }, [initialTab]);
  const active = selectedTurn;
  const content = active === null
    ? tab === "链路"
      ? <Section title="实时链路"><Empty description="选择时间线中的回合查看完整处理链路" image={Empty.PRESENTED_IMAGE_SIMPLE} /></Section>
      : tab === "原始"
        ? <Section title="当前状态 · 原始"><pre className="raw-block">{JSON.stringify(session?.current_state ?? {}, null, 2)}</pre></Section>
        : tab === "摘要"
          ? <Section title="实时摘要"><List values={liveSummary(session?.current_state)} /></Section>
          : <Section title="实时快照"><List values={snapshot(session?.current_state)} /></Section>
    : tab === "摘要" ? <Summary preview={previewResult} turn={active} /> : tab === "链路" ? <Chain turn={active} /> : tab === "快照" ? <><Section title="处理前"><List values={snapshot(active.state_before)} /></Section><Section title="字段变化"><List diff values={difference(active.state_diff)} /></Section><Section title="处理后"><List values={snapshot(active.state_after)} /></Section></> : <Section title="TurnRecord · 已脱敏"><pre className="raw-block">{JSON.stringify(active, null, 2)}</pre></Section>;
  const kicker = active === null ? "实时 · 未选择历史回合" : `历史回合 · ${new Date(active.timestamp).toLocaleTimeString("zh-CN")} · 只读`;
  const title = active === null ? (tab === "链路" ? "实时链路" : tab === "原始" ? "当前状态 · 原始" : "当前状态") : detailTitle(focus, tab);
  return <aside aria-hidden={!open} className={open ? "detail-panel" : "detail-panel is-closed"}>
    <div className="detail-heading">
      <div><p className="eyebrow">{kicker}</p><h2>{title}</h2></div>
      <Button aria-label="收起回合详情" onClick={onClose} shape="circle" type="text">×</Button>
    </div>
    <Tabs
      activeKey={tab}
      className="detail-tabs"
      items={tabs.map((item) => ({ key: item, label: item }))}
      onChange={setTab}
    />
    <div className="detail-content">{content}</div>
  </aside>;
}
