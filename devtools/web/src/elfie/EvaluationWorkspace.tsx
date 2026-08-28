import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Collapse,
  Descriptions,
  Drawer,
  Dropdown,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Pagination,
  Progress,
  Radio,
  Result,
  Select,
  Skeleton,
  Statistic,
  Table,
  Tabs,
  Tag,
} from "antd";
import { DownOutlined, MinusOutlined, PlusOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";

import { requestJson } from "../api/http";
import {
  evaluationBatchListSchema,
  evaluationBatchRecordSchema,
  evaluationCodeBranchesSchema,
  evaluationComparisonSchema,
  evaluationPresetsSchema,
  type ElfieListItem,
  type ElfieSession,
  type EvaluationBatchRecord,
  type EvaluationCodeBranches,
  type EvaluationComparison,
  type EvaluationPreset,
  type EvaluationRun,
  type FoodItem,
  type ReviewerSubscription,
} from "./contracts";

type Props = Readonly<{
  readonly elfies: readonly ElfieListItem[];
  readonly session: ElfieSession | null;
  readonly food: string;
  readonly foods: readonly FoodItem[];
  readonly reviewerSubscriptions?: readonly ReviewerSubscription[];
  readonly onSaveReviewerSubscription?: ((configuration: Record<string, unknown>) => Promise<ReviewerSubscription>) | undefined;
  readonly onDeleteReviewerSubscription?: ((subscriptionId: string) => Promise<void>) | undefined;
  readonly onOpenExperiment?: () => void;
  readonly onNewFood?: (onSaved: (foodKey: string) => void) => void;
  readonly onNewElfie?: (onSaved: (elfieId: string) => void) => void;
}>;

type DrawerState =
  | Readonly<{ readonly kind: "report"; readonly reportId: string }>
  | Readonly<{ readonly kind: "comparison"; readonly reportIds: readonly [string, string] }>
  | null;
type CreateMode = "single" | "paired" | null;
type ComparisonGrade = "strict" | "observational" | "incompatible";

type EvaluationSelectOption = Readonly<{
  readonly value: string;
  readonly label: React.ReactNode;
  readonly disabled?: boolean;
}>;

function EvaluationSelect({ value, onChange, options, placeholder, ariaLabel }: Readonly<{
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly options: readonly EvaluationSelectOption[];
  readonly placeholder?: string;
  readonly ariaLabel?: string;
}>): React.JSX.Element {
  return <Select aria-label={ariaLabel} className="evaluation-library-select" onChange={onChange} options={[...options]} placeholder={placeholder} popupClassName="evaluation-library-select-dropdown" popupMatchSelectWidth={false} value={value || null} />;
}

const fallbackPresets: readonly EvaluationPreset[] = [
  { key: "quick", title: "快速检查", description: "检查越权、角色锚点和关键记忆。", typical_duration: "约 3–10 分钟", scenario_count: 3, requires_godot: false },
  { key: "standard", title: "标准评测", description: "覆盖六项核心体验和关键边界。", typical_duration: "约 30–60 分钟", scenario_count: 8, requires_godot: false },
];

const statusLabels = {
  pending: "等待中", running: "运行中", completed: "已完成", partial_failed: "部分失败", failed: "失败",
} as const;
const verdictLabels: Readonly<Record<EvaluationRun["verdict"], string>> = {
  baseline: "历史开发基线",
  passed: "确定项通过",
  evidence_ready: "证据已就绪",
  failed: "发现未通过项",
  improved: "整体变好",
  observe: "没有明显变化",
  regressed: "发现退化",
  incomplete: "证据不完整",
};
const resultLabels = {
  pending: "等待中", running: "运行中", baseline: "基线", passed: "通过", evidence_ready: "待相对比较",
  failed: "未通过", improved: "变好", unchanged: "持平", regressed: "退化", incomplete: "证据不足",
} as const;
const qualityDimensions = [
  { key: "identity_continuity", label: "角色锚点连续性" },
  { key: "understanding_reasoning", label: "意图理解一致性" },
  { key: "memory_relationships", label: "关键事件记忆" },
  { key: "emotion_energy", label: "情感表达" },
  { key: "autonomy_boundaries", label: "场景适配鲁棒性" },
  { key: "commitment_reliability", label: "安全与合规" },
] as const satisfies readonly Readonly<{
  readonly key: EvaluationRun["dimensions"][number]["dimension"];
  readonly label: string;
}>[];

function formatTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

export function shortEvaluationId(value: string): string {
  const prefixes: readonly [string, string][] = [
    ["evaluation_batch_", "#E-"],
    ["evaluation_snapshot_", "#S-"],
    ["evaluation_", "#R-"],
    ["comparison-", "#C-"],
  ];
  const match = prefixes.find(([source]) => value.startsWith(source));
  return match ? `${match[1]}${value.slice(match[0].length, match[0].length + 10)}` : value.slice(0, 13);
}

export function selectActiveEvaluationRun(
  current: EvaluationRun | null,
  runs: readonly EvaluationRun[],
  suite: "quick" | "standard",
  elfieId: string,
): EvaluationRun | null {
  if (current?.elfie_id === elfieId && current.suite === suite) return current;
  return runs.find((item) => item.elfie_id === elfieId && item.suite === suite) ?? null;
}

export function comparisonGradeForReports(a: EvaluationRun, b: EvaluationRun): ComparisonGrade {
  if (a.fixture_sha256 !== b.fixture_sha256 || a.test_plan_sha256 !== b.test_plan_sha256) return "incompatible";
  const differences = Number(a.source_snapshot_sha256 !== b.source_snapshot_sha256)
    + Number(a.food_spec_sha256 !== b.food_spec_sha256);
  return differences === 1 && a.judge_spec_sha256 === b.judge_spec_sha256 ? "strict" : "observational";
}

export function nextSelectedReportIds(
  current: readonly string[],
  ids: readonly string[],
): readonly string[] | null {
  const selected = new Set(current);
  if (ids.every((id) => selected.has(id))) {
    ids.forEach((id) => selected.delete(id));
    return [...selected];
  }
  const missing = ids.filter((id) => !selected.has(id));
  if (selected.size + missing.length > 2) return null;
  missing.forEach((id) => selected.add(id));
  return [...selected];
}

export function nextSelectedEvaluationRuns(
  current: readonly EvaluationRun[],
  visible: readonly EvaluationRun[],
  ids: readonly string[],
): readonly EvaluationRun[] | null {
  const nextIds = nextSelectedReportIds(current.map((item) => item.run_id), ids);
  if (nextIds === null) return null;
  const available = new Map([...current, ...visible].map((item) => [item.run_id, item]));
  return nextIds.map((id) => available.get(id)).filter((item): item is EvaluationRun => item !== undefined);
}

function allReports(records: readonly EvaluationBatchRecord[]): readonly EvaluationRun[] {
  const result = new Map<string, EvaluationRun>();
  for (const record of records) for (const report of record.reports) result.set(report.run_id, report);
  return [...result.values()];
}

function runResult(run: EvaluationRun): string {
  if (run.status === "pending") return "等待中";
  if (run.status === "running") return `${run.completed_scenarios}/${run.total_scenarios}`;
  if (run.status === "failed") return "运行失败";
  return verdictLabels[run.verdict];
}

function runScoreResult(run: EvaluationRun): string {
  if (run.status !== "completed") return runResult(run);
  return run.overall_score === null ? verdictLabels[run.verdict] : `${formatScore(run.overall_score)}${run.grade ? ` · ${gradeLabel(run.grade)}` : ""}`;
}

function candidateDisplay(run: EvaluationRun): string {
  const food = run.food_display_name || run.food_key || "未命名粮食";
  return run.food_model ? `${food} · ${run.food_model}` : food;
}

function reportTitleDisplay(run: EvaluationRun, fallback = "未命名评测"): string {
  return run.title.trim() || fallback;
}

function sourceRevisionDisplay(run: EvaluationRun): string {
  const ref = run.source_ref || "当前分支";
  const revision = run.source_revision && run.source_revision.length > 12 ? run.source_revision.slice(0, 8) : run.source_revision;
  return revision ? `${ref} · ${revision}` : ref;
}

function foodDisplay(run: EvaluationRun): string {
  return run.food_display_name || run.food_key || "未配置粮食套餐";
}

function PairValue({ reports, value }: Readonly<{ readonly reports: readonly EvaluationRun[]; readonly value: (run: EvaluationRun) => string }>): React.JSX.Element {
  const first = reports[0];
  const second = reports[1];
  if (!first) return <span>—</span>;
  const firstValue = value(first);
  const secondValue = second ? value(second) : firstValue;
  if (!second || firstValue === secondValue) return <span>{firstValue}</span>;
  return <span className="evaluation-pair-values"><span><b>A</b>{firstValue}</span><span><b>B</b>{secondValue}</span></span>;
}

function formatScore(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(1).replace(/\.0$/, "");
}

function gradeLabel(value: EvaluationRun["grade"]): string {
  return value === "P0_FAILED" ? "P0 未通过" : value === "INCOMPLETE" ? "未完成" : value ?? "—";
}

function scoreClass(value: number | null | undefined): string {
  return value !== null && value !== undefined && value < 60 ? "danger" : "good";
}

function reportSummary(run: EvaluationRun): string {
  if (run.error) return `评测因技术错误中断：${run.error}`;
  if (run.p0_violations.length) return `发现 ${run.p0_violations.length} 项 P0 红线，需要先处理红线再判断能力变化。`;
  if (run.status !== "completed") return `已完成 ${run.completed_scenarios}/${run.total_scenarios} 个场景，当前结论仍会继续更新。`;
  return `${verdictLabels[run.verdict]}；结论来自 ${run.completed_scenarios} 个固定场景、${run.total_model_calls} 次模型调用和冻结输入证据。`;
}

function dimensionFor(run: EvaluationRun, dimension: string): EvaluationRun["dimensions"][number] | undefined {
  return run.dimensions.find((item) => item.dimension === dimension);
}

function scenarioFor(run: EvaluationRun, familyId: string): EvaluationRun["scenarios"][number] | undefined {
  return run.scenarios.find((item) => item.family_id === familyId);
}

function StatusPill({ value }: Readonly<{ readonly value: string }>): React.JSX.Element {
  const colors: Readonly<Record<string, string>> = {
    running: "processing",
    completed: "success",
    partial_failed: "warning",
    failed: "error",
    passed: "success",
    evidence_ready: "blue",
    improved: "success",
    unchanged: "default",
    regressed: "error",
    incomplete: "warning",
  };
  return <Tag className="eval-status" color={colors[value] ?? "default"}>{statusLabels[value as keyof typeof statusLabels] ?? resultLabels[value as keyof typeof resultLabels] ?? value}</Tag>;
}

function SectionHeading({ index, title, note }: Readonly<{ readonly index: string; readonly title: string; readonly note: string }>): React.JSX.Element {
  return <div className="report-section-heading"><span className="section-index">{index}</span><h3>{title}</h3><small>{note}</small></div>;
}

function EvidenceList({ items, empty = "暂无额外证据。" }: Readonly<{ readonly items: readonly string[]; readonly empty?: string }>): React.JSX.Element {
  return items.length
    ? <List className="evaluation-evidence-list" dataSource={[...items]} size="small" renderItem={(item) => <List.Item>{item}</List.Item>} />
    : <Empty description={empty} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
}

function PairSelectionCheckbox({
  label,
  reportIds,
  selected,
  onToggle,
}: Readonly<{
  readonly label: string;
  readonly reportIds: readonly string[];
  readonly selected: readonly string[];
  readonly onToggle: () => void;
}>): React.JSX.Element {
  const checked = reportIds.length > 0 && reportIds.every((id) => selected.includes(id));
  const indeterminate = !checked && reportIds.some((id) => selected.includes(id));
  return <Checkbox aria-label={label} checked={checked} indeterminate={indeterminate} onChange={onToggle} />;
}

function SingleReportView({ run }: Readonly<{ readonly run: EvaluationRun }>): React.JSX.Element {
  const completedRows = run.scenarios.filter((item) => !["pending", "running"].includes(item.status));
  const evidenceCount = run.scenarios.reduce((count, item) => count + item.evidence.length, 0)
    + run.dimensions.reduce((count, item) => count + item.evidence.length, 0);
  const scenarioItems = run.scenarios.map((item) => ({
    key: item.family_id,
    label: <div className="scenario-collapse-label"><span>{item.title}</span><StatusPill value={item.status} /><small>{(item.latency_ms / 1000).toFixed(1)}s</small></div>,
    children: <div className="scenario-collapse-body"><p>{item.purpose}</p>{item.candidate_outputs.length ? <pre>{item.candidate_outputs.join("\n")}</pre> : <Empty description="没有公开文字输出" image={Empty.PRESENTED_IMAGE_SIMPLE} />}<EvidenceList items={item.evidence} />{item.error ? <Alert description={`技术错误：${item.error}`} showIcon type="error" /> : null}</div>,
  }));
  const disclosureItems = [
    {
      key: "evidence",
      label: "证据与关键事件",
      extra: `${evidenceCount} 项`,
      children: <List dataSource={[...run.scenarios]} renderItem={(item) => <List.Item><List.Item.Meta description={<EvidenceList items={item.evidence} />} title={item.title} /></List.Item>} />,
    },
    {
      key: "snapshots",
      label: "冻结快照与版本证据",
      extra: "精灵、代码、粮食、计划与评审规格",
      children: <Descriptions column={2} items={[
        { key: "fixture", label: "精灵快照", children: <code>{run.fixture_sha256}</code> },
        { key: "source", label: "代码内容", children: <code>{run.source_snapshot_sha256}</code> },
        { key: "candidate", label: "候选规格", children: <code>{run.candidate_spec_sha256}</code> },
        { key: "food", label: "粮食规格", children: <code>{run.food_spec_sha256}</code> },
        { key: "plan", label: "测试计划", children: <code>{run.test_plan_sha256}</code> },
        { key: "judge", label: "评审规格", children: <code>{run.judge_spec_sha256}</code> },
      ]} size="small" />,
    },
    {
      key: "models",
      label: "模型调用与资源",
      extra: `${run.total_model_calls} 次 · ${(run.total_latency_ms / 1000).toFixed(1)}s`,
      children: <Descriptions column={2} items={[
        { key: "candidate-model", label: "候选模型", children: run.food_model },
        { key: "judge-model", label: "评审模型", children: run.judge_model },
        { key: "food", label: "候选粮食配置", children: run.food_display_name || run.food_key },
        { key: "judge-subscription", label: "评审订阅", children: run.judge_subscription_id || "—" },
      ]} size="small" />,
    },
    {
      key: "warnings",
      label: "错误与警告",
      extra: `${run.error ? 1 : 0} 错误 · ${run.warnings.length} 警告`,
      children: run.error || run.warnings.length
        ? <div className="evaluation-alert-stack">{run.error ? <Alert description={run.error} showIcon type="error" /> : null}{run.warnings.map((item) => <Alert description={item} key={item} showIcon type="warning" />)}</div>
        : <Result status="success" subTitle="没有记录到错误或警告" title="运行记录正常" />,
    },
    {
      key: "raw",
      label: "原始回执与断言详情",
      extra: "完整冻结报告",
      children: <pre>{JSON.stringify(run, null, 2)}</pre>,
    },
  ];
  return <div className="report-detail-body">
    <section className="report-decision-band">
      <Card className="report-score-card" size="small"><span className="report-kicker">总得分</span><strong className={scoreClass(run.overall_score)}>{formatScore(run.overall_score)}<small> /100</small></strong><span className="report-grade">等级 {gradeLabel(run.grade)}</span></Card>
      <Card size="small"><Statistic title="P0 红线" value={run.p0_violations.length ? `${run.p0_violations.length} 项` : "全部通过"} /></Card>
      <Card size="small"><Statistic title="评分覆盖" value={`${Math.round(run.score_coverage * 100)}%`} /></Card>
      <Card className="report-summary-copy" size="small" title="评测结论"><p>{reportSummary(run)}</p></Card>
    </section>
    <section className="report-fact-row snapshot-row">
      <SectionHeading index="01" note="精灵状态与记忆已冻结" title="评测对象快照" />
      <Descriptions bordered column={4} items={[
        { key: "elfie", label: "测试精灵", children: `${run.elfie_name || run.elfie_id} · ${run.elfie_species_id || "未知物种"}` },
        { key: "snapshot", label: "快照 ID / 指纹", children: <span className="fact-stack"><span>{run.fixture_snapshot_id ? shortEvaluationId(run.fixture_snapshot_id) : "历史报告未冻结"}</span><code>{run.fixture_sha256.slice(0, 12)}</code></span> },
        { key: "captured", label: "冻结时间", children: formatTime(run.fixture_captured_at) },
        { key: "memory", label: "历史与记忆", children: `${run.fixture_memory_count} 记忆 · ${run.fixture_activity_count} 活动 · ${run.fixture_journal_count} 日志` },
      ]} layout="vertical" size="small" />
    </section>
    <section className="report-fact-row">
      <SectionHeading index="02" note="代码 / 粮食 / 模型" title="候选方案" />
      <Descriptions bordered column={4} items={[
        { key: "code", label: "代码版本", children: <span className="fact-stack"><span>{run.source_ref || run.candidate_label}</span><small>{run.candidate_label}</small><code>{run.source_snapshot_sha256.slice(0, 12)}</code></span> },
        { key: "food", label: "粮食配置（Food）", children: <span className="fact-stack"><span>{run.food_display_name || run.food_key}</span><code>{run.food_spec_sha256.slice(0, 12)}</code></span> },
        { key: "model", label: "实际模型", children: run.food_model },
        { key: "judge", label: "评审模型", children: run.judge_model },
      ]} layout="vertical" size="small" />
    </section>
    <section className="report-fact-row">
      <SectionHeading index="03" note="样本集与执行规则" title="测试计划" />
      <Descriptions bordered column={3} items={[
        { key: "title", label: "评测方案", children: run.test_plan_title },
        { key: "scenarios", label: "场景数量", children: `${run.total_scenarios} 个场景` },
        { key: "fingerprint", label: "计划指纹", children: <code>{run.test_plan_sha256.slice(0, 8)}</code> },
        { key: "rules", label: "执行规则", span: 3, children: <div className="test-plan-tags">{run.execution_rules.map((item) => <Tag key={item}>{item}</Tag>)}</div> },
      ]} size="small" />
    </section>
    <section className="report-results">
      <SectionHeading index="04" note={`${run.completed_scenarios}/${run.total_scenarios} 场景 · ${evidenceCount} 条证据`} title="结果与证据" />
      <div className="report-result-grid">
        <Card className="dimension-panel" size="small" title="六大能力维度"><List dataSource={[...qualityDimensions]} renderItem={(dimension) => { const item = dimensionFor(run, dimension.key); const score = item?.score ?? null; return <List.Item><div className="dimension-report-line"><span>{dimension.label}</span><div className="dimension-score-track">{score !== null ? <Progress percent={score} showInfo={false} size="small" strokeColor="#287e61" trailColor="#dfe8e3" /> : <Progress percent={0} showInfo={false} size="small" strokeColor="#c7d3cd" trailColor="#eef2f0" />}</div><strong className={scoreClass(score)}>{formatScore(score)}</strong></div></List.Item>; }} size="small" /></Card>
        <Card className="scenario-panel" size="small" title={`场景结果（${completedRows.length}/${run.total_scenarios}）`}><Collapse items={scenarioItems} size="small" /></Card>
        <Card className="p0-panel" size="small" title="红线检查（P0）">{run.p0_violations.length ? <List dataSource={[...run.p0_violations]} renderItem={(item) => <List.Item><List.Item.Meta description={`${item.evidence.length} 条证据`} title={<span className="danger">{item.code} · {item.title}</span>} /></List.Item>} size="small" /> : <Result status="success" subTitle="已完成场景未发现 P0 红线违规" title="全部通过" />}</Card>
      </div>
    </section>
    <Collapse className="report-disclosures" items={disclosureItems} />
    {run.error || run.warnings.length ? <Alert className="report-warnings" description={<div>{run.error ? <p>{run.error}</p> : null}{run.warnings.map((item) => <p key={item}>{item}</p>)}</div>} message="运行提醒" showIcon type={run.error ? "error" : "warning"} /> : null}
  </div>;
}

function ComparisonOverview({ comparison, a, b }: Readonly<{ readonly comparison: EvaluationComparison; readonly a: EvaluationRun; readonly b: EvaluationRun }>): React.JSX.Element {
  const improved = comparison.scenarios.filter((item) => item.status === "improved").length;
  const unchanged = comparison.scenarios.filter((item) => item.status === "unchanged").length;
  const regressed = comparison.scenarios.filter((item) => item.status === "regressed").length;
  const strictEvidenceReady = comparison.grade === "strict" && comparison.verdict !== "incomplete";
  const gradeCopy = comparison.grade === "strict"
    ? strictEvidenceReady
      ? `严格配对，可归因 · 唯一变量：${comparison.comparison_variable === "food" ? "粮食" : "代码"}`
      : "严格配对条件 · 暂无胜负结论"
    : comparison.grade === "observational"
      ? comparison.differing_fields.length === 0
        ? "重复运行观察 · 候选配置相同"
        : "多变量观察 · 可以看变化，不归因"
      : "测试条件不兼容 · 仅并排查看";
  const improvedItems = comparison.scenarios.filter((item) => item.status === "improved");
  const regressedItems = comparison.scenarios.filter((item) => item.status === "regressed");
  const scenarioItems = comparison.scenarios.map((item) => {
    const left = scenarioFor(a, item.family_id);
    const right = scenarioFor(b, item.family_id);
    return {
      key: item.family_id,
      label: <div className="comparison-collapse-label"><span>{item.title}</span><small>A · {left ? resultLabels[left.status] : "—"}</small><small>B · {right ? resultLabels[right.status] : "—"}</small><StatusPill value={item.status} /><small>{item.evidence.length} 条</small></div>,
      children: <div><div className="ab-output"><Card size="small" title="报告 A"><pre>{item.report_a_outputs.join("\n") || "没有公开文字输出"}</pre></Card><Card size="small" title="报告 B"><pre>{item.report_b_outputs.join("\n") || "没有公开文字输出"}</pre></Card></div><EvidenceList items={item.evidence} /></div>,
    };
  });
  const disclosureItems = [
    {
      key: "scenario-evidence",
      label: "场景证据",
      extra: `${comparison.scenarios.reduce((count, item) => count + item.evidence.length, 0)} 条`,
      children: <List dataSource={[...comparison.scenarios]} renderItem={(item) => <List.Item><List.Item.Meta description={<EvidenceList items={item.evidence} />} title={item.title} /></List.Item>} />,
    },
    { key: "raw-scenarios", label: "原始证据（场景级）", extra: "A/B 输出与冻结摘要", children: <pre>{JSON.stringify(comparison.scenarios, null, 2)}</pre> },
    {
      key: "resources",
      label: "模型调用与资源",
      extra: `${a.total_model_calls + b.total_model_calls} 次 · ${((a.total_latency_ms + b.total_latency_ms) / 1000).toFixed(1)}s`,
      children: <Descriptions column={2} items={[
        { key: "a-calls", label: "A 调用", children: `${a.total_model_calls} 次 · ${(a.total_latency_ms / 1000).toFixed(1)}s` },
        { key: "b-calls", label: "B 调用", children: `${b.total_model_calls} 次 · ${(b.total_latency_ms / 1000).toFixed(1)}s` },
        { key: "a-model", label: "A 模型", children: a.food_model },
        { key: "b-model", label: "B 模型", children: b.food_model },
      ]} size="small" />,
    },
    {
      key: "warnings",
      label: "错误与警告",
      extra: `${Number(Boolean(a.error)) + Number(Boolean(b.error))} 错误 · ${comparison.warnings.length} 警告`,
      children: a.error || b.error || comparison.warnings.length
        ? <div className="evaluation-alert-stack">{a.error ? <Alert description={`A：${a.error}`} showIcon type="error" /> : null}{b.error ? <Alert description={`B：${b.error}`} showIcon type="error" /> : null}{comparison.warnings.map((item) => <Alert description={item} key={item} showIcon type="warning" />)}</div>
        : <Result status="success" subTitle="没有记录到错误或警告" title="对比运行正常" />,
    },
    { key: "raw", label: "原始回执与断言详情", extra: "完整对比产物", children: <pre>{JSON.stringify(comparison, null, 2)}</pre> },
  ];
  return <div className="comparison-overview">
    <section className="comparison-snapshot-band">
      <Card size="small" title={<span><Tag color="green">A</Tag>{a.elfie_name || a.elfie_id}</span>}><Descriptions column={1} items={[{ key: "id", label: "快照 ID", children: a.fixture_snapshot_id ? shortEvaluationId(a.fixture_snapshot_id) : "未冻结" }, { key: "time", label: "冻结时间", children: formatTime(a.fixture_captured_at) }]} size="small" /></Card>
      <Card className="shared-plan" size="small" title="共同测试计划"><strong>{a.test_plan_title} · {a.total_scenarios} 场景</strong><code>{a.test_plan_sha256.slice(0, 8)}</code></Card>
      <Card size="small" title={<span><Tag color="blue">B</Tag>{b.elfie_name || b.elfie_id}</span>}><Descriptions column={1} items={[{ key: "id", label: "快照 ID", children: b.fixture_snapshot_id ? shortEvaluationId(b.fixture_snapshot_id) : "未冻结" }, { key: "time", label: "冻结时间", children: formatTime(b.fixture_captured_at) }]} size="small" /></Card>
    </section>
    <Card className={`comparison-grade ${comparison.grade}`} size="small" title="配对条件"><Alert description={strictEvidenceReady ? "精灵快照、测试计划与评审配置完全一致。" : comparison.warnings[0] ?? "当前条件只支持并排观察。"} message={gradeCopy} showIcon type={comparison.grade === "strict" ? "success" : comparison.grade === "observational" ? "warning" : "error"} /><Descriptions column={3} items={[{ key: "a", label: "A 候选", children: <span className="fact-stack"><span>{candidateDisplay(a)}</span><small>{a.candidate_label}</small></span> }, { key: "variable", label: "唯一变量", children: comparison.comparison_variable === "food" ? "粮食配置（Food）" : comparison.comparison_variable === "code" ? "代码版本" : "多变量观察" }, { key: "b", label: "B 候选", children: <span className="fact-stack"><span>{candidateDisplay(b)}</span><small>{b.candidate_label}</small></span> }]} size="small" /></Card>
    <section className="comparison-conclusion">
      <Card size="small"><Statistic title="整体变化" value={comparison.overall_delta === null ? verdictLabels[comparison.verdict] : `${comparison.overall_delta >= 0 ? "+" : ""}${formatScore(comparison.overall_delta)}`} suffix={comparison.overall_delta === null ? undefined : "分"} /></Card>
      <Card size="small"><Statistic title="报告 A 总分" value={formatScore(comparison.report_a_score ?? a.overall_score)} suffix="/100" /></Card>
      <Card size="small"><Statistic title="报告 B 总分" value={formatScore(comparison.report_b_score ?? b.overall_score)} suffix="/100" /></Card>
      <Card size="small"><Statistic className="good" title="变好" suffix="项" value={improved} /></Card>
      <Card size="small"><Statistic title="持平" suffix="项" value={unchanged} /></Card>
      <Card size="small"><Statistic className={regressed ? "danger" : ""} title="退化" suffix="项" value={regressed} /></Card>
    </section>
    <div className="comparison-grid">
      <Card className="dimension-comparison" size="small" title="能力维度对比（6 维度）"><List dataSource={[...qualityDimensions]} renderItem={(dimension) => { const item = comparison.dimensions.find((entry) => entry.dimension === dimension.key); const left = dimensionFor(a, dimension.key); const right = dimensionFor(b, dimension.key); const leftScore = item?.baseline_score ?? left?.score ?? null; const rightScore = item?.candidate_score ?? right?.score ?? null; const delta = item?.delta ?? (leftScore !== null && rightScore !== null ? rightScore - leftScore : null); return <List.Item><div className="dimension-comparison-line"><div><strong>{dimension.label}</strong>{item ? <StatusPill value={item.status} /> : <Tag>无可比证据</Tag>}</div><div className="dimension-comparison-scores"><span>A {formatScore(leftScore)}</span><span>B {formatScore(rightScore)}</span><strong className={scoreClass(delta)}>{delta === null ? "—" : `${delta >= 0 ? "+" : ""}${formatScore(delta)}`}</strong></div></div></List.Item>; }} size="small" /></Card>
      <Card className="scenario-comparison" size="small" title={`场景差异对比（${comparison.scenarios.length} 场景）`}><Collapse items={scenarioItems} size="small" /></Card>
      <Card className="comparison-auto-summary" size="small" title="AI 总结"><Descriptions column={1} items={[{ key: "better", label: "改好了什么", children: improvedItems.length ? <EvidenceList items={improvedItems.map((item) => item.title)} /> : "没有场景形成明确提升证据。" }, { key: "worse", label: "变坏了什么", children: regressedItems.length ? <EvidenceList items={regressedItems.map((item) => item.title)} /> : "没有场景形成明确退化证据。" }, { key: "next", label: "建议下一步", children: comparison.warnings[0] ?? (strictEvidenceReady ? "复核关键证据后，可将严格配对结论用于版本决策。" : "补齐严格配对条件，再判断变化能否归因。") }]} size="small" /></Card>
    </div>
    <section className="comparison-p0"><Card size="small" title="P0 红线 · 报告 A">{comparison.p0_report_a.length ? <List dataSource={[...comparison.p0_report_a]} renderItem={(item) => <List.Item><span className="danger">{item.code} · {item.title}</span></List.Item>} size="small" /> : <Result status="success" subTitle="报告 A 未发现红线违规" title="全部通过" />}</Card><Card size="small" title="P0 红线 · 报告 B">{comparison.p0_report_b.length ? <List dataSource={[...comparison.p0_report_b]} renderItem={(item) => <List.Item><span className="danger">{item.code} · {item.title}</span></List.Item>} size="small" /> : <Result status="success" subTitle="报告 B 未发现红线违规" title="全部通过" />}</Card></section>
    <Collapse className="comparison-disclosures" items={disclosureItems} />
    {comparison.warnings.length ? <Alert className="comparison-notes" description={<EvidenceList items={comparison.warnings} />} message="结论边界" showIcon type="warning" /> : null}
  </div>;
}

function EvaluationDrawer({ state, reports, comparison, comparisonLoading, onClose }: Readonly<{ readonly state: Exclude<DrawerState, null>; readonly reports: readonly EvaluationRun[]; readonly comparison: EvaluationComparison | null; readonly comparisonLoading: boolean; readonly onClose: () => void }>): React.JSX.Element {
  const [tab, setTab] = useState<"overview" | "a" | "b">(state.kind === "comparison" ? "overview" : "a");
  const report = state.kind === "report" ? reports.find((item) => item.run_id === state.reportId) ?? null : null;
  const pair = state.kind === "comparison" ? state.reportIds.map((id) => reports.find((item) => item.run_id === id) ?? null) : [];
  useEffect(() => { setTab(state.kind === "comparison" ? "overview" : "a"); }, [state]);
  if (state.kind === "report") {
    if (!report) return <Drawer aria-label="评测报告详情" className="evaluation-library-drawer-panel" mask maskClosable onClose={onClose} open placement="right" rootClassName="evaluation-library-drawer" title="报告详情" width="70vw"><Result status="warning" subTitle="可能已被删除或当前列表尚未加载该报告" title="报告不存在" /></Drawer>;
    return <Drawer aria-label="评测报告详情" className="evaluation-library-drawer-panel" extra={<div className="evaluation-drawer-extra"><span>{report.elfie_name || report.elfie_id}</span><span>{formatTime(report.completed_at ?? report.created_at)}</span><StatusPill value={report.status} /></div>} mask maskClosable onClose={onClose} open placement="right" rootClassName="evaluation-library-drawer" title={<div className="evaluation-drawer-title"><h2>报告详情</h2><code>{shortEvaluationId(report.run_id)}</code></div>} width="70vw">
      <SingleReportView run={report} />
    </Drawer>;
  }
  const a = pair[0]; const b = pair[1];
  return <Drawer aria-label="评测报告对比" className="evaluation-library-drawer-panel" mask maskClosable onClose={onClose} open placement="right" rootClassName="evaluation-library-drawer" title={<div className="evaluation-drawer-title"><h2>报告对比</h2>{comparison?.batch_id ? <code>{shortEvaluationId(comparison.batch_id)}</code> : null}</div>} width="70vw">
    <Tabs activeKey={tab} aria-label="对比报告标签" className="drawer-tabs" items={[{ key: "overview", label: "对比总览" }, { key: "a", label: "报告 A" }, { key: "b", label: "报告 B" }]} onChange={(value) => setTab(value as "overview" | "a" | "b")} />
    {a && b ? tab === "overview" ? comparisonLoading ? <div className="drawer-loading"><Skeleton active paragraph={{ rows: 8 }} title /></div> : comparison ? <ComparisonOverview a={a} b={b} comparison={comparison} /> : <Result status="error" subTitle="请关闭抽屉后重新选择两份报告" title="无法生成对比证据" /> : <SingleReportView run={tab === "a" ? a : b} /> : <Result status="warning" subTitle="对比必须包含完整的报告 A 与报告 B" title="报告数据不完整" />}
  </Drawer>;
}

function CreateEvaluationModal({ mode, elfies, foods, reviewerSubscriptions = [], onSaveReviewerSubscription, branches, presets, defaultElfieId, defaultFood, onClose, onCreated, onNewFood, onNewElfie }: Readonly<{ readonly mode: Exclude<CreateMode, null>; readonly elfies: readonly ElfieListItem[]; readonly foods: readonly FoodItem[]; readonly reviewerSubscriptions?: readonly ReviewerSubscription[]; readonly onSaveReviewerSubscription?: ((configuration: Record<string, unknown>) => Promise<ReviewerSubscription>) | undefined; readonly onDeleteReviewerSubscription?: ((subscriptionId: string) => Promise<void>) | undefined; readonly branches: EvaluationCodeBranches; readonly presets: readonly EvaluationPreset[]; readonly defaultElfieId: string; readonly defaultFood: string; readonly onClose: () => void; readonly onCreated: (record: EvaluationBatchRecord) => void; readonly onNewFood: ((onSaved: (foodKey: string) => void) => void) | undefined; readonly onNewElfie: ((onSaved: (elfieId: string) => void) => void) | undefined }>): React.JSX.Element {
  const readyFoods = useMemo(() => foods.filter((item) => item.ready_for_attempt), [foods]);
  const branchOptions = useMemo(
    () => branches.items.length ? branches.items : [{ name: branches.current_ref || "HEAD", is_current: true }],
    [branches.current_ref, branches.items],
  );
  const [title, setTitle] = useState("");
  const [elfieId, setElfieId] = useState(defaultElfieId || elfies[0]?.elfie_id || "");
  const [suite, setSuite] = useState<"quick" | "standard">("quick");
  const [axis, setAxis] = useState<"food" | "code">("food");
  const [foodA, setFoodA] = useState(defaultFood || readyFoods[0]?.key || "");
  const [foodB, setFoodB] = useState(readyFoods.find((item) => item.key !== (defaultFood || readyFoods[0]?.key))?.key ?? defaultFood ?? "");
  const defaultReviewer = reviewerSubscriptions[0];
  const [judge, setJudge] = useState(defaultReviewer?.id || "");
  const [judgeModel, setJudgeModel] = useState(defaultReviewer?.models[0] || "");
  const [reviewerInlineOpen, setReviewerInlineOpen] = useState(false);
  const [reviewerName, setReviewerName] = useState("");
  const [reviewerApiBase, setReviewerApiBase] = useState("");
  const [reviewerApiKey, setReviewerApiKey] = useState("");
  const [reviewerModels, setReviewerModels] = useState("");
  const [reviewerSaving, setReviewerSaving] = useState(false);
  const [reviewerError, setReviewerError] = useState("");
  const [codeA, setCodeA] = useState(branches.current_ref || branchOptions[0]?.name || "");
  const [codeB, setCodeB] = useState(branchOptions.find((item) => item.name !== (branches.current_ref || branchOptions[0]?.name))?.name ?? branchOptions[0]?.name ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!foodB || (axis === "food" && foodB === foodA)) setFoodB(readyFoods.find((item) => item.key !== foodA)?.key ?? foodA);
    const selectedReviewer = reviewerSubscriptions.find((item) => item.id === judge);
    if (!selectedReviewer) { const next = reviewerSubscriptions[0]; setJudge(next?.id || ""); setJudgeModel(next?.models[0] || ""); }
    else if (!selectedReviewer.models.includes(judgeModel)) setJudgeModel(selectedReviewer.models[0] || "");
  }, [axis, defaultFood, foodA, foodB, judge, reviewerSubscriptions, judgeModel]);
  useEffect(() => {
    const current = branches.current_ref || branchOptions[0]?.name || "";
    if (!codeA) setCodeA(current);
    if (!codeB || codeB === codeA) setCodeB(branchOptions.find((item) => item.name !== current)?.name ?? current);
  }, [branches.current_ref, branchOptions, codeA, codeB]);
  async function submit(): Promise<void> {
    setSubmitting(true); setError("");
    try {
      const common = { elfie_id: elfieId, suite, judge_subscription_id: judge, judge_model: judgeModel, title: title.trim(), purpose: title.trim() };
      const body = mode === "single"
        ? { ...common, food_key: foodA }
        : axis === "food"
          ? { ...common, comparison_variable: axis, food_key_a: foodA, food_key_b: foodB }
          : { ...common, comparison_variable: axis, food_key_b: foodB, code_ref_a: codeA, code_ref_b: codeB };
      const endpoint = mode === "single" ? "evaluations/batches/single" : "evaluations/batches/paired";
      const created = await requestJson(endpoint, evaluationBatchRecordSchema, { method: "post", json: body, timeout: 30_000 });
      onCreated(created);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法新建评测"); setSubmitting(false); }
  }
  const selectedPreset = presets.find((item) => item.key === suite) ?? presets[0];
  const codePairAvailable = branchOptions.length > 1;
  const valid = Boolean(title.trim() && elfieId && judgeModel && (mode === "single" ? foodA : axis === "food" ? foodA && foodB && foodA !== foodB : foodB && codePairAvailable && codeA && codeB && codeA !== codeB));
  const formId = `evaluation-create-${mode}-form`;
  function selectFood(value: string, setter: (value: string) => void): void {
    if (value === "__manage_food__") {
      onNewFood?.(setter);
      return;
    }
    setter(value);
  }
  function selectElfie(value: string): void {
    if (value === "__manage_elfie__") {
      onNewElfie?.(setElfieId);
      return;
    }
    setElfieId(value);
  }
  function selectReviewerOption(value: string): void {
    if (value === "__new_reviewer_subscription__") {
      setReviewerName(""); setReviewerApiBase(""); setReviewerApiKey(""); setReviewerModels(""); setReviewerError(""); setReviewerInlineOpen(true);
      return;
    }
    const separator = value.indexOf("::");
    if (separator < 1) return;
    setJudge(value.slice(0, separator)); setJudgeModel(value.slice(separator + 2)); setReviewerInlineOpen(false);
  }
  async function saveInlineReviewer(): Promise<void> {
    if (!onSaveReviewerSubscription) return;
    setReviewerSaving(true); setReviewerError("");
    try {
      const saved = await onSaveReviewerSubscription({
        display_name: reviewerName.trim(), api_base: reviewerApiBase.trim(), api_key: reviewerApiKey.trim() || undefined,
        models: reviewerModels.split(/[\n,]/).map((item) => item.trim()).filter(Boolean),
      });
      setJudge(saved.id); setJudgeModel(saved.models[0] ?? ""); setReviewerInlineOpen(false);
    } catch (reason) { setReviewerError(reason instanceof Error ? reason.message : "评审订阅验证失败"); }
    finally { setReviewerSaving(false); }
  }
  const foodOptions: readonly EvaluationSelectOption[] = [{ value: "__empty_food__", label: "选择粮食配置", disabled: true }, ...readyFoods.map((item) => ({ value: item.key, label: `${item.display_name} · ${item.model}` })), { value: "__manage_food__", label: "管理 / 新增粮食…" }];
  const elfieOptions: readonly EvaluationSelectOption[] = [{ value: "__empty_elfie__", label: "选择测试精灵", disabled: true }, ...elfies.map((item) => ({ value: item.elfie_id, label: `${item.name} · ${item.species_id === "dog" ? "小狗" : "狐狸"}` })), { value: "__manage_elfie__", label: "管理 / 新建测试精灵…" }];
  const branchSelectOptions: readonly EvaluationSelectOption[] = branchOptions.map((item) => ({ value: item.name, label: `${item.name}${item.is_current ? " · 当前分支" : ""}` }));
  const presetOptions: readonly EvaluationSelectOption[] = presets.map((item) => ({ value: item.key, label: `${item.title} · ${item.scenario_count} 个场景` }));
  const reviewerOptions: readonly EvaluationSelectOption[] = [
    ...reviewerSubscriptions.flatMap((item) => item.models.map((model) => ({ value: `${item.id}::${model}`, label: `${item.display_name} · ${model}` }))),
    { value: "__new_reviewer_subscription__", label: "＋ 新增远程评审订阅" },
  ];
  const reviewerSelectionValue = judge && judgeModel ? `${judge}::${judgeModel}` : "";
  const currentBranchLabel = branches.current_ref || "当前分支";
  return <><Modal centered className="evaluation-library-modal" footer={[<Button key="cancel" onClick={onClose}>取消</Button>, <Button disabled={!valid} form={formId} htmlType="submit" key="submit" loading={submitting} type="primary">{mode === "single" ? "创建并运行" : "创建配对并运行"}</Button>]} onCancel={onClose} open rootClassName="evaluation-library-modal-root" title={mode === "single" ? "新建单次评测" : "新建配对评测"} width={780} zIndex={1100}>
    <Form className="evaluation-create-form" id={formId} layout="vertical" onFinish={() => { void submit(); }}>
      <Form.Item label="评测标题" required><Input autoFocus maxLength={80} onChange={(event) => setTitle(event.target.value)} placeholder="例如：角色记忆优化" value={title} /></Form.Item>
      {mode === "paired" ? <Form.Item className="axis-picker" extra={axis === "food" ? "同一代码，运行两套粮食配置" : "同一粮食配置，运行两个代码分支"} label="只改变哪一个变量？"><Radio.Group buttonStyle="solid" onChange={(event) => setAxis(event.target.value as "food" | "code")} optionType="button" options={[{ label: "粮食配置对比", value: "food" }, { label: "代码对比", value: "code" }]} value={axis} /></Form.Item> : null}
      <div className="ordered-form">
        <Form.Item label="测试精灵" required><EvaluationSelect onChange={selectElfie} options={elfieOptions} placeholder="选择测试精灵" value={elfieId} /></Form.Item>
        {mode === "paired" && axis === "food" ? <div className="ordered-dual-row"><Form.Item label="粮食配置 A" required><EvaluationSelect onChange={(value) => selectFood(value, setFoodA)} options={foodOptions} placeholder="选择粮食配置" value={foodA} /></Form.Item><Form.Item label="粮食配置 B" required><EvaluationSelect onChange={(value) => selectFood(value, setFoodB)} options={foodOptions} placeholder="选择粮食配置" value={foodB} /></Form.Item></div> : <Form.Item label={mode === "single" ? "候选粮食配置" : "粮食配置"} required><EvaluationSelect onChange={(value) => selectFood(value, mode === "single" ? setFoodA : setFoodB)} options={foodOptions} placeholder="选择粮食配置" value={mode === "single" ? foodA : foodB} /></Form.Item>}
        {mode === "paired" && axis === "code" ? <div className="ordered-dual-row"><Form.Item label="代码 A" required><EvaluationSelect onChange={setCodeA} options={branchSelectOptions} value={codeA} /></Form.Item><Form.Item label="代码 B" required><EvaluationSelect onChange={setCodeB} options={branchSelectOptions} value={codeB} /></Form.Item></div> : <Card className="read-only-field" size="small" title="代码"><strong>{currentBranchLabel} · 自动使用最新代码</strong></Card>}
        <Form.Item extra={selectedPreset?.description ?? "样本集与执行规则将随方案一起冻结。"} label="评测方案" required><EvaluationSelect onChange={(value) => setSuite(value as "quick" | "standard")} options={presetOptions} value={suite} /></Form.Item>
        <Form.Item label="评审模型" required><Select aria-label="评审模型" className="evaluation-library-select" onChange={selectReviewerOption} options={[...reviewerOptions]} placeholder="选择远程评审模型或新增订阅" value={reviewerSelectionValue || null} /></Form.Item>
        {reviewerInlineOpen ? <Card className="reviewer-inline-subscription" size="small" title="新增远程评审订阅"><Form layout="vertical" onFinish={() => { void saveInlineReviewer(); }}><div className="reviewer-inline-grid"><Form.Item label="订阅名称" required><Input onChange={(event) => setReviewerName(event.target.value)} placeholder="例如：火山评审" value={reviewerName} /></Form.Item><Form.Item label="API URL" required><Input onChange={(event) => setReviewerApiBase(event.target.value)} placeholder="https://api.example.com/v1" value={reviewerApiBase} /></Form.Item><Form.Item label="API Key"><Input.Password onChange={(event) => setReviewerApiKey(event.target.value)} placeholder="可留空" value={reviewerApiKey} /></Form.Item><Form.Item label="模型 ID 列表" required><Input.TextArea onChange={(event) => setReviewerModels(event.target.value)} placeholder="每行或逗号一个" rows={2} value={reviewerModels} /></Form.Item></div>{reviewerError ? <Alert description={reviewerError} showIcon type="error" /> : null}<div className="reviewer-inline-actions"><Button onClick={() => { setReviewerInlineOpen(false); setReviewerError(""); }}>取消</Button><Button htmlType="submit" loading={reviewerSaving} type="primary">验证并保存</Button></div></Form></Card> : null}
      </div>
      {!reviewerSubscriptions.length ? <Alert message="暂无远程评审模型，请在下拉框中新增订阅" showIcon type="warning" /> : null}
      <Card className="creation-summary" size="small" title="运行前确认"><p>{title.trim() || "未填写标题"}；{selectedPreset?.title ?? suite} · {selectedPreset?.scenario_count ?? 0} 个固定场景；每个候选从同一份精灵快照开始。</p>{mode === "paired" && axis === "code" && !codePairAvailable ? <Alert description="请在包含代码仓库的开发环境中选择两个分支。" message="当前运行环境没有发现第二个 Git 分支" showIcon type="error" /> : null}{mode === "paired" && axis === "code" && codePairAvailable && codeA === codeB ? <Alert description="请选择两个不同的代码分支。" showIcon type="error" /> : null}{!readyFoods.length ? <Alert description="请在粮食下拉框末项选择“管理 / 新增粮食…”。" message="还没有可运行粮食" showIcon type="error" /> : null}{error ? <Alert description={error} showIcon type="error" /> : null}</Card>
    </Form>
  </Modal></>;
}

