import { useEffect, useReducer, useRef, useState } from "react";
import { Alert } from "antd";
import { DebugToolbar } from "./DebugToolbar";
import { ActorManager } from "./ActorManager";
import { EnvironmentToolbar } from "./EnvironmentToolbar";
import { MenuDock } from "./MenuDock";
import { initialMenuState, menuReducer, runLabControl } from "./menu-state";
import { ObservationToolbar } from "./ObservationToolbar";
import { RunRecords } from "./RunRecords";
import { useNestLab } from "./use-nest-lab";
import { usePreview } from "./use-preview";
import { isAssetMode, modeUrl } from "./preview-mode";
import { StaticAssetReview } from "./StaticAssetReview";
import "./nest-lab.css";

export function NestLabApp(): React.JSX.Element {
  return isAssetMode(window.location.search) ? <StaticAssetReview /> : <LiveNestLab />;
}

function LiveNestLab(): React.JSX.Element {
  const { state, error, run } = useNestLab();
  const frameRef = useRef<HTMLIFrameElement>(null);
  const { catalog, send } = usePreview(frameRef, state.previewUrl, state.environment);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const [selectedActor, setSelectedActor] = useState("");
  const [menu, dispatch] = useReducer(menuReducer, initialMenuState);
  const actorId = state.actors.some((actor) => actor.actor_id === selectedActor)
    ? selectedActor : state.actors[0]?.actor_id ?? "";
  const ready = state.runtime?.world_configured === true;
  const playing = state.world?.wandering === true && !state.world.paused;
  const startupFailure = !ready && state.events.some((event) => event.name === "startup_error");

  useEffect(() => {
    if (!notice || actionError) return;
    const timer = window.setTimeout(() => setNotice(""), 3000);
    return () => window.clearTimeout(timer);
  }, [notice, actionError]);

  async function action(path: string, success: string, json?: unknown): Promise<boolean> {
    setBusy(true);
    try {
      await runLabControl(path, state.world, async (step) => { await run(step, "post", step === path ? json : undefined); });
      setNotice(success);
      setActionError(false);
      return true;
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "操作未完成");
      setActionError(true);
      return false;
    } finally { setBusy(false); }
  }

  function selectActor(id: string) {
    setSelectedActor(id);
    if (catalog?.active_id.startsWith("elfie-")) {
      send({ action: "select", view_id: `${catalog.active_id.startsWith("elfie-pov-") ? "elfie-pov-" : "elfie-"}${id}` });
    }
  }

  return <main className="nest-monitor" aria-label="Nest Lab">
    <section className="nest-monitor-stage" aria-label="精灵巢监控">
      {state.previewUrl === null ? <div className="nest-monitor-placeholder">{state.previewHint ?? "正在准备监控画面…"}</div>
        : <iframe ref={frameRef} src={state.previewUrl} title="Nest Lab Godot 房间预览" />}
    </section>
    {error !== null || notice ? <Alert className="nest-monitor-notice" message={error ?? notice} role="status" showIcon closable onClose={() => setNotice("")} type={error !== null || actionError ? "error" : "info"} /> : null}
    {startupFailure ? <Alert className="nest-startup-error" type="error" showIcon message="庄园加载失败，请查看运行记录。" /> : null}
    <div className="nest-pilot-modes" role="group" aria-label="预览模式">
      <button type="button" aria-pressed={true}>整体场景</button>
      <button type="button" aria-pressed={false} onClick={() => window.location.assign(modeUrl(window.location.href, true))}>单件资产</button>
    </div>
    {menu.records ? <RunRecords events={state.events} close={() => dispatch({ type: "records" })} /> : null}
    <ActorManager open={manageOpen} close={() => setManageOpen(false)} actors={state.actors} species={state.species} selectActor={selectActor} mutate={async (path, method, json) => { setBusy(true); try { return await run(path, method, json); } finally { setBusy(false); } }} />
    <MenuDock environment={<EnvironmentToolbar catalog={catalog} send={send} />} state={menu} dispatch={dispatch} playing={playing} ready={ready} busy={busy} togglePlayback={() => { void action("playback", playing ? "随机游走已暂停。" : "随机游走已播放。"); }} panels={{
      view: <ObservationToolbar catalog={catalog} actors={state.actors} ready={catalog !== null} actorId={actorId} selectActor={setSelectedActor} manageActors={() => setManageOpen(true)} send={send} />,
      action: <DebugToolbar actors={state.actors} targets={state.targets} catalog={catalog} actorId={actorId} ready={ready} busy={busy} selectActor={selectActor} manageActors={() => setManageOpen(true)} run={action} send={send} />,
    }} />
  </main>;
}
