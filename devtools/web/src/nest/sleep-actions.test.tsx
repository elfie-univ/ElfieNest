import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { DebugToolbar, actionLocationGroups, actionRequest } from "./DebugToolbar";

vi.mock("./TwoLevelMenu", () => ({
  TwoLevelMenu: ({ groups }: { groups: { options: { value: string; label: string }[] }[] }) =>
    <div>{groups.flatMap(group => group.options).map(option =>
      <button key={option.value} data-action={option.value}>{option.label}</button>)}</div>,
}));

const sleepActions = [
  ["sleep-back", "平躺"], ["sleep-left", "左侧躺"], ["sleep-right", "右侧躺"],
] as const;
const targets = [
  { anchor_id: "dorm-01/bed-02", kind: "bed", label: "床 02", owner_id: "other" },
  { anchor_id: "central-01/chair", kind: "chair", label: "椅子", owner_id: null },
  { anchor_id: "courtyard/path", kind: "waypoint", label: "步道", owner_id: null },
];

describe("sleep action choices", () => {
  it("offers all three named sleeping postures", () => {
    const html = renderToStaticMarkup(<DebugToolbar actors={[]} targets={targets} catalog={null}
      actorId="actor" ready busy={false} selectActor={() => {}} manageActors={() => {}}
      run={async () => {}} send={() => {}} />);
    for (const [action, label] of sleepActions) {
      expect(html).toContain(`data-action="${action}"`);
      expect(html).toContain(label);
    }
  });

  it.each(sleepActions)("restricts %s to beds and preserves its semantic cycle", (action) => {
    expect(actionLocationGroups(targets, action)).toEqual([
      { label: "M01 卧室与露台", options: [{ value: "dorm-01/bed-02", label: "床 02" }] },
    ]);
    expect(actionRequest(action, "actor", undefined, "dorm-01/bed-02")).toEqual({
      actor_id: "actor", action: "use", anchor_id: "dorm-01/bed-02", furniture_cycle: action,
    });
  });

  it("keeps movement destinations available", () => {
    expect(actionLocationGroups(targets, "move").flatMap(group => group.options)).toHaveLength(3);
  });
});
