import { useEffect, useRef, useState } from "react";

import { viewIntents, type NestEvent, type ViewIntent } from "./contracts";
import { useNestLab } from "./use-nest-lab";

const viewOptions: readonly Readonly<{ readonly label: string; readonly value: ViewIntent }>[] = [
  { label: "总览俯视", value: viewIntents.overview },
  { label: "活动区", value: viewIntents.activity },
  { label: "宿舍", value: viewIntents.dorm },
  { label: "传送室", value: viewIntents.portal },
];

const eventLabels: Readonly<Record<string, string>> = {
  gateway_started: "网关启动",
  runtime_connected: "Godot 已连接",
  runtime_disconnected: "Godot 已断开",
  configure_world: "房间配置已发送",
  world_reconfigured: "房间已重建",
  actor_added: "角色已加入",
  wander_enabled: "随机游走已开启",
  simulation_paused: "模拟已暂停",
  simulation_resumed: "模拟已继续",
  simulation_reset: "实验已重置",
  world_ready: "房间已就绪",
  scene_manifest: "场景目录已同步",
  world_snapshot: "世界状态已同步",
  intent_accepted: "移动指令已接收",
  intent_started: "角色开始执行动作",
  intent_completed: "角色已到达目标",
  intent_failed: "角色未能完成动作",
  intent_cancelled: "角色动作已取消",
  wander_move: "随机游走目标已分配",
};

function eventTitle(event: NestEvent): string {
  return eventLabels[event.name] ?? event.name.replaceAll("_", " ");
}

function eventTime(isoTime: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(isoTime));
}

export function NestLabApp(): React.JSX.Element {
  const { state, error, refresh, run } = useNestLab();
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [bedDraft, setBedDraft] = useState(4);
  const [bedDirty, setBedDirty] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (state.world !== null && !bedDirty) setBedDraft(state.world.bed_count);
  }, [bedDirty, state.world]);

  async function commitBeds(): Promise<void> {
    if (!bedDirty || state.world === null) return;
    await run("world", "put", { bed_count: bedDraft });
    setBedDirty(false);
    setNotice(`床位数已更新为 ${bedDraft}。`);
  }

  async function action(path: string, success: string, json?: unknown): Promise<void> {
    try {
      await run(path, path === "world" ? "put" : "post", json);
      setNotice(success);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "操作未完成");
    }
  }

  function selectView(intent: ViewIntent): void {
    frameRef.current?.contentWindow?.postMessage(
      { channel: "elfienest-nest-lab", type: "camera", intent },
      window.location.origin,
    );
    setNotice(intent === viewIntents.restore ? "已还原当前预设视角。" : "已切换房间视角。");
  }

  const status = state.world?.paused
    ? "模拟已暂停"
    : state.world?.wandering
      ? "随机游走中"
      : "等待指令";

  return (
    <main className="nest-console">
      <header className="console-header">
        <div>
          <p className="kicker">DEVELOPER OBSERVATORY · ISOLATED</p>
          <h1>Nest Lab</h1>
          <p>固定房间、碰撞、路径与 Nest / Godot 协作实验台</p>
        </div>
        <div className={`connection ${state.runtime?.runtime_connected ? "online" : ""}`}>
          <span aria-hidden="true" />
          {state.runtime?.runtime_connected ? "Godot Runtime 已连接" : "等待 Godot Runtime"}
        </div>
      </header>

      <section className="nest-grid" aria-label="Nest Lab 工作区">
        <section className="room-panel console-panel">
          <div className="panel-heading">
            <div><p className="kicker">LIVE ROOM</p><h2>房间观测</h2></div>
            <strong>{status}</strong>
          </div>
          <div className="view-toolbar" aria-label="房间视角">
            {viewOptions.map((option) => (
              <button key={option.value} onClick={() => selectView(option.value)} type="button">{option.label}</button>
            ))}
            <button className="restore-view" onClick={() => selectView(viewIntents.restore)} type="button">还原视角</button>
          </div>
          <div className="room-frame">
            {state.previewUrl === null ? <p>{state.previewHint ?? "正在准备 Godot Web…"}</p> : <iframe ref={frameRef} src={state.previewUrl} title="Nest Lab Godot 房间预览" />}
          </div>
          <p className="panel-note">拖拽可观察任意角度；“还原视角”会回到当前预设相机。房屋、相机、路径与碰撞均由 Godot 执行。</p>
        </section>

        <aside className="controls-column">
          <section className="console-panel">
            <p className="kicker">WORLD</p><h2>房间设置</h2>
            <label className="bed-control" htmlFor="bedCount">床位数 <output>{bedDraft}</output></label>
            <input
              id="bedCount"
              max="32"
              min="1"
              onChange={(event) => { setBedDraft(Number(event.target.value)); setBedDirty(true); }}
              type="range"
              value={bedDraft}
            />
            <button disabled={!bedDirty} onClick={() => { void commitBeds(); }} type="button">应用床位数</button>
            <p className="muted">{state.world?.actor_count ?? 0} 个临时角色 · 世界版本 {state.world?.world_revision ?? "—"}</p>
          </section>
          <section className="console-panel">
            <p className="kicker">ACTORS</p><h2>添加角色</h2>
            <div className="button-row"><button onClick={() => { void action("actors", "已添加一只狐狸。", { species: "fox" }); }} type="button">＋ 狐狸</button><button onClick={() => { void action("actors", "已添加一只小狗。", { species: "dog" }); }} type="button">＋ 小狗</button></div>
            <ul className="actor-list">{state.actors.map((actor) => <li key={actor.actor_id}><span>{actor.species === "fox" ? "狐狸" : "小狗"}</span>{actor.actor_id}</li>)}</ul>
          </section>
          <section className="console-panel">
            <p className="kicker">SIMULATION</p><h2>实验控制</h2>
            <div className="button-grid"><button onClick={() => { void action("simulation/wander", "随机游走已开启。"); }} type="button">随机游走</button><button onClick={() => { void action("simulation/pause", "模拟已暂停。"); }} type="button">暂停</button><button onClick={() => { void action("simulation/resume", "模拟已继续。"); }} type="button">继续</button><button className="danger" onClick={() => { void action("simulation/reset", "实验已重置。"); }} type="button">重置</button></div>
          </section>
        </aside>

        <section className="event-panel console-panel">
          <div className="panel-heading"><div><p className="kicker">EVENTS</p><h2>事件时间线</h2></div><button onClick={() => { void refresh(); }} type="button">刷新</button></div>
          <ol className="event-timeline">{[...state.events].reverse().map((event) => <li key={event.sequence}><time dateTime={event.occurred_at}>{eventTime(event.occurred_at)}</time><div><strong>{eventTitle(event)}</strong><p>{event.detail}</p><small>事件 #{event.sequence} · {event.name}</small></div></li>)}</ol>
        </section>
      </section>
      <p className={error === null ? "console-notice" : "console-notice error"} role="status">{error ?? notice}</p>
    </main>
  );
}
