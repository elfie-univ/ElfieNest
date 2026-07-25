import { z } from "zod";

export const runtimeSchema = z.object({
  runtime_connected: z.boolean(),
  runtime_ready: z.boolean(),
  websocket_url: z.string(),
  nonce: z.string(),
  paused: z.boolean(),
  wandering: z.boolean(),
});

export const worldSchema = z.object({
  bed_count: z.number().int(),
  actor_count: z.number().int(),
  world_revision: z.number().int(),
  paused: z.boolean(),
  wandering: z.boolean(),
});

export const actorsSchema = z.object({
  items: z.array(
    z.object({
      actor_id: z.string(),
      species: z.union([z.literal("dog"), z.literal("fox")]),
    }),
  ),
});

export const eventsSchema = z.object({
  items: z.array(
    z.object({
      sequence: z.number().int(),
      name: z.string(),
      detail: z.string(),
      occurred_at: z.string(),
    }),
  ),
});

export const godotWebSchema = z.object({
  ready: z.boolean(),
  entry_url: z.string(),
  build_command: z.string(),
});

export type NestRuntime = z.infer<typeof runtimeSchema>;
export type NestWorld = z.infer<typeof worldSchema>;
export type NestActor = z.infer<typeof actorsSchema>["items"][number];
export type NestEvent = z.infer<typeof eventsSchema>["items"][number];

export const viewIntents = {
  overview: "overview",
  activity: "activity",
  dorm: "dorm",
  portal: "portal",
  restore: "restore",
} as const;

export type ViewIntent = (typeof viewIntents)[keyof typeof viewIntents];
