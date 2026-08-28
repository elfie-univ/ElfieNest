import { useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Empty, Slider, Tag } from "antd";

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
          <h1>Nest Lab</h1>
        </div>
        <Tag className={`connection ${state.runtime?.runtime_connected ? "online" : ""}`} color={state.runtime?.runtime_connected ? "success" : "default"}>
          <span aria-hidden="true" />
          {state.runtime?.runtime_connected ? "Godot Runtime 已连接" : "等待 Godot Runtime"}
        </Tag>
      </header>

      <section className="nest-grid" aria-label="Nest Lab 工作区">
        <Card className="room-panel console-panel" extra={<Tag bordered={false}>{status}</Tag>} title={<h2>房间观测</h2>}>
          <div className="view-toolbar" aria-label="房间视角">
            {viewOptions.map((option) => (
              <Button key={option.value} onClick={() => selectView(option.value)} size="small">{option.label}</Button>
            ))}
            <Button className="restore-view" onClick={() => selectView(viewIntents.restore)} size="small">还原视角</Button>
          </div>
          <div className="room-frame">
            {state.previewUrl === null ? <p>{state.previewHint ?? "正在准备 Godot Web…"}</p> : <iframe ref={frameRef} src={state.previewUrl} title="Nest Lab Godot 房间预览" />}
          </div>
        </Card>

        <aside className="controls-column">
          <Card className="console-panel" title={<h2>房间设置</h2>}>
            <label className="bed-control" htmlFor="bedCount">床位数 <output>{bedDraft}</output></label>
            <Slider id="bedCount" max={32} min={1} onChange={(value) => { setBedDraft(value); setBedDirty(true); }} value={bedDraft} />
            <Button block disabled={!bedDirty} onClick={() => { void commitBeds(); }} type="primary">应用床位数</Button>
            <p className="muted">{state.world?.actor_count ?? 0} 个临时角色 · 世界版本 {state.world?.world_revision ?? "—"}</p>
          </Card>
          <Card className="console-panel" title={<h2>添加角色</h2>}>
            <div className="button-row"><Button onClick={() => { void action("actors", "已添加一只狐狸。", { species: "fox" }); }}>＋ 狐狸</Button><Button onClick={() => { void action("actors", "已添加一只小狗。", { species: "dog" }); }}>＋ 小狗</Button></div>
            {state.actors.length ? <ul className="actor-list">{state.actors.map((actor) => <li key={actor.actor_id}><span>{actor.species === "fox" ? "狐狸" : "小狗"}</span>{actor.actor_id}</li>)}</ul> : <Empty description="还没有临时角色" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          </Card>
          <Card className="console-panel" title={<h2>实验控制</h2>}>
            <div className="button-grid"><Button onClick={() => { void action("simulation/wander", "随机游走已开启。"); }}>随机游走</Button><Button onClick={() => { void action("simulation/pause", "模拟已暂停。"); }}>暂停</Button><Button onClick={() => { void action("simulation/resume", "模拟已继续。"); }}>继续</Button><Button danger onClick={() => { void action("simulation/reset", "实验已重置。"); }}>重置</Button></div>
          </Card>
        </aside>

        <Card className="event-panel console-panel" extra={<Button onClick={() => { void refresh(); }} size="small">刷新</Button>} title={<h2>事件时间线</h2>}>
          {state.events.length ? <ol className="event-timeline">{[...state.events].reverse().map((event) => <li key={event.sequence}><time dateTime={event.occurred_at}>{eventTime(event.occurred_at)}</time><div><strong>{eventTitle(event)}</strong><p>{event.detail}</p><small>事件 #{event.sequence} · {event.name}</small></div></li>)}</ol> : <Empty description="还没有运行事件" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
        </Card>
      </section>
      {error !== null || notice ? <Alert className="console-notice" message={error ?? notice} role="status" showIcon type={error === null ? "success" : "error"} /> : null}
    </main>
  );
}