type EvaluationTableRow = Readonly<{
  readonly key: string;
  readonly record: EvaluationBatchRecord;
  readonly pair: boolean;
  readonly child: boolean;
  readonly report?: EvaluationRun;
  readonly reportIndex?: number;
}>;

function EvaluationReportTable({ records, expanded, selected, onToggleExpanded, onToggleSelected, onOpenComparison, onOpenReport }: Readonly<{
  readonly records: readonly EvaluationBatchRecord[];
  readonly expanded: ReadonlySet<string>;
  readonly selected: readonly string[];
  readonly onToggleExpanded: (batchId: string) => void;
  readonly onToggleSelected: (ids: readonly string[]) => void;
  readonly onOpenComparison: (ids: readonly string[]) => void;
  readonly onOpenReport: (reportId: string) => void;
}>): React.JSX.Element {
  const rows = useMemo<readonly EvaluationTableRow[]>(() => records.flatMap((record) => {
    if (record.batch.kind === "paired") {
      const parent: EvaluationTableRow = { key: record.batch.batch_id, record, pair: true, child: false };
      if (!expanded.has(record.batch.batch_id)) return [parent];
      return [parent, ...record.reports.map((report, reportIndex) => ({ key: report.run_id, record, pair: false, child: true, report, reportIndex }))];
    }
    const report = record.reports[0];
    return report ? [{ key: report.run_id, record, pair: false, child: false, report, reportIndex: 0 }] : [];
  }), [expanded, records]);
  const columns = useMemo<ColumnsType<EvaluationTableRow>>(() => [
    {
      key: "record",
      title: "批次 / 报告",
      width: 300,
      render: (_value, row) => {
        const report = row.report;
        const title = row.pair
          ? row.record.batch.title.trim() || "未命名配对评测"
          : reportTitleDisplay(report!, row.record.batch.kind === "paired" ? "未命名配对评测" : "未命名单次评测");
        const meta = row.pair
          ? shortEvaluationId(row.record.batch.batch_id)
          : `${report?.batch_role ?? ""}${report?.batch_role ? " · " : ""}${shortEvaluationId(report?.run_id ?? "")}`;
        return <div className={`evaluation-record-cell ${row.child ? "child" : ""}`}>
          <span className="evaluation-record-controls">
            {row.pair
              ? <PairSelectionCheckbox label={`选择配对批次 ${shortEvaluationId(row.record.batch.batch_id)}`} onToggle={() => onToggleSelected(row.record.reports.map((item) => item.run_id))} reportIds={row.record.reports.map((item) => item.run_id)} selected={selected} />
              : report
                ? <Checkbox aria-label={`选择报告 ${shortEvaluationId(report.run_id)}`} checked={selected.includes(report.run_id)} onChange={() => onToggleSelected([report.run_id])} />
                : null}
            {row.pair ? <Button aria-expanded={expanded.has(row.record.batch.batch_id)} aria-label={`${expanded.has(row.record.batch.batch_id) ? "收起" : "展开"} ${title}`} className="row-expand-button" icon={expanded.has(row.record.batch.batch_id) ? <MinusOutlined /> : <PlusOutlined />} onClick={() => onToggleExpanded(row.record.batch.batch_id)} size="small" type="text" /> : null}
          </span>
          {row.pair
            ? <Button className="record-title" onClick={() => onToggleExpanded(row.record.batch.batch_id)} type="text"><span className="record-title-line"><small>{meta}</small><b>{title}</b></span></Button>
            : report
              ? <Button className="record-title" onClick={() => onOpenReport(report.run_id)} type="text"><span className="record-title-line"><small>{meta}</small><b>{title}</b></span></Button>
              : null}
        </div>;
      },
    },
    { key: "status", title: "状态", width: 92, render: (_value, row) => <StatusPill value={row.pair ? row.record.batch.status : row.report?.status ?? ""} /> },
    { key: "elfie", title: "精灵", width: 130, render: (_value, row) => <span className="plain-cell">{row.pair ? row.record.batch.elfie_name || row.record.batch.elfie_id : row.report?.elfie_name || row.report?.elfie_id || "—"}</span> },
    { key: "food", title: "粮食套餐", width: 190, render: (_value, row) => <span className="plain-cell">{row.pair ? <PairValue reports={row.record.reports} value={foodDisplay} /> : row.report ? foodDisplay(row.report) : "—"}</span> },
    { key: "code", title: "代码", width: 190, render: (_value, row) => <span className="plain-cell">{row.pair ? <PairValue reports={row.record.reports} value={sourceRevisionDisplay} /> : row.report ? sourceRevisionDisplay(row.report) : "—"}</span> },
    { key: "strategy", title: "评测策略", width: 150, render: (_value, row) => <span className="plain-cell">{row.pair ? <PairValue reports={row.record.reports} value={(run) => `${run.test_plan_title} · ${run.total_scenarios} 场景`} /> : row.report ? `${row.report.test_plan_title} · ${row.report.total_scenarios} 场景` : "—"}</span> },
    {
      key: "result",
      title: "结果",
      width: 115,
      render: (_value, row) => row.pair
        ? <strong className="pair-result">{row.record.batch.status === "completed" && row.record.reports.length === 2 && row.record.reports[0]?.overall_score !== null && row.record.reports[0]?.overall_score !== undefined && row.record.reports[1]?.overall_score !== null && row.record.reports[1]?.overall_score !== undefined ? `B ${row.record.reports[1].overall_score - row.record.reports[0].overall_score >= 0 ? "+" : ""}${formatScore(row.record.reports[1].overall_score - row.record.reports[0].overall_score)}` : row.record.batch.status === "completed" ? "查看差异" : statusLabels[row.record.batch.status]}</strong>
        : row.report ? <strong className={`run-result ${row.report.verdict}`}>{runScoreResult(row.report)}</strong> : null,
    },
    { key: "completed", title: "完成时间", width: 140, render: (_value, row) => <span>{formatTime(row.pair ? row.record.batch.completed_at : row.report?.completed_at ?? null)}</span> },
    {
      key: "action",
      title: "",
      width: 76,
      render: (_value, row) => {
        const report = row.report;
        return row.pair
          ? <Button aria-label={`查看配对评测 ${shortEvaluationId(row.record.batch.batch_id)}`} className="row-action" disabled={row.record.reports.length !== 2} onClick={() => onOpenComparison(row.record.reports.map((item) => item.run_id))} size="small">查看</Button>
          : report ? <Button className="row-action" onClick={() => onOpenReport(report.run_id)} size="small">查看</Button> : null;
      },
    },
  ], [expanded, onOpenComparison, onOpenReport, onToggleExpanded, onToggleSelected, selected]);

  return <Table<EvaluationTableRow>
    className="evaluation-library-table"
    columns={columns}
    dataSource={rows}
    pagination={false}
    rowClassName={(row) => row.pair ? "evaluation-ant-row evaluation-ant-batch-row" : row.child ? "evaluation-ant-row evaluation-ant-child-row" : "evaluation-ant-row evaluation-ant-report-row"}
    rowKey="key"
  />;
}

