import { Button, Select } from "antd";
import { useEffect, useRef, useState } from "react";
import { CascadeSeparator } from "./ActorPicker";
import { TwoLevelMenu } from "./TwoLevelMenu";
import type { CameraCommand, PreviewCatalog } from "./preview-contracts";
type Props = { catalog: PreviewCatalog | null; send: (command: CameraCommand) => void; actorId?: string; run?: (path:string,message:string)=>Promise<void | boolean> };
type SceneItem = PreviewCatalog["scene_actions"][number];

export async function previewSceneAction(item: SceneItem, send: Props["send"], actorId?: string, run?: Props["run"], mode = item.mode ?? "auto", isCurrent = () => true) {
  if (item.id === "arrival-platform") {
    if (!actorId || !run || await run(`actors/${encodeURIComponent(actorId)}/prepare-demo`,"正在准备抵达动画。") === false || !isCurrent()) return;
    send({action:"pause",paused:false});
    send({action:"scene",target:item.id,actor_id:actorId,paused:false});
    return;
  }
  // Runtime frames the actual scene object and applies its preview state.
  if (!item.id.startsWith("door-")) {
    send({action:"scene",target:item.id,paused:false});
    return;
  }
  send({action:"scene",target:item.id,mode});
  if (mode === "auto" && actorId && run) {
    if (await run(`actors/${encodeURIComponent(actorId)}/prepare-demo`,"正在准备穿门演示。") === false || !isCurrent()) return;
    send({action:"select",view_id:`elfie-${actorId}`});
    send({action:"demonstration",actor_id:actorId,demonstration_id:item.id});
  }
}

export function SceneToolbar({ catalog, send, actorId, run }: Props) {
  const [target, setTarget] = useState("");
  const sequence = useRef(0);
  useEffect(() => () => { sequence.current += 1; }, [actorId]);
  function preview(item: SceneItem, mode = item.mode ?? "auto") {
    const request = ++sequence.current;
    void previewSceneAction(item,send,actorId,run,mode,() => sequence.current === request);
  }
  const items = catalog?.scene_actions ?? [];
  const selected = items.find((item) => item.id === target);
  const door = selected?.id.startsWith("door-") === true;
  const groups = [{label:"门",options:items.filter(item=>item.id.startsWith("door-")).map(item=>({value:item.id,label:item.label}))},
    {label:"水景",options:items.filter(item=>!item.id.startsWith("door-") && item.id !== "arrival-platform").map(item=>({value:item.id,label:item.label}))},{label:"到达平台",options:items.filter(item=>item.id === "arrival-platform").map(item=>({value:item.id,label:item.label,disabled:!actorId || !run}))}].filter(group=>group.options.length);
  return <>
    <TwoLevelMenu label="场景对象" placeholder="选择场景对象" value={selected?.id ?? ""} disabled={!items.length} groups={groups} onSelect={value => {
      setTarget(value);
      const item = items.find(item => item.id === value);
      if (item) preview(item);
    }} />
    {door ? <><CascadeSeparator />
      <Select size="small" aria-label="场景动作" value={selected?.mode ?? "auto"}
        options={[{value:"auto",label:"自动感应"},{value:"open",label:"开启"},{value:"closed",label:"关闭"}]}
        onSelect={value => {if (selected) preview(selected,value);}} />
    </> : null}
    {selected?.id === "arrival-platform" ? <Button size="small" disabled={!actorId || !run} onClick={() => preview(selected)}>重播</Button> : null}
    {selected ? <span className="nest-action-state">{door ? "状态随场景实时更新" : selected.paused ? "已暂停" : "播放中"}</span> : null}
  </>;
}
