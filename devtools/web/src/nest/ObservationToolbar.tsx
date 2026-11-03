import { Button, Select } from "antd";
import { useEffect, useState } from "react";
import { ActorPicker, CascadeSeparator } from "./ActorPicker";
import { TwoLevelMenu } from "./TwoLevelMenu";
import type { NestActor } from "./contracts";
import { cameraGroups, type CameraCommand, type PreviewCatalog } from "./preview-contracts";

type ViewMode = "fixed" | "elfie";
type Perspective = "follow" | "first_person";
type Props = {
  catalog: PreviewCatalog | null; actors: readonly NestActor[]; ready: boolean; actorId: string;
  selectActor: (id: string) => void; manageActors: () => void; send: (command: CameraCommand) => void;
};
function actorView(id: string, perspective: Perspective) { return `${perspective === "follow" ? "elfie-" : "elfie-pov-"}${id}`; }
function canObserve(catalog: PreviewCatalog | null, id: string, perspective: Perspective) { return catalog?.views.some((view) => view.id === actorView(id, perspective)) ?? false; }
type SelectorProps = Pick<Props, "catalog" | "actors" | "actorId" | "send" | "manageActors"> & {
  mode: ViewMode; disabled: boolean; perspective: Perspective; chooseActor: (id: string, perspective: Perspective) => void;
};
export function CameraSelectors({ mode, catalog, actors, actorId, disabled, perspective, chooseActor, manageActors, send }: SelectorProps) {
  if (mode === "fixed") return <>
    <TwoLevelMenu label="摄像头" disabled={disabled} value={catalog?.active_id ?? "overview"} groups={cameraGroups(catalog?.views ?? [])} onSelect={(value: string) => send({ action: "select", view_id: value })} />
    <Button size="small" aria-label="复位" disabled={disabled} onClick={() => send({ action: "reset" })}>复位</Button>
  </>;
  return <>
    <ActorPicker actors={actors} actorId={actorId} disabled={false} selectActor={(id) => chooseActor(id, perspective)} manageActors={manageActors} />
    <CascadeSeparator />
    <Select size="small" aria-label="精灵视角" value={perspective} disabled={disabled || !canObserve(catalog, actorId, perspective)} options={[
      { value: "follow", label: "跟随", disabled: !canObserve(catalog, actorId, "follow") },
      { value: "first_person", label: "第一人称", disabled: !canObserve(catalog, actorId, "first_person") },
    ]} onChange={(value: Perspective) => chooseActor(actorId, value)} />
  </>;
}
export function ObservationToolbar({ catalog, actors, ready, actorId, selectActor, manageActors, send }: Props) {
  const [mode, setMode] = useState<ViewMode>(catalog?.active_id.startsWith("elfie-") ? "elfie" : "fixed");
  const [perspective, setPerspective] = useState<Perspective>(catalog?.active_id.startsWith("elfie-pov-") ? "first_person" : "follow");
  const disabled = !ready || catalog === null;
  useEffect(() => {
    if (!catalog) return;
    setMode(catalog.active_id.startsWith("elfie-") ? "elfie" : "fixed");
    setPerspective(catalog.active_id.startsWith("elfie-pov-") ? "first_person" : "follow");
  }, [catalog?.active_id]);
  function chooseActor(id: string, view: Perspective) {
    selectActor(id);
    setPerspective(view);
    if (canObserve(catalog, id, view)) send({ action: "select", view_id: actorView(id, view) });
  }
  function chooseMode(value: ViewMode) {
    setMode(value);
    if (value === "fixed") send({ action: "select", view_id: "overview" });
    else chooseActor(actorId, perspective);
  }
  return <div className="nest-monitor-toolbar" role="toolbar" aria-label="观察控制">
    <Select<ViewMode> size="small" aria-label="视角类型" value={mode} options={[{ value: "fixed", label: "固定机位" }, { value: "elfie", label: "精灵视角" }]} onChange={chooseMode} />
    <CascadeSeparator />
    <CameraSelectors mode={mode} catalog={catalog} actors={actors} actorId={actorId} disabled={disabled} perspective={perspective} chooseActor={chooseActor} manageActors={manageActors} send={send} />
  </div>;
}
