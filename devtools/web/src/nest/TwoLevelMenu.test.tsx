import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { TwoLevelMenu, cascadeOptions, cascadePath, selectCascadeOption } from "./TwoLevelMenu";

const groups = [
  { label: "基础", options: [{ value: "idle", label: "待机" }, { value: "jump", label: "跳跃" }] },
  { label: "坐卧", options: [{ value: "seat", label: "坐下并起来" }, { value: "sleep", label: "上床睡觉并起床", disabled: true }] },
  { label: "空分类", options: [] },
];

describe("two-level Lab menus", () => {
  it("keeps the controlled path stable across live catalog refreshes", () => {
    const previous = cascadePath(groups, "seat");
    const refreshed = groups.map(group => ({...group, options:group.options.map(option=>({...option}))}));
    expect(cascadePath(refreshed, "seat", previous)).toBe(previous);
    expect(cascadePath(refreshed, "jump", previous)).toEqual(["基础", "jump"]);
  });
  it("opens categories before their leaves and restores the selected category", () => {
    const options = cascadeOptions(groups);
    expect(options.map(item => item.label)).toEqual(["基础", "坐卧"]);
    expect(options[1]?.children.map(item => item.value)).toEqual(["seat", "sleep"]);
    expect(cascadePath(groups, "seat")).toEqual(["坐卧", "seat"]);
    expect(cascadePath(groups, "removed")).toEqual([]);
  });

  it("executes only enabled leaves and allows replaying the same leaf", () => {
    const onSelect = vi.fn();
    const choose = (path:string[]) => selectCascadeOption(groups,path,onSelect);
    choose(["坐卧"]);
    choose(["坐卧", "sleep"]);
    choose(["基础", "seat"]);
    expect(onSelect).not.toHaveBeenCalled();
    choose(["坐卧", "seat"]);
    choose(["坐卧", "seat"]);
    expect(onSelect.mock.calls).toEqual([["seat"], ["seat"]]);
  });

  it("keeps a single compact control with the leaf label", () => {
    const html = renderToStaticMarkup(<TwoLevelMenu label="动作位置" groups={groups} value="seat" onSelect={() => {}} />);
    expect(html).toContain("ant-cascader");
    expect(html).toContain('aria-label="动作位置"');
    expect(html).toContain("坐下并起来");
    expect(html).not.toContain("坐卧 / 坐下并起来");
  });
});
