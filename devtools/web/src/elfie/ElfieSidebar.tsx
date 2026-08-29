import { useEffect, useRef, useState, type RefObject } from "react";
import { Button, Select } from "antd";

import type { BigFive, ElfieListItem, ElfieSession, FoodItem } from "./contracts";
import { ImpactTimeline, KnowledgeGraph, RelationshipGraph, TopicWall, WorldRings } from "./MemoryVisualizations";
import { orbitButtonDelta } from "./previewProtocol";

type Preview = (action: string, payload?: Record<string, unknown>) => void;
type Props = Readonly<{
  readonly items: readonly ElfieListItem[];
  readonly session: ElfieSession | null;
  readonly foods: readonly FoodItem[];
  readonly food: string;
  readonly runtimeWarning: string;
  readonly iframeRef: RefObject<HTMLIFrameElement | null>;
  readonly collapsed: boolean;
  readonly menuOpen: boolean;
  readonly portraitEpoch: number;
  readonly previewStatus: string;
  readonly onCollapse: () => void;
  readonly onCreate: () => void;
  readonly onSelect: (id: string) => void;
  readonly onDelete: (id: string) => void;
  readonly onFood: (key: string) => void;
  readonly onNewFood: () => void;
  readonly onMenu: () => void;
  readonly onEditPersonality: () => void;
  readonly preview: Preview;
}>;

const radarAxes: readonly (readonly [string, keyof BigFive])[] = [
  ["开放", "openness"], ["尽责", "conscientiousness"], ["外向", "extraversion"],
  ["亲和", "agreeableness"], ["敏感", "neuroticism"],
];

function imageUrl(url: string | undefined, epoch: number): string | undefined {
  if (!url) return undefined;
  return `${url}${url.includes("?") ? "&" : "?"}v=${epoch}`;
}

function Portrait({ elfieId, name, url, epoch, compact = false }: Readonly<{ elfieId: string; name: string; url: string | undefined; epoch: number; compact?: boolean }>): React.JSX.Element {
  const source = imageUrl(url || `/api/elfies/${encodeURIComponent(elfieId)}/portrait`, epoch);
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [source]);
  const label = name.trim().slice(0, 1) || "艾";
  return <span className={compact ? "mini-avatar" : "avatar"}>{source && !failed ? <img alt={compact ? `${name}的头像` : "当前精灵头像"} onError={() => setFailed(true)} src={source} /> : <b>{label}</b>}{compact ? null : <i />}</span>;
}

function PersonalityRadar({ values }: Readonly<{ values: BigFive }>): React.JSX.Element {
  const center = [105, 82] as const;
  const radius = 58;
  function point(index: number, scale: number): readonly [number, number] {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / radarAxes.length;
    return [center[0] + Math.cos(angle) * radius * scale, center[1] + Math.sin(angle) * radius * scale];
  }
  function points(scale: number): string { return radarAxes.map((_, index) => point(index, scale).join(",")).join(" "); }
  const profilePoints = radarAxes.map(([, key], index) => point(index, Math.max(0, Math.min(1, values[key]))));
  return <svg aria-label="大五人格雷达图" className="personality-radar" role="img" viewBox="0 0 210 170">
    {[0.25, 0.5, 0.75, 1].map((scale) => <polygon className="radar-grid" key={scale} points={points(scale)} />)}
    {radarAxes.map(([label], index) => {
      const edge = point(index, 1);
      const text = point(index, 1.28);
      return <g key={label}><line className="radar-axis" x1={center[0]} x2={edge[0]} y1={center[1]} y2={edge[1]} /><text className="radar-label" textAnchor="middle" x={text[0]} y={text[1]}>{label}</text></g>;
    })}
    <polygon className="radar-profile" points={profilePoints.map((item) => item.join(",")).join(" ")} />
    {profilePoints.map(([x, y], index) => <circle className="radar-point" cx={x} cy={y} key={radarAxes[index]?.[1] ?? index} r="3" />)}
  </svg>;
}

function Personality({ session, onEdit }: Readonly<{ session: ElfieSession; onEdit: () => void }>): React.JSX.Element {
  return <section className="portrait-section"><div className="section-heading"><strong>大五人格</strong><Button className="section-action" onClick={onEdit} size="small" type="text">修改</Button></div><div className="personality-layout"><PersonalityRadar values={session.profile.big_five} /><div className="personality-tags">{session.profile.personality_tags.slice(0, 3).map((tag) => <span key={tag}>{tag}</span>)}</div></div></section>;
}

