import { useEffect, useMemo, useRef, useState } from "react";

import { requestJson } from "../api/http";
import {
  evaluationHistorySchema,
  evaluationPresetsSchema,
  evaluationRunSchema,
  type ElfieSession,
  type EvaluationPreset,
  type EvaluationRun,
  type EvaluationScenario,
  type FoodItem,
} from "./contracts";
import { WorkspaceModeSwitch } from "./WorkspaceModeSwitch";

type Props = Readonly<{
  readonly session: ElfieSession | null;
  readonly food: string;
  readonly foods: readonly FoodItem[];
  readonly onOpenExperiment: () => void;
}>;

const fallbackPresets: readonly EvaluationPreset[] = [
  { key: "quick", title: "快速检查", description: "检查越权、角色锚点和关键记忆，适合每轮改动后运行。", typical_duration: "约 3–10 分钟", scenario_count: 3, requires_godot: false },
  { key: "standard", title: "标准评测", description: "覆盖六项核心体验和关键边界，用于版本基线对比。", typical_duration: "约 30–60 分钟", scenario_count: 8, requires_godot: false },
];

const verdictLabels: Readonly<Record<EvaluationRun["verdict"], string>> = {
  baseline: "已建立开发基线",
  improved: "整体变好",
  observe: "没有明显变化",
  regressed: "发现退化",
  incomplete: "证据还不完整",
};
const statusLabels: Readonly<Record<EvaluationScenario["status"], string>> = {
  pending: "等待中", running: "运行中", baseline: "基线", passed: "通过", failed: "未通过",
  improved: "变好", unchanged: "持平", regressed: "退化", incomplete: "证据不足",
};

