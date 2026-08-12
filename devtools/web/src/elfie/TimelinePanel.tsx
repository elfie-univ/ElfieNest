import { useEffect, useRef, useState } from "react";

import type { ElfieSession, ElfieTurn, PreviewIntent } from "./contracts";
import { buildStateInjection } from "./stimulus";
import { formatSignedDelta } from "./viewModel";

type Stimulus = Readonly<{
  readonly source_domain: "communication" | "embodied";
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
}>;

type Props = Readonly<{
  readonly session: ElfieSession | null;
  readonly food: string;
  readonly onSend: (stimulus: Stimulus) => Promise<boolean>;
  readonly onSelectTurn: (turn: ElfieTurn, focus: string) => void;
  readonly onPreviewIntent: (turn: ElfieTurn, intent: PreviewIntent) => void;
  readonly onUpload: (file: File) => Promise<string>;
  readonly portraitEpoch: number;
}>;

const emotionLabels: Readonly<Record<string, string>> = {
  happiness: "快乐", sadness: "悲伤", anger: "愤怒", fear: "恐惧", surprise: "惊讶", disgust: "厌恶", boredom: "无聊", attachment: "依恋",
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

function avatar(url: string, name: string, epoch: number, developer = false): React.JSX.Element {
  const source = url ? `${url}${url.includes("?") ? "&" : "?"}v=${epoch}` : "";
  return <span aria-hidden="true" className={developer ? "message-avatar developer-avatar" : "message-avatar"}>{source ? <img alt="" src={source} /> : developer ? <svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4" /><path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" /></svg> : <b>{name.slice(0, 1) || "艾"}</b>}</span>;
}

function tags(turn: ElfieTurn): readonly string[] {
  const rows: string[] = [];
  const emotion = turn.state_after?.dominant_emotion;
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
    return <article className="turn" key={turn.turn_id}><div className="turn-meta">TURN {String(index + 1).padStart(2, "0")} · {new Date(turn.timestamp).toLocaleTimeString("zh-CN")}</div><div className="bubble-row user">{avatar("", "", epoch, true)}<button className="bubble" onClick={() => onSelect(turn, "input")} type="button"><span className="bubble-label"><span>开发者刺激</span><span className="channel">{turn.stimulus_bundle.vision_media_id ? "视觉" : "文字"}</span></span><p>{turn.stimulus_bundle.message || "非文字刺激"}</p>{turn.used_state_injection ? <span className="bubble-tag warning">状态注入</span> : null}</button></div><button className="process-line" onClick={() => onSelect(turn, "chain")} type="button">感知 <i /> 决策 <i /> {turn.duration_ms ?? 0}ms</button><div className="bubble-row elfie">{avatar(session.profile.portrait_url, session.profile.name, epoch)}<div><button className={turn.result.success === false ? "bubble error" : "bubble"} onClick={() => onSelect(turn, "output")} type="button"><span className="bubble-label">{session.profile.name}</span><p>{turnText(turn)}</p>{tags(turn).map((tag) => <span className="bubble-tag" key={tag}>{tag}</span>)}</button>{intents.length ? <div className="turn-actions" aria-label="动作回放">{intents.map((intent) => <button className="turn-action" key={intent.intent_id} onClick={() => onPreviewIntent(turn, intent)} type="button">{intentLabel(intent)}</button>)}</div> : null}</div></div></article>;
  })}</>;
}

