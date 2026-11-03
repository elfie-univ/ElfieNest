import { Select } from "antd";
import { useState } from "react";
import { CascadeSeparator } from "./ActorPicker";
import { TwoLevelMenu } from "./TwoLevelMenu";
import type { CameraCommand, PreviewCatalog } from "./preview-contracts";
export function SceneToolbar({ catalog, send, actorId, run }: { catalog: PreviewCatalog | null; send: (command: CameraCommand) => void; actorId?:string; run?:(path:string,message:string)=>Promise<void | boolean> }) {
  const [target, setTarget] = useState("water");
  const items = catalog?.scene_actions ?? [];
  const selected = items.find((item) => item.id === target) ?? items[0];
  const door = selected?.id.startsWith("door-") === true;
  const groups = [{label:"门",options:items.filter(item=>item.id.startsWith("door-")).map(item=>({value:item.id,label:item.label}))},
    {label:"水景",options:items.filter(item=>!item.id.startsWith("door-")).map(item=>({value:item.id,label:item.label}))}].filter(group=>group.options.length);
  return <>
    <TwoLevelMenu label="场景对象" placeholder="等待场景对象" value={selected?.id ?? ""} disabled={!selected} groups={groups} onSelect={setTarget} />
    <CascadeSeparator />
    <Select size="small" aria-label="场景动作" value={door ? selected?.mode ?? "auto" : selected?.paused ? "pause" : "play"} disabled={!selected}
      options={door ? [{value:"auto",label:"自动感应"},{value:"open",label:"开启"},{value:"closed",label:"关闭"}] : [{ value: "play", label: "播放" }, { value: "pause", label: "暂停" }]}
      onSelect={(value: string) => { if (!selected) return; if (door && (value === "auto" || value === "open" || value === "closed")) {
        send({action:"scene",target:selected.id,mode:value});
        if(value === "auto" && actorId && run) void(async()=>{if(await run(`actors/${encodeURIComponent(actorId)}/prepare-demo`,"正在准备穿门演示。") === false)return;send({action:"select",view_id:`elfie-${actorId}`});send({action:"demonstration",actor_id:actorId,demonstration_id:selected.id});})();
      } else if (!door) send({ action: "scene", target: selected.id, paused: value === "pause" }); }} />
    {selected ? <span className="nest-action-state">{door ? "状态随场景实时更新" : selected.paused ? "已暂停" : "播放中"}</span> : null}
  </>;
}
