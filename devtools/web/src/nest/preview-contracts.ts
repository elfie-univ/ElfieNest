import { z } from "zod";

export const previewCatalogSchema = z.object({
  channel: z.literal("elfienest-nest-lab"),
  kind: z.literal("catalog"),
  views: z.array(z.object({ id: z.string(), label: z.string() })),
  active_id: z.string(),
  presentation_paused: z.boolean(),
  lighting: z.string(),
  scene_actions: z.array(z.object({ id: z.string(), label: z.string(), paused: z.boolean(), mode: z.enum(["auto","open","closed"]).optional() })),
  actors: z.array(z.object({
    actor_id: z.string(),
    animations: z.array(z.string()),
    posture: z.string(),
    command_id: z.string(),
    demonstrations: z.array(z.object({id:z.string(),group:z.string(),label:z.string(),available:z.boolean()})).optional(),
    demonstration_state: z.string().optional(),
  })),
});

export type PreviewCatalog = z.infer<typeof previewCatalogSchema>;
export type CameraCommand =
  | Readonly<{ action: "select"; view_id: string }>
  | Readonly<{ action: "reset" }>
  | Readonly<{ action: "pause"; paused: boolean }>
  | Readonly<{ action: "scene"; target: string; paused: boolean; actor_id?: string }>
  | Readonly<{ action: "scene"; target: string; mode: "auto" | "open" | "closed" }>
  | Readonly<{ action: "demonstration"; actor_id: string; demonstration_id: string }>;

export function cameraGroups(views: PreviewCatalog["views"]): { label: string; options: { value: string; label: string }[] }[] {
  return [
    { label: "室外", views: views.filter((view) => ["overview", "estate-ring"].includes(view.id)) },
    { label: "主楼", views: views.filter((view) => /^central-[1-4]$/.test(view.id)) },
    ...Array.from({length:8},(_,index) => {
      const number=String(index+1).padStart(2,"0");
      const pairedViews = [`dorm-${number}`, `terrace-${number}`].flatMap(id =>
        views.filter(view => view.id === id).map(view => ({
          ...view, label: `M${number} ${id.startsWith("dorm-") ? "卧室" : "露台"}`,
        })),
      );
      return {label:`M${number} 卧室与露台`, views:pairedViews};
    }),
  ].filter((group) => group.views.length > 0).map((group) => ({
    label: group.label,
    options: group.views.map((view) => ({ value: view.id, label: view.label })),
  }));
}