function Memory({ session }: Readonly<{ session: ElfieSession }>): React.JSX.Element {
  const memory = session.profile.memory_cognition;
  return <section className="memory-section"><div className="section-heading"><strong>记忆与认知</strong><small><b>{session.current_state.memory_count}</b> 条经历</small></div>
    <details data-memory-panel="topics"><summary><span>记忆主题</span><i>＋</i></summary><TopicWall topics={memory.topics} /></details>
    <details data-memory-panel="timeline"><summary><span>重要经历</span><i>＋</i></summary><ImpactTimeline events={memory.important_events} /></details>
    <details data-memory-panel="relationship"><summary><span>关系认知</span><i>＋</i></summary><RelationshipGraph graph={memory.relations} /></details>
    <details data-memory-panel="knowledge"><summary><span>知识与信念</span><i>＋</i></summary><KnowledgeGraph graph={memory.knowledge} /></details>
    <details data-memory-panel="world"><summary><span>世界理解</span><i>＋</i></summary><WorldRings model={memory.world_model} /></details>
  </section>;
}

function Preview({ iframeRef, preview, status }: Readonly<{ iframeRef: Props["iframeRef"]; preview: Preview; status: string }>): React.JSX.Element {
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    const surface = iframeRef.current?.contentWindow;
    if (surface === null || surface === undefined) return;
    let drag: { x: number; y: number; pan: boolean } | null = null;
    function pointerDown(event: PointerEvent): void { event.preventDefault(); drag = { x: event.clientX, y: event.clientY, pan: event.button === 2 || event.shiftKey }; }
    function pointerMove(event: PointerEvent): void {
      if (drag === null) return;
      event.preventDefault();
      const delta = { x: (event.clientX - drag.x) * 0.008, y: (event.clientY - drag.y) * 0.008 };
      drag = { ...drag, x: event.clientX, y: event.clientY };
      preview(drag.pan ? "pan" : "orbit", { delta });
    }
    function stopDrag(): void { drag = null; }
    function wheel(event: WheelEvent): void {
      event.preventDefault();
      if (event.shiftKey) preview("pan", { delta: { x: event.deltaX * -0.002, y: event.deltaY * -0.002 } });
      else preview("zoom", { delta: event.deltaY * 0.002 });
    }
    surface.addEventListener("pointerdown", pointerDown);
    surface.addEventListener("pointermove", pointerMove);
    surface.addEventListener("pointerup", stopDrag);
    surface.addEventListener("pointercancel", stopDrag);
    surface.addEventListener("wheel", wheel, { passive: false });
    return () => {
      surface.removeEventListener("pointerdown", pointerDown);
      surface.removeEventListener("pointermove", pointerMove);
      surface.removeEventListener("pointerup", stopDrag);
      surface.removeEventListener("pointercancel", stopDrag);
      surface.removeEventListener("wheel", wheel);
    };
  }, [iframeRef, loaded, preview]);
  return <section className="appearance-section"><div className="section-heading"><strong>3D 个体视图</strong><small>{status}</small></div><div className="appearance-viewport"><iframe onLoad={() => setLoaded(true)} ref={iframeRef} src="/godot-web/elfienest.html?mode=elfie_lab" title="当前精灵 3D 外貌" /></div><div className="appearance-tools"><Button aria-label="向左旋转" onClick={() => preview("orbit", { delta: orbitButtonDelta("left") })}>↶</Button><Button aria-label="向右旋转" onClick={() => preview("orbit", { delta: orbitButtonDelta("right") })}>↷</Button><Button aria-label="缩小" onClick={() => preview("zoom", { delta: 0.18 })}>−</Button><Button aria-label="放大" onClick={() => preview("zoom", { delta: -0.18 })}>＋</Button><Button aria-label="复位视角" onClick={() => preview("reset")}>⌂</Button><Button aria-label="头部取景" onClick={() => preview("focus", { target: "head" })}>◉</Button><Button className="capture-button" onClick={() => preview("capture")} type="primary"><span>拍照</span><b>◎</b></Button></div></section>;
}

