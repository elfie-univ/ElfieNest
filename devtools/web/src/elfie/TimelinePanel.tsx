import { useEffect, useRef, useState } from "react";
import { Button, Checkbox, Input, Segmented, Select } from "antd";

import type { ElfieSession, ElfieTurn, PreviewIntent } from "./contracts";
import { buildStateInjection } from "./stimulus";
import { formatSignedDelta } from "./viewModel";

type SourceDomain = "communication" | "embodied";
type UploadedMedia = Readonly<{ readonly id: string; readonly mimeType: string }>;

type Stimulus = Readonly<{
  readonly source_domain: SourceDomain;
  readonly message: string;
  readonly food_key: string;
  readonly temperature: number;
  readonly is_network_online: boolean;
  readonly salience_score: number;
  readonly impact_force: number;
  readonly impact_direction: string;
  readonly gentle_stroke: number;
  readonly state_injection: Record<string, unknown>;
  readonly vision_media_id?: string;
  readonly attachments?: readonly Readonly<{ readonly media_id: string; readonly filename: string }>[];
}>;

type Props = Readonly<{
  readonly session: ElfieSession | null;
  readonly food: string;
  readonly onSend: (stimulus: Stimulus) => Promise<boolean>;
  readonly onSelectTurn: (turn: ElfieTurn, focus: string) => void;
  readonly onPreviewIntent: (turn: ElfieTurn, intent: PreviewIntent) => void;
  readonly onUpload: (file: File) => Promise<UploadedMedia>;
  readonly portraitEpoch: number;
  readonly onOpenEvaluation?: () => void;
}>;

const emotionLabels: Readonly<Record<string, string>> = {
  happiness: "快乐", sadness: "悲伤", anger: "愤怒", fear: "恐惧", surprise: "惊讶", disgust: "厌恶",
};

function turnText(turn: ElfieTurn): string {
  return [...turn.decision.spoken_texts, ...turn.decision.message_texts].join("\n") || turn.result.message || "本轮无文字输出";
}

function actionIntents(turn: ElfieTurn): readonly PreviewIntent[] {
  if (turn.decision.action_intents.length) return turn.decision.action_intents;
  return [...turn.decision.motion_intents, ...turn.decision.expression_intents];
}

function intentLabel(intent: PreviewIntent): string {
  if (intent.motion) return `动作 · ${intent.motion}`;
  return `表情 · ${intent.expression ?? "未知"}${intent.intensity === undefined ? "" : ` · ${intent.intensity}`}`;
}

function turnSourceLabel(turn: ElfieTurn): string {
  const source = turn.stimulus_bundle.source_domain === "embodied" ? "现场" : "消息";
  const attachments = turn.stimulus_bundle.message_attachments;
  const modality = turn.stimulus_bundle.vision_media_id
    ? "视觉"
    : Array.isArray(attachments) && attachments.length > 0
      ? "附件"
    : turn.stimulus_bundle.message
      ? "文字"
      : "非文字";
  return `${source} · ${modality}`;
}

function avatar(url: string, name: string, epoch: number, developer = false): React.JSX.Element {
  const source = url ? `${url}${url.includes("?") ? "&" : "?"}v=${epoch}` : "";
  return <span aria-hidden="true" className={developer ? "message-avatar developer-avatar" : "message-avatar"}>{source ? <img alt="" src={source} /> : developer ? <svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4" /><path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" /></svg> : <b>{name.slice(0, 1) || "艾"}</b>}</span>;
}

function tags(turn: ElfieTurn): readonly string[] {
  const rows: string[] = [];
  const emotion = turn.state_after?.primary_emotion;
  if (emotion) rows.push(emotionLabels[emotion] ?? emotion);
  const energy = turn.state_diff?.energy;
  if (typeof energy === "object" && energy !== null && "before" in energy && "after" in energy) {
    const before = energy.before;
    const after = energy.after;
    if (typeof before === "number" && typeof after === "number") rows.push(`能量 ${formatSignedDelta(before, after)}`);
  }
  return rows;
}

