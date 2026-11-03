import { Select } from "antd";
import { useState } from "react";
import { ActorPicker, CascadeSeparator } from "./ActorPicker";
import { SceneToolbar } from "./SceneToolbar";
import { TwoLevelMenu } from "./TwoLevelMenu";
import type { NestActor, NestTarget } from "./contracts";
import type { CameraCommand, PreviewCatalog } from "./preview-contracts";

type Action = "animation" | "move" | "use" | "seat" | "sleep-back" | "sleep-left" | "sleep-right";
export function actionRequest(action: Action, actorId: string, animation: string | undefined, anchor: string | undefined) {
  const cycle = action === "seat" || action.startsWith("sleep-");
  return { actor_id: actorId, action: cycle ? "use" : action, ...(action === "animation" ? { animation } : { anchor_id: anchor }), ...(cycle ? { furniture_cycle: action } : {}) };
}
export function previewActorAction(actorId: string, action: Action, animation: string | undefined, anchor: string | undefined, run: Props["run"], send: Props["send"]) {
  send({action:"select",view_id:`elfie-${actorId}`});
  return run("actions","动作预览已提交。",actionRequest(action,actorId,animation,anchor));
}
type Props = {
  actors: readonly NestActor[];
  targets: readonly NestTarget[];
  catalog: PreviewCatalog | null;
  actorId: string;
  ready: boolean;
  busy: boolean;
  selectActor: (id: string) => void;
  manageActors: () => void;
  send: (command: CameraCommand) => void;
  run: (path: string, message: string, json?: unknown) => Promise<void | boolean>;
};

const stageLabels: Readonly<Record<string, string>> = {
  chair_turn_out: "空椅转出", approach_seat: "接近座位", step_up: "登上座位", turn_left_90: "转身", sit_down: "坐下", seated_idle: "坐姿待机", chair_turn_to_desk: "转回桌前", chair_turn_to_exit: "转向出口", stand_up: "起身", jump_down: "下座", leave_seat: "离开座位", sit_on_bed_edge: "坐床沿", lie_down: "躺下", pull_original_duvet: "拉被", covered_breathing: "盖被呼吸", fold_duvet_down: "掀被", sit_up: "坐起", leave_and_lay_back: "下床回铺",
};
const animationLabels: Readonly<Record<string, string>> = {
  idle: "待机", walking: "走路（原地）", running: "跑步（原地）", jump: "跳跃", twist_dance: "跳舞",
  pose_thinking: "思考", pose_victory: "胜利", pose_thumbs_up: "点赞", pose_hands_on_hips: "叉腰",
  pose_waving: "挥手", left_strafe: "向左侧移", right_strafe: "向右侧移",
  left_strafe_walking: "向左侧走", right_strafe_walking: "向右侧走",
  left_turn: "左转", right_turn: "右转", left_turn_90: "左转 90°", right_turn_90: "右转 90°",
};

export function actionLocationGroups(targets: readonly NestTarget[], action: string) {
  const groups = new Map<string, {value:string; label:string}[]>();
  for (const target of targets) {
    if (action === "seat" && target.kind !== "chair") continue;
    if (action === "sleep-back" && target.kind !== "bed") continue;
    const prefix = target.anchor_id.split("/")[0] ?? "";
    const group = prefix.startsWith("dorm-") ? `M${prefix.slice(5)} 卧室与露台` : prefix.startsWith("central-") ? `主楼 ${Number(prefix.slice(8))} 层` : prefix.startsWith("terrace-") ? `M${prefix.slice(8)} 卧室与露台` : "户外";
    const options = groups.get(group) ?? [];
    options.push({value:target.anchor_id, label:target.label}); groups.set(group,options);
  }
  return [...groups].map(([label,options]) => ({label, options}));
}