function ExperimentConfig({ foods, food, warning, onFood, onNewFood }: Readonly<{ foods: readonly FoodItem[]; food: string; warning: string; onFood: (key: string) => void; onNewFood: () => void }>): React.JSX.Element {
  const selected = foods.find((item) => item.key === food) ?? foods[0];
  function selectFood(value: string): void {
    if (value === "__new_food__") {
      onNewFood();
      return;
    }
    onFood(value);
  }
  return <details className="experiment-section"><summary><span>实验配置</span><i>＋</i></summary><div className="model-controls"><label htmlFor="foodSelect">本次实验粮食</label><Select id="foodSelect" onChange={selectFood} options={[...foods.map((item) => ({ disabled: !item.ready_for_attempt, label: item.display_name, value: item.key })), { label: "管理 / 新增粮食…", value: "__new_food__" }]} placeholder="选择粮食" value={selected?.key ?? null} /><p className={selected?.ready_for_attempt ? "is-ready" : "is-error"}>{selected ? `${selected.model} · ${selected.description}` : "还没有粮食，请先进入粮食管理添加。"}</p>{warning ? <p className="is-error">{warning}</p> : null}</div></details>;
}

function Switcher(props: Readonly<Pick<Props, "items" | "session" | "collapsed" | "menuOpen" | "portraitEpoch" | "onCreate" | "onDelete" | "onMenu" | "onSelect">>): React.JSX.Element {
  const session = props.session;
  const wrapRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!props.menuOpen) return;
    function closeOutside(event: PointerEvent): void {
      if (event.target instanceof Node && !wrapRef.current?.contains(event.target)) props.onMenu();
    }
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [props.menuOpen, props.onMenu]);
  if (session === null) return <></>;
  return <div className="elfie-switcher-wrap" ref={wrapRef}><div className={props.collapsed ? "elfie-menu compact-switcher-menu" : "elfie-menu"} hidden={!props.menuOpen} role="menu">{props.items.map((item) => props.collapsed ? <Button aria-label={`切换至${item.name}`} className={item.elfie_id === session.elfie_id ? "active" : ""} data-tooltip={item.name} key={item.elfie_id} onClick={() => props.onSelect(item.elfie_id)} role="menuitem" type="text"><Portrait compact elfieId={item.elfie_id} epoch={props.portraitEpoch} name={item.name} url={item.portrait_url} /></Button> : <div className="elfie-menu-row" key={item.elfie_id}><Button className={item.elfie_id === session.elfie_id ? "active" : ""} onClick={() => props.onSelect(item.elfie_id)} role="menuitem" type="text"><Portrait compact elfieId={item.elfie_id} epoch={props.portraitEpoch} name={item.name} url={item.portrait_url} /><span>{item.name} · {item.species_id === "dog" ? "小狗" : "狐狸"}</span></Button><Button aria-label={`删除${item.name}`} danger onClick={() => props.onDelete(item.elfie_id)} type="text">⌫</Button></div>)}{props.collapsed ? null : <><hr /><Button block onClick={props.onCreate} type="text">＋ 新建测试精灵</Button></>}</div><Button aria-label="切换测试精灵" className="elfie-switcher" aria-expanded={props.menuOpen} aria-haspopup="menu" onClick={props.onMenu} type="text"><Portrait compact elfieId={session.elfie_id} epoch={props.portraitEpoch} name={session.profile.name} url={session.profile.portrait_url} /><span><strong>{session.profile.name}</strong><small>切换测试精灵</small></span><b>⌃</b></Button></div>;
}

export function ElfieSidebar(props: Props): React.JSX.Element {
  const { session } = props;
  return <aside className="elfie-panel" aria-label="当前测试精灵"><Button className="panel-collapse" aria-label={props.collapsed ? "展开精灵信息" : "收起精灵信息"} onClick={props.onCollapse} shape="circle" type="text">{props.collapsed ? "›" : "‹"}</Button>{session === null ? <section className="elfie-empty"><div className="empty-orbit"><span>◇</span></div><h1>创建第一只<br />测试精灵</h1><p>它将使用独立记忆和会话，不会影响普通用户数据。</p><Button className="primary-button" onClick={props.onCreate} type="primary">＋ 新建测试精灵</Button></section> : <><section className="elfie-content"><div className="identity-block"><Portrait elfieId={session.elfie_id} epoch={props.portraitEpoch} name={session.profile.name} url={session.profile.portrait_url} /><div className="identity-copy"><span className="dev-badge">测试精灵</span><h1>{session.profile.name}</h1><p>{session.profile.description || session.profile.personality_summary}</p><div className="identity-meta"><span>{session.profile.species_label || session.profile.species_id}</span><span>{session.profile.life_stage}</span><code>{session.elfie_id}</code></div></div></div><Preview iframeRef={props.iframeRef} preview={props.preview} status={props.previewStatus} /><Personality onEdit={props.onEditPersonality} session={session} /><Memory session={session} /><ExperimentConfig food={props.food} foods={props.foods} onFood={props.onFood} onNewFood={props.onNewFood} warning={props.runtimeWarning} /></section><Switcher {...props} /></>}</aside>;
}