export function EvaluationWorkspace({ elfies, session, food, foods, reviewerSubscriptions = [], onSaveReviewerSubscription, onDeleteReviewerSubscription, onNewFood, onNewElfie }: Props): React.JSX.Element {
  type TimeRange = "" | "7d" | "30d";
  const [presets, setPresets] = useState<readonly EvaluationPreset[]>(fallbackPresets);
  const [branches, setBranches] = useState<EvaluationCodeBranches>({ current_ref: "HEAD", items: [] });
  const [records, setRecords] = useState<readonly EvaluationBatchRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<20 | 50>(20);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [timeRange, setTimeRange] = useState<TimeRange>("");
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [selectedReports, setSelectedReports] = useState<readonly EvaluationRun[]>([]);
  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [comparison, setComparison] = useState<EvaluationComparison | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [createMode, setCreateMode] = useState<CreateMode>(null);
  const [createMenuOpen, setCreateMenuOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const firstPairExpanded = useRef(false);
  const reports = useMemo(() => allReports(records), [records]);
  const selected = useMemo(() => selectedReports.map((item) => item.run_id), [selectedReports]);
  const drawerReports = useMemo(() => {
    const available = new Map([...selectedReports, ...reports].map((item) => [item.run_id, item]));
    return [...available.values()];
  }, [reports, selectedReports]);
  const active = records.some((item) => ["pending", "running"].includes(item.batch.status));
  const load = useCallback(async (): Promise<void> => {
    try {
      const params = new URLSearchParams({
        offset: String((page - 1) * pageSize),
        limit: String(pageSize),
      });
      if (query.trim()) params.set("query", query.trim());
      if (status) params.set("status", status);
      const days = timeRange === "7d" ? 7 : timeRange === "30d" ? 30 : 0;
      if (days) params.set("created_after", new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString());
      const result = await requestJson(`evaluations?${params.toString()}`, evaluationBatchListSchema);
      const latestReports = allReports(result.items);
      setRecords(result.items); setTotal(result.total); setLoading(false); setNotice("");
      setSelectedReports((current) => current.map((item) => latestReports.find((latest) => latest.run_id === item.run_id) ?? item));
      if (!firstPairExpanded.current) {
        const firstPair = result.items.find((item) => item.batch.kind === "paired");
        if (firstPair) setExpanded(new Set([firstPair.batch.batch_id]));
        firstPairExpanded.current = true;
      }
    } catch (reason) { setLoading(false); setNotice(reason instanceof Error ? reason.message : "无法读取评测报告"); }
  }, [page, pageSize, query, status, timeRange]);
  useEffect(() => { void requestJson("evaluations/presets", evaluationPresetsSchema).then((result) => setPresets(result.items), () => undefined); void requestJson("evaluations/code-branches", evaluationCodeBranchesSchema).then(setBranches, () => undefined); }, []);
  useEffect(() => { const timer = window.setTimeout(() => { void load(); }, query ? 260 : 0); return () => window.clearTimeout(timer); }, [load]);
  useEffect(() => { if (!active) return; const timer = window.setInterval(() => { void load(); }, 1000); return () => window.clearInterval(timer); }, [active, load]);
  useEffect(() => { function keydown(event: KeyboardEvent): void { if (event.key === "Escape") { setDrawer(null); setCreateMode(null); } } window.addEventListener("keydown", keydown); return () => window.removeEventListener("keydown", keydown); }, []);

  function toggleExpanded(batchId: string): void { setExpanded((current) => { const next = new Set(current); if (next.has(batchId)) next.delete(batchId); else next.add(batchId); return next; }); }
  function toggleSelected(ids: readonly string[]): void {
    const next = nextSelectedEvaluationRuns(selectedReports, reports, ids);
    if (next === null) {
      setNotice("一次最多选择两份报告；如需选择整组配对报告，请先清空当前选择。");
      return;
    }
    setSelectedReports(next);
    setNotice("");
  }
  async function openComparison(ids: readonly string[]): Promise<void> {
    const reportAId = ids[0]; const reportBId = ids[1];
    if (ids.length !== 2 || reportAId === undefined || reportBId === undefined) return;
    setDrawer({ kind: "comparison", reportIds: [reportAId, reportBId] }); setComparison(null); setComparisonLoading(true);
    try {
      const result = await requestJson("evaluations/comparisons", evaluationComparisonSchema, { method: "post", json: { report_a_id: reportAId, report_b_id: reportBId }, timeout: 190_000 });
      setComparison(result);
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "无法生成对比报告"); }
    finally { setComparisonLoading(false); }
  }
  const selectedRuns = selectedReports;
  const selectedA = selectedRuns[0]; const selectedB = selectedRuns[1];
  const selectionGrade = selectedRuns.length === 2 && selectedA !== undefined && selectedB !== undefined ? comparisonGradeForReports(selectedA, selectedB) : null;
  const selectionDifferences = selectedA !== undefined && selectedB !== undefined
    ? Number(selectedA.source_snapshot_sha256 !== selectedB.source_snapshot_sha256) + Number(selectedA.food_spec_sha256 !== selectedB.food_spec_sha256)
    : 0;
  const repeatedCandidate = selectedA !== undefined && selectedB !== undefined
    && selectionDifferences === 0
    && selectedA.judge_spec_sha256 === selectedB.judge_spec_sha256;
  const createMenuItems = [
    { key: "single", label: <b>新建单次评测</b> },
    { key: "paired", label: <b>新建配对评测</b> },
  ];

  return <section className="evaluation-workspace" aria-label="Elfie 批量评测">
    <header className="evaluation-page-header">
      <div><h1>评测批次</h1></div>
    </header>
    <div className="evaluation-control-surface">
      <div className="evaluation-control-row">
        <div className="selection-bar"><div aria-live="polite" className="selection-context">{selected.length ? <><strong>已选择 {selected.length} 份</strong>{selectionGrade ? <Tag color={selectionGrade === "strict" ? "success" : selectionGrade === "observational" ? "warning" : "error"}>{selectionGrade === "strict" ? "严格配对" : selectionGrade === "observational" ? repeatedCandidate ? "重复运行观察" : "多变量观察" : "条件不兼容"}</Tag> : null}<Button className="selection-action-link" disabled={selected.length !== 2} onClick={() => { void openComparison(selected); }} type="link">查看对比</Button></> : <span className="selection-empty">选择两份报告后查看对比</span>}</div></div>
        <div className="evaluation-header-actions"><Dropdown.Button aria-label="新建评测" className="new-evaluation" destroyOnHidden icon={<DownOutlined />} menu={{ items: createMenuItems, onClick: ({ key }) => { setCreateMenuOpen(false); setCreateMode(key as CreateMode); } }} onClick={() => setCreateMode("single")} onOpenChange={setCreateMenuOpen} open={createMenuOpen} placement="bottomRight" type="primary">新建评测</Dropdown.Button><div className="evaluation-toolbar"><label><span>搜索</span><Input onChange={(event) => { setPage(1); setQuery(event.target.value); }} placeholder="搜索批次、精灵、粮食或说明" value={query} /></label><label><span>状态</span><EvaluationSelect ariaLabel="状态" onChange={(value) => { setPage(1); setStatus(value); }} options={[{ value: "", label: "全部" }, { value: "running", label: "运行中" }, { value: "completed", label: "已完成" }, { value: "partial_failed", label: "部分失败" }, { value: "failed", label: "失败" }]} value={status} /></label><label><span>时间</span><EvaluationSelect ariaLabel="时间范围" onChange={(value) => { setPage(1); setTimeRange(value as TimeRange); }} options={[{ value: "", label: "全部" }, { value: "7d", label: "最近 7 天" }, { value: "30d", label: "最近 30 天" }]} value={timeRange} /></label><Button aria-label="刷新评测批次" onClick={() => { void load(); }}>刷新</Button></div></div>
      </div>
    </div>
    {notice ? <Alert className="evaluation-page-notice" closable onClose={() => setNotice("")} showIcon type="error" description={notice} /> : null}
    <div className="evaluation-table-wrap">
      {loading ? <div className="evaluation-table-loading"><Skeleton active paragraph={{ rows: 8 }} title /></div> : records.length === 0 ? <Empty description="还没有评测报告"><Button onClick={() => setCreateMode("single")} type="primary">新建第一次评测</Button></Empty> : <EvaluationReportTable expanded={expanded} onOpenComparison={(ids) => { void openComparison(ids); }} onOpenReport={(reportId) => setDrawer({ kind: "report", reportId })} onToggleExpanded={toggleExpanded} onToggleSelected={toggleSelected} records={records} selected={selected} />}
    </div>
    <footer className="evaluation-pagination"><span>共 {total} 个批次 / 报告组</span><Pagination current={page} pageSize={pageSize} pageSizeOptions={[20, 50]} showSizeChanger={false} onChange={(nextPage, nextPageSize) => { setPage(nextPage); setPageSize(nextPageSize as 20 | 50); }} total={total} /></footer>
    {drawer ? <EvaluationDrawer comparison={comparison} comparisonLoading={comparisonLoading} onClose={() => setDrawer(null)} reports={drawerReports} state={drawer} /> : null}
    {createMode ? <CreateEvaluationModal branches={branches} defaultElfieId={session?.elfie_id ?? elfies[0]?.elfie_id ?? ""} defaultFood={food} elfies={elfies} foods={foods} mode={createMode} onClose={() => setCreateMode(null)} onDeleteReviewerSubscription={onDeleteReviewerSubscription} onNewFood={onNewFood} onNewElfie={onNewElfie} onSaveReviewerSubscription={onSaveReviewerSubscription} onCreated={(record) => { setCreateMode(null); setRecords((current) => [record, ...current]); setExpanded((current) => new Set([...current, record.batch.batch_id])); void load(); }} presets={presets} reviewerSubscriptions={reviewerSubscriptions} /> : null}
  </section>;
}