function TurnList({ session, onPreviewIntent, onSelect, epoch }: Readonly<{ readonly session: ElfieSession; readonly onPreviewIntent: Props["onPreviewIntent"]; readonly onSelect: Props["onSelectTurn"]; readonly epoch: number }>): React.JSX.Element {
  if (!session.turns.length) return <section className="timeline-placeholder"><div className="signal-mark"><i /><i /><i /></div><h3>等待第一次刺激</h3><p>发送一句话，或打开实验刺激构造边界状态。</p></section>;
  return <>{session.turns.map((turn, index) => {
    const intents = actionIntents(turn).filter((intent) => (intent.type === "motion" || intent.type === "expression") && Boolean(intent.intent_id));
    return <article className="turn" key={turn.turn_id}><div className="turn-meta">TURN {String(index + 1).padStart(2, "0")} · {new Date(turn.timestamp).toLocaleTimeString("zh-CN")}</div><div className="bubble-row user">{avatar("", "", epoch, true)}<Button className="bubble" onClick={() => onSelect(turn, "input")} type="text"><span className="bubble-label"><span>开发者刺激</span><span className="channel">{turnSourceLabel(turn)}</span></span><p>{turn.stimulus_bundle.message || "非文字刺激"}</p>{turn.used_state_injection ? <span className="bubble-tag warning">状态注入</span> : null}</Button></div><Button className="process-line" onClick={() => onSelect(turn, "chain")} type="text">感知 <i /> 决策 <i /> {turn.duration_ms ?? 0}ms</Button><div className="bubble-row elfie">{avatar(session.profile.portrait_url, session.profile.name, epoch)}<div><Button className={turn.result.success === false ? "bubble error" : "bubble"} onClick={() => onSelect(turn, "output")} type="text"><span className="bubble-label">{session.profile.name}</span><p>{turnText(turn)}</p>{tags(turn).map((tag) => <span className="bubble-tag" key={tag}>{tag}</span>)}</Button>{intents.length ? <div className="turn-actions" aria-label="动作回放">{intents.map((intent) => <Button className="turn-action" key={intent.intent_id} onClick={() => onPreviewIntent(turn, intent)} size="small" type="default">{intentLabel(intent)}</Button>)}</div> : null}</div></div></article>;
  })}</>;
}

