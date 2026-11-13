import { Select } from "antd";
import type { NestActor } from "./contracts";

const manageValue = "__manage__";
export function actorLabel(actor: NestActor): string {
  return actor.name || `${actor.species === "saevi" ? "赛维" : "托伦"} · ${actor.actor_id.split("-").at(-1)}`;
}
export function actorOptions(actors: readonly NestActor[]) {
  return [...actors.map((actor) => ({ value: actor.actor_id, label: actorLabel(actor) })),
    { value: manageValue, label: "管理精灵…" }];
}
export type ActorPickerProps = {
  actors: readonly NestActor[]; actorId: string; disabled: boolean;
  selectActor: (id: string) => void; manageActors: () => void;
};
export function ActorPicker({ actors, actorId, disabled, selectActor, manageActors }: ActorPickerProps) {
  return <Select size="small" aria-label="选择精灵" className="nest-actor-select" value={actorId || null} placeholder="选择精灵" disabled={disabled} options={actorOptions(actors)} onChange={(id: string) => { if (id === manageValue) manageActors(); else selectActor(id); }} />;
}
export function CascadeSeparator() { return <span className="nest-cascade-separator" aria-hidden="true">&gt;</span>; }
