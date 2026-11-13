import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { DebugToolbar, animationActionGroups, actionRequest, actionLocationGroups, previewActorAction } from "./DebugToolbar";
import { CameraSelectors, ObservationToolbar } from "./ObservationToolbar";
import { EnvironmentToolbar } from "./EnvironmentToolbar";
import { actorOptions } from "./ActorPicker";
import { MenuDock } from "./MenuDock";
import { SceneToolbar, previewSceneAction } from "./SceneToolbar";
import { cameraGroups, previewCatalogSchema } from "./preview-contracts";

const actors = [{ actor_id: "actor", species: "saevi" as const, age_years: 5, gender: "female" as const }];
const catalog = previewCatalogSchema.parse({
  channel: "elfienest-nest-lab", kind: "catalog", active_id: "overview",
  presentation_paused: false, lighting: "lighting-live", scene_actions: [{ id: "water", label: "水景（喷泉／湖面）", paused: false }],
  views: [{ id: "overview", label: "全园总览" }, { id: "central-1", label: "主楼 · 1 层" },
    { id: "terrace-01", label: "露台 M01" }, { id: "dorm-01", label: "卧室 M01" },
    { id: "elfie-actor", label: "跟随" }, { id: "lighting-night", label: "夜晚" }],
  actors: [{ actor_id: "actor", animations: ["idle", "jump"], posture: "idle", command_id: "" }],
});

