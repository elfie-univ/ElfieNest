import { z } from "zod";

const bigFiveSchema = z.object({
  openness: z.number(), conscientiousness: z.number(), extraversion: z.number(),
  agreeableness: z.number(), neuroticism: z.number(),
});

const graphSchema = z.object({
  nodes: z.array(z.object({ id: z.string(), label: z.string(), weight: z.number().optional() }).passthrough()).default([]),
  links: z.array(z.object({ source: z.string(), target: z.string() }).passthrough()).default([]),
}).passthrough();

const memorySchema = z.object({
  topics: z.array(z.object({ label: z.string(), weight: z.number().optional() }).passthrough()).default([]),
  important_events: z.array(z.object({ content: z.string(), timestamp: z.string().optional() }).passthrough()).default([]),
  relations: graphSchema.default({ nodes: [], links: [] }),
  knowledge: graphSchema.default({ nodes: [], links: [] }),
  world_understanding: z.string().default("尚未形成稳定的世界理解"),
}).passthrough();

const intentSchema = z.object({
  intent_id: z.string().optional(),
  type: z.string().optional(),
  motion: z.string().optional(),
  expression: z.string().optional(),
  intensity: z.number().optional(),
  status: z.string().optional(),
}).passthrough();

const resultSchema = z.object({ success: z.boolean().optional(), message: z.string().optional() }).passthrough();

export const turnSchema = z.object({
  turn_id: z.string(), timestamp: z.string(), stimulus_bundle: z.object({ message: z.string().default("") }).passthrough(),
  result: resultSchema,
  decision: z.object({
    spoken_texts: z.array(z.string()).default([]),
    message_texts: z.array(z.string()).default([]),
    action_intents: z.array(intentSchema).default([]),
    motion_intents: z.array(intentSchema).default([]),
    expression_intents: z.array(intentSchema).default([]),
    speech_intents: z.array(intentSchema).default([]),
    message_intents: z.array(intentSchema).default([]),
    internal_intents: z.array(intentSchema).default([]),
    noop_intents: z.array(intentSchema).default([]),
  }).passthrough(),
  trace: z.object({}).passthrough().optional(), state_after: z.object({ dominant_emotion: z.string().optional() }).passthrough().optional(), state_diff: z.object({}).passthrough().optional(), duration_ms: z.number().optional(), used_state_injection: z.boolean().optional(),
}).passthrough();

export const elfieListSchema = z.object({
  items: z.array(z.object({ elfie_id: z.string(), name: z.string(), species_id: z.union([z.literal("dog"), z.literal("fox")]), portrait_url: z.string().optional() }).passthrough()),
});

export const sessionSchema = z.object({
  elfie_id: z.string(),
  profile: z.object({
    elfie_id: z.string(), name: z.string(), species_id: z.union([z.literal("dog"), z.literal("fox")]),
    species_label: z.string().default(""), life_stage: z.string().default(""), age_years: z.number().optional(),
    description: z.string().default(""), appearance_description: z.string().default(""),
    personality_summary: z.string().default(""), personality_tags: z.array(z.string()).default([]),
    big_five: bigFiveSchema, portrait_url: z.string().default(""), appearance: z.record(z.string(), z.unknown()),
    memory_cognition: memorySchema.default({ topics: [], important_events: [], relations: { nodes: [], links: [] }, knowledge: { nodes: [], links: [] }, world_understanding: "尚未形成稳定的世界理解" }),
    spec_revision: z.number().optional(), updated_at: z.string().optional(),
  }).passthrough(),
  current_state: z.object({ energy: z.number(), fatigue: z.number(), dominant_emotion: z.string(), is_sleeping: z.boolean(), memory_count: z.number().default(0) }).passthrough(),
  turns: z.array(turnSchema),
}).passthrough();

export const foodsSchema = z.object({
  items: z.array(z.object({
    key: z.string(),
    display_name: z.string(),
    description: z.string().default(""),
    model: z.string().default(""),
    reasoning: z.string().default(""),
    ready_for_attempt: z.boolean(),
    unavailable_reason: z.string().default(""),
    setup_commands: z.array(z.string()).default([]),
  }).passthrough()),
  configuration_command: z.string().default(""),
});

export const mediaSchema = z.object({ media_id: z.string(), media_url: z.string().optional() }).passthrough();
export type ElfieListItem = z.infer<typeof elfieListSchema>["items"][number];
export type ElfieSession = z.infer<typeof sessionSchema>;
export type ElfieTurn = ElfieSession["turns"][number];
export type BigFive = z.infer<typeof bigFiveSchema>;
export type FoodItem = z.infer<typeof foodsSchema>["items"][number];
export type PreviewIntent = z.infer<typeof intentSchema>;