export function DebugToolbar(props: Props) {
  const {actorId, actors, targets, catalog, ready, busy, run, selectActor} = props;
  const [category, setCategory] = useState<"elfie" | "scene" | "demo">("elfie");
  const [selection, setSelection] = useState("");
  const [location, setLocation] = useState("");
  const [demonstration, setDemonstration] = useState("");
  const actor = catalog?.actors.find(item => item.actor_id === actorId);
  const disabled = !ready || busy || !actor || catalog?.presentation_paused === true;
  const clips = actor?.animations ?? [];
  const demonstrations = actor?.demonstrations ?? [];
  const demoGroups = [...new Set(demonstrations.map(item=>item.group))].map(label=>({label,options:demonstrations.filter(item=>item.group===label).map(item=>({value:item.id,label:item.available ? item.label : `${item.label}（路线未连通）`,disabled:!item.available}))}));
  const animationGroups = [
    {label:"基础", keys:["idle","walking","running","jump","twist_dance"]},
    {label:"方向", keys:["left_strafe","right_strafe","left_strafe_walking","right_strafe_walking","left_turn","right_turn","left_turn_90","right_turn_90"]},
    {label:"姿态", keys:["pose_waving","pose_thinking","pose_victory","pose_thumbs_up","pose_hands_on_hips"]},
  ].map(group => ({label:group.label, options:group.keys.filter(key => clips.includes(key)).map(key => ({value:`clip:${key}`,label:animationLabels[key] ?? key}))})).filter(group => group.options.length);
  const needsLocation = selection !== "" && !selection.startsWith("clip:");
  function chooseAction(value:string) {
    setSelection(value); setLocation("");
    if (value.startsWith("clip:")) void previewActorAction(actorId,"animation",value.slice(5),undefined,run,props.send);
  }
  function chooseLocation(value:string) {
    setLocation(value);
    void previewActorAction(actorId,selection as Action,undefined,value,run,props.send);
  }
  return <div className="nest-monitor-toolbar nest-debug-toolbar" role="toolbar" aria-label="角色与动作调试">
    <Select size="small" aria-label="动作分类" value={category} options={[{value:"elfie",label:"精灵动作"},{value:"scene",label:"场景动作"},{value:"demo",label:"组合演示"}]} onChange={setCategory}/>
    <CascadeSeparator/>
    {category === "scene" ? <SceneToolbar catalog={catalog} send={props.send} actorId={actorId} run={run}/> : <>
      <ActorPicker actors={actors} actorId={actorId} disabled={busy} selectActor={id => {setSelection("");setLocation("");setDemonstration("");selectActor(id);}} manageActors={props.manageActors}/>
      <CascadeSeparator/>
      {category === "demo" ? <TwoLevelMenu label="组合演示" placeholder="选择演示" value={demonstration} disabled={disabled} groups={demoGroups} onSelect={(value:string)=>{setDemonstration(value);void (async()=>{if(await run(`actors/${encodeURIComponent(actorId)}/prepare-demo`,"正在准备组合演示。") === false)return; props.send({action:"select",view_id:`elfie-${actorId}`}); props.send({action:"demonstration",actor_id:actorId,demonstration_id:value});})();}}/> : <TwoLevelMenu label="动作" placeholder="选择动作" value={selection} disabled={disabled}
        groups={[...animationGroups,{label:"坐卧",options:[{value:"seat",label:"坐下并起来"},{value:"sleep-back",label:"上床睡觉并起床"}]},{label:"移动",options:[{value:"move",label:"走到指定位置"}]}]}
        onSelect={chooseAction}/> }
      {category === "elfie" && needsLocation ? <><CascadeSeparator/><TwoLevelMenu label="动作位置" placeholder="选择位置" value={location} disabled={disabled}
        groups={actionLocationGroups(targets,selection)} onSelect={chooseLocation}/></> : null}
      {actor ? <span className="nest-action-state">{category === "demo" ? actor.demonstration_state || "等待选择演示" : actor.command_id ? (stageLabels[actor.posture] ?? "执行中") : actor.posture === "idle" ? "等待选择动作" : actor.posture}</span> : null}
    </>}
  </div>;
}