export function TimelinePanel(props: Props): React.JSX.Element {
  const [sourceDomain, setSourceDomain] = useState<SourceDomain>("communication");
  const [drafts, setDrafts] = useState<Record<SourceDomain, string>>({ communication: "", embodied: "" });
  const [drawer, setDrawer] = useState(false);
  const [debug, setDebug] = useState(false);
  const [injectionEnabled, setInjectionEnabled] = useState(false);
  const [sending, setSending] = useState(false);
  const [temperature, setTemperature] = useState(24);
  const [impact, setImpact] = useState(0);
  const [direction, setDirection] = useState("none");
  const [stroke, setStroke] = useState(0);
  const [sleeping, setSleeping] = useState(false);
  const [sleepingTouched, setSleepingTouched] = useState(false);
  const [injection, setInjection] = useState<Record<string, string>>({});
  const [media, setMedia] = useState<{ readonly id: string; readonly name: string; readonly url: string; readonly mimeType: string } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const disabled = props.session === null;
  const message = drafts[sourceDomain];
  const stateInjection = buildStateInjection(
    injectionEnabled,
    injection,
    sleeping,
    sleepingTouched,
  );
  const hasStateInjection = Object.keys(stateInjection).length > 0;
  useEffect(() => () => {
    if (media !== null) URL.revokeObjectURL(media.url);
  }, [media]);
  function updateInjection(name: string, value: string): void { setInjection((current) => ({ ...current, [name]: value })); }
  function updateMessage(value: string): void {
    setDrafts((current) => ({ ...current, [sourceDomain]: value }));
  }
  function switchSource(nextSource: SourceDomain): void {
    if (nextSource === sourceDomain) return;
    setMedia(null);
    setSourceDomain(nextSource);
  }
  function sendWithEnter(event: React.KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }
  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (sending) return;
    setSending(true);
    try {
      const sent = await props.onSend({
        source_domain: sourceDomain,
        message,
        food_key: props.food,
        temperature,
        is_network_online: true,
        salience_score: 20,
        impact_force: sourceDomain === "embodied" ? impact : 0,
        impact_direction: sourceDomain === "embodied" ? direction : "none",
        gentle_stroke: sourceDomain === "embodied" ? stroke : 0,
        state_injection: stateInjection,
        ...(sourceDomain === "embodied" && media !== null ? { vision_media_id: media.id } : {}),
        ...(sourceDomain === "communication" && media !== null ? { attachments: [{ media_id: media.id, filename: media.name }] } : {}),
      });
      if (!sent) return;
      setDrafts((current) => ({ ...current, [sourceDomain]: "" }));
      setImpact(0);
      setDirection("none");
      setStroke(0);
      setInjection({});
      setSleeping(false);
      setSleepingTouched(false);
      setInjectionEnabled(false);
      setMedia(null);
    } finally {
      setSending(false);
    }
  }
  async function chooseMedia(file: File): Promise<void> {
    const uploaded = await props.onUpload(file);
    if (media !== null) URL.revokeObjectURL(media.url);
    setMedia({ id: uploaded.id, name: file.name, url: URL.createObjectURL(file), mimeType: uploaded.mimeType });
  }
  const showDebugPanel = sourceDomain === "communication" || debug;
  const cannotSend = sourceDomain === "communication"
    ? !message.trim() && media === null
    : !message.trim() && media === null && impact === 0 && stroke === 0 && !hasStateInjection;
  return <section className="timeline-panel" aria-label="交互时间线">
    <div className="timeline-heading">
      <div className="timeline-heading-title"><h2>交互时间线</h2></div>
      <div className="timeline-heading-actions"><div className="session-indicator"><span /><b>{props.session?.turns.length ?? 0} 轮</b></div></div>
    </div>
    <div className="timeline">
      {props.session === null
        ? <section className="timeline-placeholder"><h3>等待测试精灵</h3><p>在左侧创建一只独立测试精灵。</p></section>
        : <TurnList epoch={props.portraitEpoch} onPreviewIntent={props.onPreviewIntent} onSelect={props.onSelectTurn} session={props.session} />}
    </div>
    <form className="composer" onSubmit={(event) => { void submit(event); }}>
      {drawer ? <div className="stimulus-drawer">
        {sourceDomain === "embodied" ? <Segmented className="stimulus-tabs" onChange={(value) => setDebug(value === "debug")} options={[{ label: "现场刺激", value: "live" }, { label: `Debug 状态${hasStateInjection ? " · 已启用" : ""}`, value: "debug" }]} value={debug ? "debug" : "live"} /> : <div className="drawer-context">
          <strong>消息 · Debug 状态</strong>
          <span>消息线路只发送会话内容；这里可以覆盖本轮开始前的实验状态。</span>
        </div>}
        {showDebugPanel ? <div>
          <div className="debug-toggle-row"><Checkbox checked={injectionEnabled} onChange={(event) => setInjectionEnabled(event.target.checked)}>启用本轮状态覆盖</Checkbox></div>
          <div aria-disabled={!injectionEnabled} className="injection-grid">
            <Checkbox checked={sleeping} disabled={!injectionEnabled} onChange={(event) => { setSleeping(event.target.checked); setSleepingTouched(true); }}>睡眠中</Checkbox>
            {["energy", "fatigue", "happiness", "sadness", "anger", "fear", "surprise", "disgust"].map((name) => <label key={name}>{name}<Input disabled={!injectionEnabled} onChange={(event) => updateInjection(name, event.target.value)} placeholder="不修改" type="number" value={injection[name] ?? ""} /></label>)}
          </div>
        </div> : <div className="stimulus-grid">
          <label>环境温度 <span><Input onChange={(event) => setTemperature(Number(event.target.value))} type="number" value={temperature} /> °C</span></label>
          <label>撞击力 <span><Input min="0" onChange={(event) => setImpact(Number(event.target.value))} type="number" value={impact} /></span></label>
          <label>触碰位置 <Select onChange={setDirection} options={[{ label: "无", value: "none" }, { label: "头部", value: "head" }, { label: "背部", value: "back" }, { label: "爪部", value: "paw" }]} value={direction} /></label>
          <label>抚摸力度 <span><Input min="0" onChange={(event) => setStroke(Number(event.target.value))} type="number" value={stroke} /></span></label>
        </div>}
      </div> : null}
      {media !== null ? <div className="media-preview">
        {media.mimeType.startsWith("image/") ? <img alt={sourceDomain === "embodied" ? "本轮视觉输入预览" : "消息图片附件预览"} src={media.url} /> : <span aria-hidden="true" className="media-file-icon">↥</span>}
        <span><strong>{media.name}</strong><small>{sourceDomain === "embodied" ? "现场视觉输入" : "消息附件"}</small></span>
        <Button aria-label="移除附件" onClick={() => setMedia(null)} shape="circle" type="text">×</Button>
      </div> : null}
      <div className="composer-row"><div className="message-field">
        <div className="message-field-inner"><Input.TextArea autoSize={{ minRows: 1, maxRows: 5 }} disabled={disabled || sending} onChange={(event) => updateMessage(event.target.value)} onKeyDown={sendWithEnter} placeholder={sourceDomain === "communication" ? "发送一条消息…" : "输入现场听到的话…"} value={message} /></div>
        <div className="message-field-footer">
          <div className="message-field-actions">
            <Segmented aria-label="输入来源" className="source-switch" disabled={sending} onChange={(value) => switchSource(value as SourceDomain)} options={[{ label: "消息", value: "communication" }, { label: "现场", value: "embodied" }]} value={sourceDomain} />
            <Button aria-label={sourceDomain === "embodied" ? "添加视觉输入" : "添加附件"} className="tool-button" disabled={disabled || sending} onClick={() => inputRef.current?.click()} type="text">+</Button>
            <input accept={sourceDomain === "embodied" ? "image/png,image/jpeg,image/webp" : "image/png,image/jpeg,image/webp,application/pdf,text/plain,text/markdown,application/json,text/csv"} hidden onChange={(event) => { const file = event.target.files?.[0]; event.currentTarget.value = ""; if (file !== undefined) void chooseMedia(file); }} ref={inputRef} type="file" />
            <Button aria-expanded={drawer} aria-label={hasStateInjection ? "输入设置（状态覆盖已启用）" : "输入设置"} className={drawer || hasStateInjection ? "tool-button active" : "tool-button"} disabled={disabled || sending} onClick={() => setDrawer(!drawer)} type="text">⌘</Button>
          </div>
          <Button className="send-button" disabled={disabled || sending || cannotSend} htmlType="submit" loading={sending} type="primary"><span>{sending ? "思考中" : "发送"}</span><b>↑</b></Button>
        </div>
      </div></div>
      <p className="composer-note">Enter 发送 · Shift + Enter 换行 · 消息与现场分别形成独立 Turn</p>
    </form>
  </section>;
}
