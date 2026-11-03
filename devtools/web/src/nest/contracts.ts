import { z } from "zod";

import { FIXED_BED_COUNT } from "../constants";

export const runtimeSchema = z.object({
  runtime_connected: z.boolean(),
  runtime_ready: z.boolean(),
  world_configured: z.boolean(),
  websocket_url: z.string(),
  nonce: z.string(),
  paused: z.boolean(),
  wandering: z.boolean(),
});

export const worldSchema = z.object({
  bed_count: z.literal(FIXED_BED_COUNT),
  actor_count: z.number().int(),
  world_revision: z.number().int(),
  paused: z.boolean(),
  wandering: z.boolean(),
});

export const actorSchema = z.object({
  actor_id: z.string(), species: z.enum(["tovren", "saevi"]),
  age_years: z.number().int(), gender: z.enum(["male", "female"]),
  name: z.string().optional(), saved: z.boolean().optional(),
});
export const actorsSchema = z.object({ items: z.array(actorSchema) });

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
export const environmentSchema = z.object({ phase: z.enum(["day", "dawn", "dusk", "night"]), lights_on: z.boolean(), quiet_mode: z.boolean() }).strict();
export type NestEnvironment = z.infer<typeof environmentSchema>;
export const targetsSchema = z.object({ items: z.array(z.object({
  anchor_id: z.string(), kind: z.string(), label: z.string(), owner_id: z.string().nullable(),
})) });
export type NestTarget = z.infer<typeof targetsSchema>["items"][number];
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

export const actorSpeciesSchema = z.object({ items: z.array(z.object({ id: z.enum(["saevi", "tovren"]), label: z.string(), min_age: z.number().int(), max_age: z.number().int() })) });
export type ActorSpecies = z.infer<typeof actorSpeciesSchema>["items"][number];