function outputText(values: readonly string[]): string {
  return values.join("\n") || "没有公开文字输出";
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
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

function ResultDetail({ run, scenario, onBaseline }: Readonly<{ readonly run: EvaluationRun | null; readonly scenario: EvaluationScenario | null; readonly onBaseline: () => void }>): React.JSX.Element {
  if (run === null) return <aside className="evaluation-detail"><div className="evaluation-detail-empty"><p className="eyebrow">结果解释</p><h2>等待一次评测</h2><p>第一次运行会保存为开发基线；下一轮才会显示变好、持平或退化。</p></div></aside>;
  const progress = Math.round((run.completed_scenarios / Math.max(1, run.total_scenarios)) * 100);
  return <aside className="evaluation-detail">
    <header className="evaluation-detail-heading"><div><p className="eyebrow">探索性版本结论</p><h2>{run.status === "completed" ? verdictLabels[run.verdict] : run.status === "failed" ? "运行失败" : `正在运行 · ${progress}%`}</h2></div><span className={`evaluation-verdict-dot ${run.verdict}`} /></header>
    <div className="evaluation-detail-scroll">
      <section className="evaluation-summary-card">
        <div><span>候选</span><strong>{run.candidate_label}</strong></div><div><span>套件</span><strong>{run.suite === "quick" ? "快速检查" : "标准评测"}</strong></div>
        <div><span>被测模型</span><strong>{run.food_model}</strong></div><div><span>评审模型</span><strong>{run.judge_model}</strong></div>
        <div><span>Brain 调用</span><strong>{run.total_model_calls}</strong></div><div><span>Brain 耗时</span><strong>{(run.total_latency_ms / 1000).toFixed(1)}s</strong></div>
      </section>
      {run.dimensions.length ? <section className="evaluation-detail-section"><h3>能力维度变化</h3><div className="dimension-list">{run.dimensions.map((item) => <div key={item.dimension}><span>{item.label}</span><b className={item.status}>{statusLabels[item.status]}</b></div>)}</div></section> : null}
      <section className="evaluation-detail-section"><h3>红线检查</h3>{run.p0_violations.length ? <div className="violation-list">{run.p0_violations.map((item) => <article key={`${item.code}-${item.title}`}><b>{item.code}</b><p>{item.title}</p></article>)}</div> : <p className="evaluation-ok">当前已完成场景未发现红线违规。</p>}</section>
      {scenario !== null ? <section className="evaluation-detail-section scenario-comparison"><h3>{scenario.title}</h3><p>{scenario.purpose}</p><div><span>旧基线</span><pre>{outputText(scenario.baseline_outputs)}</pre></div><div><span>当前版本</span><pre>{outputText(scenario.candidate_outputs)}</pre></div>{scenario.evidence.length ? <ul>{scenario.evidence.map((item) => <li key={item}>{item}</li>)}</ul> : null}</section> : null}
      {run.warnings.length ? <section className="evaluation-detail-section evaluation-warnings"><h3>如何理解这个结果</h3>{run.warnings.map((warning) => <p key={warning}>{warning}</p>)}</section> : null}
      {run.status === "completed" && !run.is_baseline ? <button className="evaluation-secondary-action" onClick={onBaseline} type="button">设为新的开发基线</button> : null}
    </div>
  </aside>;
}

export function EvaluationWorkspace({ session, food, foods, onOpenExperiment }: Props): React.JSX.Element {
  const [presets, setPresets] = useState<readonly EvaluationPreset[]>(fallbackPresets);
  const [suite, setSuite] = useState<"quick" | "standard">("quick");
  const [judgeFood, setJudgeFood] = useState(food);
  const [runs, setRuns] = useState<readonly EvaluationRun[]>([]);
  const [baselineIds, setBaselineIds] = useState<Readonly<Record<string, string>>>({});
  const [activeRun, setActiveRun] = useState<EvaluationRun | null>(null);
  const [selectedFamily, setSelectedFamily] = useState("");
  const [notice, setNotice] = useState("");
  const currentElfieIdRef = useRef<string | null>(null);
  currentElfieIdRef.current = session?.elfie_id ?? null;

  const readyFoods = useMemo(() => foods.filter((item) => item.ready_for_attempt), [foods]);
  const selectedFood = foods.find((item) => item.key === food);
  const selectedFoodReady = selectedFood?.ready_for_attempt === true;
  const judgeFoodReady = readyFoods.some((item) => item.key === judgeFood);
  const scopedRuns = runs.filter((item) => item.elfie_id === session?.elfie_id);
  const currentRun = activeRun?.elfie_id === session?.elfie_id ? activeRun : null;
  const selectedPreset = presets.find((item) => item.key === suite) ?? presets[0];
  const baseline = scopedRuns.find((item) => item.run_id === baselineIds[suite]);
  const selectedScenario = currentRun?.scenarios.find((item) => item.family_id === selectedFamily) ?? currentRun?.scenarios[0] ?? null;
  const running = currentRun?.status === "pending" || currentRun?.status === "running";
  const selectedFoodName = selectedFood?.display_name ?? (food || "未选择");

  useEffect(() => {
    if (readyFoods.some((item) => item.key === judgeFood)) return;
    const fallback = readyFoods.find((item) => item.key === food)?.key ?? readyFoods[0]?.key ?? "";
    setJudgeFood(fallback);
  }, [food, judgeFood, readyFoods]);
  useEffect(() => {
    void requestJson("evaluations/presets", evaluationPresetsSchema).then((result) => setPresets(result.items), () => undefined);
  }, []);
  useEffect(() => {
    if (session === null) { setRuns([]); setBaselineIds({}); setActiveRun(null); return; }
    void loadHistory(session.elfie_id);
  }, [session?.elfie_id]);
  useEffect(() => {
    if (!running || currentRun === null || session === null) return;
    const timer = window.setTimeout(() => {
      void requestJson(`elfies/${encodeURIComponent(session.elfie_id)}/evaluations/${encodeURIComponent(currentRun.run_id)}`, evaluationRunSchema).then((next) => {
        if (currentElfieIdRef.current !== next.elfie_id) return;
        setActiveRun(next);
        if (next.status === "completed" || next.status === "failed") void loadHistory(session.elfie_id);
      }, (error: unknown) => {
        if (currentElfieIdRef.current === currentRun.elfie_id) setNotice(error instanceof Error ? error.message : "无法刷新评测进度");
      });
    }, 700);
    return () => window.clearTimeout(timer);
  }, [currentRun, running, session]);

  async function loadHistory(elfieId: string): Promise<void> {
    try {
      const history = await requestJson(`elfies/${encodeURIComponent(elfieId)}/evaluations`, evaluationHistorySchema);
      if (currentElfieIdRef.current !== elfieId) return;
      setRuns(history.items);
      setBaselineIds(history.baseline_run_ids);
      setActiveRun((current) => selectActiveEvaluationRun(current, history.items, suite, elfieId));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "无法读取评测历史");
    }
  }
  async function start(): Promise<void> {
    if (session === null || !selectedFoodReady || !judgeFoodReady) return;
    setNotice("");
    try {
      const run = await requestJson(`elfies/${encodeURIComponent(session.elfie_id)}/evaluations`, evaluationRunSchema, { method: "post", json: { suite, food_key: food, judge_food_key: judgeFood || food }, timeout: 15_000 });
      setActiveRun(run);
      setSelectedFamily(run.scenarios[0]?.family_id ?? "");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "评测启动失败");
    }
  }
  async function makeBaseline(): Promise<void> {
    if (session === null || currentRun === null) return;
    try {
      const updated = await requestJson(`elfies/${encodeURIComponent(session.elfie_id)}/evaluations/${encodeURIComponent(currentRun.run_id)}/baseline`, evaluationRunSchema, { method: "post" });
      setActiveRun(updated);
      await loadHistory(session.elfie_id);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "无法设置开发基线");
    }
  }
  function chooseSuite(next: "quick" | "standard"): void {
    setSuite(next);
    setActiveRun(scopedRuns.find((item) => item.suite === next) ?? null);
    setSelectedFamily("");
  }

  return <section className="evaluation-workspace" aria-label="Elfie 版本评测">
    <div className="evaluation-main">
      <header className="evaluation-heading"><div><p className="eyebrow">Elfie Brain 对比</p><h2>版本评测</h2></div><WorkspaceModeSwitch active="evaluation" onEvaluation={() => undefined} onExperiment={onOpenExperiment} /></header>
      <div className="evaluation-scroll">
        <section className="evaluation-intro"><div><p className="eyebrow">每轮优化后的固定动作</p><h1>运行同一组生活场景，确认精灵是真的变好了</h1><p>第一次运行保存旧基线；以后自动对比当前代码、模型与配置。聊天与记忆评测不依赖 3D 世界。</p></div><div className="evaluation-baseline-card"><span>{baseline ? "当前开发基线" : "尚未建立基线"}</span><strong>{baseline?.candidate_label ?? "首次运行后自动建立"}</strong><small>{baseline ? formatTime(baseline.created_at) : "只影响本地开发评测"}</small></div></section>
        <section className="evaluation-section"><header><div><p className="eyebrow">01 · 选择范围</p><h3>评测强度</h3></div></header><div className="preset-grid">{presets.map((preset) => <button aria-pressed={suite === preset.key} className={suite === preset.key ? "preset-card active" : "preset-card"} key={preset.key} onClick={() => chooseSuite(preset.key)} type="button"><span>{preset.title}</span><b>{preset.scenario_count} 个场景</b><p>{preset.description}</p><small>{preset.typical_duration}</small></button>)}</div></section>
        <section className="evaluation-section evaluation-run-config"><header><div><p className="eyebrow">02 · 冻结本轮</p><h3>当前候选</h3></div></header><div className="candidate-strip"><div><span>测试精灵</span><strong>{session?.profile.name ?? "请先创建测试精灵"}</strong></div><div><span>被测模型</span><strong>{selectedFoodName}</strong></div><label><span>自动评审模型</span><select disabled={running || !readyFoods.length} onChange={(event) => setJudgeFood(event.target.value)} value={judgeFood}>{readyFoods.map((item) => <option key={item.key} value={item.key}>{item.display_name}</option>)}</select></label></div><button className="evaluation-primary-action" disabled={running || session === null || !selectedFoodReady || !judgeFoodReady} onClick={() => { void start(); }} type="button">{running ? `正在运行 ${currentRun?.completed_scenarios ?? 0}/${currentRun?.total_scenarios ?? selectedPreset?.scenario_count ?? 0}` : "运行评测"}</button>{!selectedFoodReady && food ? <p className="evaluation-notice" role="status">{selectedFoodName}尚未配置，不能运行评测。</p> : notice ? <p className="evaluation-notice" role="status">{notice}</p> : null}</section>
        {currentRun !== null ? <section className="evaluation-section evaluation-results"><header><div><p className="eyebrow">03 · 查看证据</p><h3>{currentRun.status === "completed" ? verdictLabels[currentRun.verdict] : "场景运行进度"}</h3></div><span>{currentRun.completed_scenarios}/{currentRun.total_scenarios}</span></header><div className="evaluation-progress"><i style={{ width: `${(currentRun.completed_scenarios / Math.max(1, currentRun.total_scenarios)) * 100}%` }} /></div><div className="scenario-list">{currentRun.scenarios.map((scenario) => <button className={selectedScenario?.family_id === scenario.family_id ? "active" : ""} key={scenario.family_id} onClick={() => setSelectedFamily(scenario.family_id)} type="button"><span><b>{scenario.title}</b><small>{scenario.purpose}</small></span><em className={scenario.status}>{statusLabels[scenario.status]}</em></button>)}</div></section> : null}
        {scopedRuns.length ? <section className="evaluation-section evaluation-history"><header><div><p className="eyebrow">历史</p><h3>最近运行</h3></div></header><div>{scopedRuns.map((run) => <button className={currentRun?.run_id === run.run_id ? "active" : ""} key={run.run_id} onClick={() => { setSuite(run.suite); setActiveRun(run); setSelectedFamily(run.scenarios[0]?.family_id ?? ""); }} type="button"><span>{run.suite === "quick" ? "快速" : "标准"} · {formatTime(run.created_at)}</span><b>{run.is_baseline ? "开发基线" : verdictLabels[run.verdict]}</b></button>)}</div></section> : null}
      </div>
    </div>
    <ResultDetail onBaseline={() => { void makeBaseline(); }} run={currentRun} scenario={selectedScenario} />
  </section>;
}