describe("Nest Lab cascade", () => {
  it("offers available head gestures through the existing actor action request", () => {
    const items = animationActionGroups(["nod_head", "shake_head"]).flatMap(group => group.options);
    expect(items).toEqual([{value:"clip:nod_head",label:"点头"},{value:"clip:shake_head",label:"摇头"}]);
    expect(animationActionGroups(["idle"]).flatMap(group => group.options).map(item => item.value)).toEqual(["clip:idle"]);
    expect(actionRequest("animation","actor","nod_head",undefined)).toEqual({actor_id:"actor",action:"animation",animation:"nod_head"});
  });
  it("allows inspecting a ready scene before the resident runtime is configured", () => {
    const html = renderToStaticMarkup(<ObservationToolbar catalog={catalog} actors={[]} actorId="" selectActor={() => {}} manageActors={() => {}} ready={false} send={() => {}} />);
    const reset = html.match(/<button\b[^>]*aria-label="复位"[^>]*>/)?.[0];
    expect(reset).toBeDefined();
    expect(reset).not.toContain("disabled");
  });
  it("uses short lighting state names without time ranges", () => {
    for (const [lighting, label] of [["lighting-live", "实时"], ["lighting-day", "白天"], ["lighting-night", "晚上"], ["lighting-quiet", "深夜"]] as const) {
      const html = renderToStaticMarkup(<EnvironmentToolbar catalog={{ ...catalog, lighting }} send={() => {}} />);
      expect(html).toContain(`title="${label}"`);
      expect(html).not.toMatch(/本地实时|安静时段|06:00|18:00|00:00/);
    }
  });
  it("filters fixed cameras and keeps reset only in fixed mode, with no frame freeze", () => {
    expect(cameraGroups(catalog.views).flatMap((group) => group.options.map((option) => option.value)))
      .toEqual(["overview", "central-1", "dorm-01", "terrace-01"]);
    const html = renderToStaticMarkup(<ObservationToolbar catalog={catalog} actors={actors} actorId="actor" selectActor={() => {}} manageActors={() => {}} ready send={() => {}} />);
    expect(html).toContain('aria-label="视角类型"');
    expect(html).toContain('aria-label="复位"');
    expect(html).toContain("ant-cascader");
    expect(html).not.toContain("定格");
    const elfie = renderToStaticMarkup(<CameraSelectors mode="elfie" catalog={catalog} disabled={false} actorId="actor" actors={actors} perspective="follow" chooseActor={() => {}} manageActors={() => {}} send={() => {}} />);
    expect(elfie).not.toContain("复位");
    expect(elfie.indexOf('aria-label="选择精灵"')).toBeLessThan(elfie.indexOf('aria-label="精灵视角"'));
  });
  it("uses the same actor list with management as the final option", () => {
    const options = actorOptions(actors);
    expect(options[0]?.value).toBe("actor");
    expect(options.at(-1)?.label).toBe("管理精灵…");
    expect(actorOptions([{ ...actors[0]!, actor_id: "12345678", name: "实验赛维", saved: true }])[0])
      .toEqual({ value: "12345678", label: "实验赛维" });
  });
  it("shows only view and action groups, with lighting before playback and logs", () => {
    const html = renderToStaticMarkup(<MenuDock state={{ panel: "view", records: false }} dispatch={() => {}} playing={false} ready busy={false} togglePlayback={() => {}} environment={<EnvironmentToolbar catalog={catalog} send={() => {}} />} panels={{ view: <span>camera-control</span>, action: <span>action-control</span> }} />);
    expect(html.match(/<section[^>]*hidden=""/g)).toHaveLength(1);
    expect(html).toContain('aria-label="操作分类"');
    expect(html).not.toContain("精灵操作");
    expect(html).not.toContain("环境操作");
    expect(html.indexOf('title="实时"')).toBeGreaterThan(-1);
    expect(html.indexOf('title="实时"')).toBeLessThan(html.indexOf("播放随机游走"));
    expect(html.indexOf("播放随机游走")).toBeLessThan(html.indexOf('aria-label="运行记录"'));
  });
  it("submits a full sleep cycle through a semantic furniture command", () => {
    expect(actionRequest("sleep-left", "actor", undefined, "dorm-01/bed-01"))
      .toEqual({ actor_id: "actor", action: "use", anchor_id: "dorm-01/bed-01", furniture_cycle: "sleep-left" });
    expect(actionRequest("animation", "actor", "jump", undefined))
      .toEqual({ actor_id: "actor", action: "animation", animation: "jump" });
  });
  it("puts actor actions and scene actions in the action cascade", () => {
    const html = renderToStaticMarkup(<DebugToolbar actors={[]} targets={[]} catalog={catalog} actorId="missing" ready busy={false} selectActor={() => {}} manageActors={() => {}} run={async () => {}} send={() => {}} />);
    expect(html).toContain('aria-label="动作分类"');
    expect(html).toContain("精灵动作");
    expect(html).toContain('aria-label="动作"');
    expect(html).toContain("ant-cascader");
    expect(html).not.toContain('aria-label="调试类型"');
    expect(html).not.toContain('aria-label="动画"');
  });
  it("groups positions inside one selector and includes beds owned by other actors", () => {
    const targets = [
      {anchor_id:"dorm-01/bed-02",kind:"bed",label:"01 卧室·床 02",owner_id:"other"},
      {anchor_id:"central-01/sofa",kind:"chair",label:"一楼沙发",owner_id:null},
      {anchor_id:"courtyard/lakeside-seat",kind:"chair",label:"湖边长凳",owner_id:null},
    ];
    expect(actionLocationGroups(targets,"sleep-back")).toEqual([{label:"M01 卧室与露台",options:[{value:"dorm-01/bed-02",label:"01 卧室·床 02"}]}]);
    expect(actionLocationGroups(targets,"seat").map(group=>group.label)).toEqual(["主楼 1 层","户外"]);
    expect(actionLocationGroups([...targets, {...targets[0]!, anchor_id:"dorm-02/bed-01", label:"02 卧室·床 01"}],"sleep-back").map(group=>group.label)).toEqual(["M01 卧室与露台","M02 卧室与露台"]);
  });
  it("uses two-level scene objects without an extra water playback selector", () => {
    const html = renderToStaticMarkup(<SceneToolbar catalog={catalog} send={() => {}} />);
    expect(html).toContain("ant-cascader");
    expect(html).toContain('aria-label="场景对象"');
    expect(html).not.toContain('aria-label="场景动作"');
    expect(cameraGroups(catalog.views).map(group=>group.label)).toEqual(["室外","主楼","M01 卧室与露台"]);
  });
  it("prepares the selected actor before replaying the complete platform arrival", async () => {
    const calls: unknown[] = [];
    const send = vi.fn(command => { calls.push(command); });
    const run = vi.fn(async () => { calls.push("prepare"); return true; });
    await previewSceneAction({id:"arrival-platform",label:"完整抵达动画",paused:true},send,"actor",run);
    expect(calls).toEqual(["prepare",{action:"pause",paused:false},{action:"scene",target:"arrival-platform",actor_id:"actor",paused:false}]);
    calls.length = 0;
    await previewSceneAction({id:"arrival-platform",label:"完整抵达动画",paused:true},send);
    expect(calls).toEqual([]);
    await previewSceneAction({id:"arrival-platform",label:"完整抵达动画",paused:true},send,"actor",async () => false);
    expect(calls).toEqual([]);
    await previewSceneAction({id:"arrival-platform",label:"完整抵达动画",paused:true},send,"actor",run,"auto",() => false);
    expect(calls).toEqual(["prepare"]);
  });
  it("opens each selected water scene directly, without needing an actor", async () => {
    const send = vi.fn();
    for (const id of ["fountain", "waterfall", "lake"]) {
      await previewSceneAction({id,label:id,paused:true}, send);
      expect(send).toHaveBeenLastCalledWith({action:"scene",target:id,paused:false});
    }
    expect(send).toHaveBeenCalledTimes(3);
  });
  it("focuses a door through its scene command before preparing the followed passage", async () => {
    const calls: unknown[] = [];
    const send = vi.fn(command => {calls.push(command);});
    const run = vi.fn(async () => {calls.push("prepare");return true;});
    await previewSceneAction({id:"door-0",label:"M01 卧室门",paused:false,mode:"auto"},send,"actor",run);
    expect(calls).toEqual([{action:"scene",target:"door-0",mode:"auto"},"prepare",{action:"select",view_id:"elfie-actor"},{action:"demonstration",actor_id:"actor",demonstration_id:"door-0"}]);
    calls.length = 0;
    await previewSceneAction({id:"door-0",label:"M01 卧室门",paused:false},send,"actor",run,"closed");
    expect(calls).toEqual([{action:"scene",target:"door-0",mode:"closed"}]);
  });
  it("does not let an obsolete door passage steal the newly selected scene camera", async () => {
    let current = true;
    const send = vi.fn();
    const run = vi.fn(async () => {current = false;return true;});
    await previewSceneAction({id:"door-0",label:"M01 卧室门",paused:false},send,"actor",run,"auto",() => current);
    expect(send.mock.calls).toEqual([[{action:"scene",target:"door-0",mode:"auto"}]]);
  });
  it("pairs the same bedroom and terrace inside each M-number category", () => {
    const views = [...catalog.views,{id:"terrace-02",label:"M02露台"},{id:"dorm-02",label:"M02卧室"}];
    expect(cameraGroups(views).slice(2).map(group=>group.options.map(option=>option.value)))
      .toEqual([["dorm-01","terrace-01"],["dorm-02","terrace-02"]]);
    expect(cameraGroups(views)[2]?.options.map(option=>option.label)).toEqual(["M01 卧室","M01 露台"]);
    const targets = ["dorm-01/chair-01","terrace-01/sofa"].map(anchor_id=>({anchor_id,kind:"chair",label:anchor_id,owner_id:null}));
    expect(actionLocationGroups(targets,"seat")).toHaveLength(1);
  });
  it("switches to the chosen actor camera before submitting a targeted preview", async () => {
    const calls:unknown[]=[];
    const send=vi.fn(command=>{calls.push(command);});
    const run=vi.fn(async (...args:unknown[])=>{calls.push(args);return true;});
    await previewActorAction("actor", "seat", undefined, "terrace-01/sofa", run, send);
    expect(calls).toEqual([
      {action:"select",view_id:"elfie-actor"},
      ["actions","动作预览已提交。",{actor_id:"actor",action:"use",anchor_id:"terrace-01/sofa",furniture_cycle:"seat"}],
    ]);
  });
  it("shows the actor perspective when a preview switches the runtime camera", () => {
    const html=renderToStaticMarkup(<ObservationToolbar catalog={{...catalog,active_id:"elfie-actor"}} actors={actors} actorId="actor" selectActor={()=>{}} manageActors={()=>{}} ready send={()=>{}}/>);
    expect(html).toContain('aria-label="精灵视角"');
    expect(html).not.toContain('aria-label="复位"');
  });
});
