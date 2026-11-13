import { describe, expect, it, vi } from "vitest";
import { initialMenuState, menuReducer, runLabControl } from "./menu-state";

describe("Nest Lab compact menus", () => {
  it("starts with view controls and keeps one group selected when clicked again", () => {
    expect(initialMenuState).toEqual({ panel: "view", records: false });
    const view = menuReducer(initialMenuState, { type: "panel", panel: "view" });
    const actor = menuReducer(view, { type: "panel", panel: "action" });
    expect(actor.panel).toBe("action");
    expect(menuReducer(actor, { type: "panel", panel: "action" }).panel).toBe("action");
  });

  it("toggles records independently of the secondary menu", () => {
    const action = menuReducer(initialMenuState, { type: "panel", panel: "action" });
    const open = menuReducer(action, { type: "records" });
    expect(open).toEqual({ panel: "action", records: true });
    expect(menuReducer(open, { type: "records" })).toEqual(action);
  });

  it.each([
    [{ paused: false, wandering: false }, ["simulation/wander"]],
    [{ paused: false, wandering: true }, ["simulation/pause"]],
    [{ paused: true, wandering: true }, ["simulation/resume"]],
    [{ paused: true, wandering: false }, ["simulation/resume", "simulation/wander"]],
  ] as const)("uses actual wander state for the play/pause button: %j", async (world, paths) => {
    const send = vi.fn().mockResolvedValue(undefined);
    await runLabControl("playback", world, send);
    expect(send.mock.calls.map(([path]) => path)).toEqual(paths);
  });

  it("allows a manual action after pausing automatic wandering", async () => {
    const send = vi.fn().mockResolvedValue(undefined);
    await runLabControl("actions", { paused: true, wandering: true }, send);
    expect(send.mock.calls.map(([path]) => path)).toEqual(["simulation/resume", "actions"]);
  });

  it("stops the sequence when resuming fails", async () => {
    const send = vi.fn().mockRejectedValue(new Error("disconnected"));
    await expect(runLabControl("playback", { paused: true, wandering: false }, send)).rejects.toThrow("disconnected");
    expect(send).toHaveBeenCalledTimes(1);
  });
});
