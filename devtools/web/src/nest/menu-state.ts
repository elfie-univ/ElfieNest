import type { NestWorld } from "./contracts";

export type MenuPanel = "view" | "action";
export type MenuState = Readonly<{ panel: MenuPanel; records: boolean }>;
export type MenuEvent = Readonly<{ type: "panel"; panel: MenuPanel }> | Readonly<{ type: "records" }>;
export const initialMenuState: MenuState = { panel: "view", records: false };

export function menuReducer(state: MenuState, event: MenuEvent): MenuState {
  return event.type === "records"
    ? { ...state, records: !state.records }
    : { ...state, panel: event.panel };
}

export async function runLabControl(
  path: string,
  world: Pick<NestWorld, "paused" | "wandering"> | null,
  send: (path: string) => Promise<void>,
): Promise<void> {
  if (path === "playback") {
    if (world?.wandering && !world.paused) return send("simulation/pause");
    if (world?.paused) await send("simulation/resume");
    if (!world?.wandering) await send("simulation/wander");
    return;
  }
  if (path === "actions" && world?.paused) await send("simulation/resume");
  await send(path);
}