export function TimelinePanel(props: Props): React.JSX.Element {
  const [sourceDomain, setSourceDomain] = useState<"communication" | "embodied">("communication");
  const [message, setMessage] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [debug, setDebug] = useState(false);
  const [injectionEnabled, setInjectionEnabled] = useState(false);
  const [sending, setSending] = useState(false);
  const [salience, setSalience] = useState(20);
  const [temperature, setTemperature] = useState(24);
  const [impact, setImpact] = useState(0);
  const [direction, setDirection] = useState("none");
  const [stroke, setStroke] = useState(0);
  const [network, setNetwork] = useState(true);
  const [sleeping, setSleeping] = useState(false);
  const [sleepingTouched, setSleepingTouched] = useState(false);
  const [injection, setInjection] = useState<Record<string, string>>({});
  const [media, setMedia] = useState<{ readonly id: string; readonly name: string; readonly url: string } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const disabled = props.session === null;
  useEffect(() => () => {
    if (media !== null) URL.revokeObjectURL(media.url);
  }, [media]);
  function updateInjection(name: string, value: string): void { setInjection((current) => ({ ...current, [name]: value })); }
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
        is_network_online: network,
        salience_score: sourceDomain === "embodied" ? salience : 20,
        impact_force: sourceDomain === "embodied" ? impact : 0,
        impact_direction: sourceDomain === "embodied" ? direction : "none",
        gentle_stroke: sourceDomain === "embodied" ? stroke : 0,
        state_injection: buildStateInjection(
          injectionEnabled,
          injection,
          sleeping,
          sleepingTouched,
        ),
        ...(sourceDomain === "embodied" && media !== null ? { vision_media_id: media.id } : {}),
      });
      if (!sent) return;
      setMessage("");
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
    const id = await props.onUpload(file);
    if (media !== null) URL.revokeObjectURL(media.url);
    setMedia({ id, name: file.name, url: URL.createObjectURL(file) });
  }
  return <section className="timeline-panel" aria-label="交互时间线"><div className="timeline-heading"><div><p className="eyebrow">实时实验会话</p><h2>交互时间线</h2></div><div className="session-indicator"><span /><b>{props.session?.turns.length ?? 0} 轮</b></div></div><div className="timeline">{props.session === null ? <section className="timeline-placeholder"><h3>等待测试精灵</h3><p>在左侧创建一只独立测试精灵。</p></section> : <TurnList epoch={props.portraitEpoch} onPreviewIntent={props.onPreviewIntent} onSelect={props.onSelectTurn} session={props.session} />}</div><form className="composer" onSubmit={(event) => { void submit(event); }}><div className="stimulus-tabs"><button className={sourceDomain === "communication" ? "active" : ""} onClick={() => setSourceDomain("communication")} type="button">通信消息</button><button className={sourceDomain === "embodied" ? "active" : ""} onClick={() => setSourceDomain("embodied")} type="button">具身感知</button></div>{drawer && <div className="stimulus-drawer"><div className="stimulus-tabs"><button className={!debug ? "active" : ""} onClick={() => setDebug(false)} type="button">高级输入</button><button className={debug ? "active" : ""} onClick={() => setDebug(true)} type="button">Debug 状态</button></div>{!debug ? <div className="stimulus-grid"><label>突显度 <output>{salience}</output><input disabled={sourceDomain !== "embodied"} max="100" min="0" onChange={(event) => setSalience(Number(event.target.value))} type="range" value={salience} /></label><label>环境温度 <span><input disabled={sourceDomain !== "embodied"} onChange={(event) => setTemperature(Number(event.target.value))} type="number" value={temperature} /> °C</span></label><label>撞击力 <span><input disabled={sourceDomain !== "embodied"} min="0" onChange={(event) => setImpact(Number(event.target.value))} type="number" value={impact} /></span></label><label>触碰位置 <select disabled={sourceDomain !== "embodied"} onChange={(event) => setDirection(event.target.value)} value={direction}><option value="none">无</option><option value="head">头部</option><option value="back">背部</option><option value="paw">爪部</option></select></label><label>抚摸力度 <span><input disabled={sourceDomain !== "embodied"} min="0" onChange={(event) => setStroke(Number(event.target.value))} type="number" value={stroke} /></span></label><label className="check-control"><input checked={network} onChange={(event) => setNetwork(event.target.checked)} type="checkbox" /> 网络可用</label></div> : <div><div className="debug-toggle-row"><label className="check-control"><input checked={injectionEnabled} onChange={(event) => setInjectionEnabled(event.target.checked)} type="checkbox" /> 启用本轮状态覆盖</label></div><div aria-disabled={!injectionEnabled} className="injection-grid"><label className="check-control"><input checked={sleeping} disabled={!injectionEnabled} onChange={(event) => { setSleeping(event.target.checked); setSleepingTouched(true); }} type="checkbox" /> 睡眠中</label>{["energy", "fatigue", "happiness", "sadness", "anger", "fear", "surprise", "disgust", "boredom", "attachment"].map((name) => <label key={name}>{name}<input disabled={!injectionEnabled} onChange={(event) => updateInjection(name, event.target.value)} placeholder="不修改" type="number" value={injection[name] ?? ""} /></label>)}</div></div>}</div>}{sourceDomain === "embodied" && media !== null && <div className="media-preview"><img alt="本轮视觉输入预览" src={media.url} /><span><strong>{media.name}</strong><small>已上传</small></span><button onClick={() => setMedia(null)} type="button">×</button></div>}<div className="composer-row"><div className="message-field"><div className="message-field-inner"><textarea disabled={disabled || sending} onChange={(event) => setMessage(event.target.value)} onKeyDown={sendWithEnter} placeholder={sourceDomain === "communication" ? "发送一条通信消息…" : "输入现场听到的话…"} value={message} /></div><div className="message-field-footer"><div className="message-field-actions"><button aria-label="添加视觉输入" className="tool-button" disabled={disabled || sending || sourceDomain !== "embodied"} onClick={() => inputRef.current?.click()} type="button">+</button><input accept="image/png,image/jpeg,image/webp" hidden onChange={(event) => { const file = event.target.files?.[0]; event.currentTarget.value = ""; if (file !== undefined) void chooseMedia(file); }} ref={inputRef} type="file" /><button aria-expanded={drawer} aria-label="高级输入" className={drawer ? "tool-button active" : "tool-button"} disabled={disabled || sending} onClick={() => setDrawer(!drawer)} type="button">⌘</button></div><button className="send-button" disabled={disabled || sending || (sourceDomain === "communication" ? !message.trim() : (!message.trim() && media === null && impact === 0 && stroke === 0 && salience < 70))} type="submit"><span>{sending ? "思考中" : "发送"}</span><b>↑</b></button></div></div></div><p className="composer-note">Enter 发送 · Shift + Enter 换行 · 两条输入链路分别形成独立 Turn</p></form></section>;
}
