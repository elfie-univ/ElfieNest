import { z } from "zod";

const bigFiveSchema = z.object({
  openness: z.number(), conscientiousness: z.number(), extraversion: z.number(),
  agreeableness: z.number(), neuroticism: z.number(),
});

const normalizedScalarSchema = z.number().min(0).max(1);

const graphLinkSchema = z.object({
  source: z.string(),
  target: z.string(),
  label: z.string().default(""),
  relation_kind: z.string().default(""),
  weight: normalizedScalarSchema.default(0.5),
}).passthrough().readonly();

const denseGraphSchema = z.object({
  nodes: z.array(z.object({
    id: z.string(),
    label: z.string(),
    kind: z.enum(["self", "human", "elfie", "knowledge", "belief", "pattern"]).optional(),
    weight: normalizedScalarSchema.default(0.5),
    confidence: normalizedScalarSchema.optional(),
    source_event_ids: z.array(z.string()).default([]),
  }).passthrough().readonly()).max(20).default([]),
  links: z.array(graphLinkSchema).default([]),
}).passthrough().readonly();

const worldNodeSchema = z.object({
  id: z.string(),
  label: z.string(),
  weight: normalizedScalarSchema.default(0.5),
}).passthrough().readonly();

const worldRingSchema = <Kind extends "self" | "family" | "nest" | "society" | "outside">(kind: Kind) => z.object({
  kind: z.literal(kind),
  label: z.string().default(kind),
  nodes: z.array(worldNodeSchema).default([]),
}).passthrough().readonly();

const worldModelSchema = z.object({
  summary: z.string().default(""),
  rings: z.tuple([
    worldRingSchema("self"),
    worldRingSchema("family"),
    worldRingSchema("nest"),
    worldRingSchema("society"),
    worldRingSchema("outside"),
  ]),
}).passthrough().readonly();

function emptyWorldModel(summary: string) {
  return {
    summary,
    rings: [
      { kind: "self", label: "自我", nodes: [] },
      { kind: "family", label: "家庭", nodes: [] },
      { kind: "nest", label: "巢穴", nodes: [] },
      { kind: "society", label: "社会", nodes: [] },
      { kind: "outside", label: "外部世界", nodes: [] },
    ],
  } as const;
}

export const memoryCognitionSchema = z.object({
  topics: z.array(z.object({
    label: z.string(),
    weight: normalizedScalarSchema.default(0.5),
    category: z.string().default("uncategorized"),
  }).passthrough().readonly()).max(20).default([]),
  important_events: z.array(z.object({
    id: z.string().default(""),
    content: z.string(),
    timestamp: z.string().optional(),
    emotion: z.string().default(""),
    importance: normalizedScalarSchema.default(0.5),
    people: z.array(z.string()).default([]),
    changed: z.string().default(""),
  }).passthrough().readonly()).max(20).default([]),
  relations: denseGraphSchema.default({ nodes: [], links: [] }),
  knowledge: denseGraphSchema.default({ nodes: [], links: [] }),
  world_understanding: z.string().default("尚未形成稳定的世界理解"),
  world_model: worldModelSchema.optional(),
}).passthrough().transform((memory) => ({
  ...memory,
  world_model: memory.world_model ?? emptyWorldModel(memory.world_understanding),
}));

const intentSchema = z.object({
  intent_id: z.string().optional(),
  type: z.string().optional(),
  motion: z.string().optional(),
  expression: z.string().optional(),
  intensity: z.number().optional(),
  status: z.string().optional(),
}).passthrough();

const activityIntentSchema = intentSchema.extend({
  activity_id: z.string().optional(),
  goal: z.string().optional(),
  state: z.string().optional(),
  wake_at: z.string().nullable().optional(),
  step_count: z.number().optional(),
}).passthrough();

const resultSchema = z.object({ success: z.boolean().optional(), message: z.string().optional() }).passthrough();

export const turnSchema = z.object({
  turn_id: z.string(), timestamp: z.string(), stimulus_bundle: z.object({ source_domain: z.enum(["communication", "embodied"]).default("communication"), message: z.string().default("") }).passthrough(),
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
    activity_intents: z.array(activityIntentSchema).default([]),
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
    memory_cognition: memoryCognitionSchema.prefault({ topics: [], important_events: [], relations: { nodes: [], links: [] }, knowledge: { nodes: [], links: [] }, world_understanding: "尚未形成稳定的世界理解" }),
    spec_revision: z.number().optional(), updated_at: z.string().optional(),
  }).passthrough(),
  current_state: z.object({ energy: z.number(), fatigue: z.number(), dominant_emotion: z.string(), is_sleeping: z.boolean(), normal_budget_available: z.number().default(0), emergency_reserve_available: z.number().default(0), reserved_cognitive_budget: z.number().default(0), memory_count: z.number().default(0), activity_count: z.number().default(0), activities: z.array(z.record(z.string(), z.unknown())).default([]), motivation: z.record(z.string(), z.unknown()).nullable().optional(), orientation: z.record(z.string(), z.unknown()).nullable().optional(), selfhood: z.record(z.string(), z.unknown()).nullable().optional(), profile_anchor: z.record(z.string(), z.unknown()).nullable().optional(), cognitive_consolidation: z.record(z.string(), z.unknown()).nullable().optional(), journal: z.record(z.string(), z.unknown()).nullable().optional() }).passthrough(),
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
  }).passthrough()),
  local_models: z.array(z.string()).default([]),
});

export const configureFoodSchema = foodsSchema.extend({
  selected_food: z.string(),
});

export const mediaSchema = z.object({ media_id: z.string(), mime_type: z.string(), media_url: z.string().optional() }).passthrough();

const evaluationResultStatusSchema = z.enum(["pending", "running", "baseline", "passed", "failed", "improved", "unchanged", "regressed", "incomplete"]);
export const evaluationPresetSchema = z.object({
  key: z.enum(["quick", "standard"]),
  title: z.string(),
  description: z.string(),
  typical_duration: z.string(),
  scenario_count: z.number().int().positive(),
  requires_godot: z.boolean(),
}).readonly();
export const evaluationPresetsSchema = z.object({ items: z.array(evaluationPresetSchema) });
const evaluationScenarioSchema = z.object({
  family_id: z.string(),
  title: z.string(),
  purpose: z.string(),
  dimension: z.enum(["identity_continuity", "understanding_reasoning", "memory_relationships", "emotion_energy", "autonomy_boundaries", "commitment_reliability"]).nullable(),
  status: evaluationResultStatusSchema,
  baseline_outputs: z.array(z.string()),
  candidate_outputs: z.array(z.string()),
  evidence: z.array(z.string()),
  latency_ms: z.number(),
  error: z.string().nullable(),
}).readonly();
const evaluationDimensionSchema = z.object({
  dimension: z.enum(["identity_continuity", "understanding_reasoning", "memory_relationships", "emotion_energy", "autonomy_boundaries", "commitment_reliability"]),
  label: z.string(),
  status: evaluationResultStatusSchema,
  value: z.number().int().min(-1).max(1).nullable(),
  evidence: z.array(z.string()),
}).readonly();
export const evaluationRunSchema = z.object({
  schema_version: z.literal(1),
  run_id: z.string(),
  elfie_id: z.string(),
  suite: z.enum(["quick", "standard"]),
  status: z.enum(["pending", "running", "completed", "failed"]),
  verdict: z.enum(["baseline", "improved", "observe", "regressed", "incomplete"]),
  created_at: z.string(),
  completed_at: z.string().nullable(),
  source_revision: z.string(),
  source_dirty: z.boolean(),
  source_snapshot_sha256: z.string(),
  candidate_label: z.string(),
  candidate_spec_sha256: z.string(),
  fixture_sha256: z.string(),
  food_key: z.string(),
  food_model: z.string(),
  judge_food_key: z.string(),
  judge_model: z.string(),
  judge_spec_sha256: z.string(),
  baseline_run_id: z.string().nullable(),
  is_baseline: z.boolean(),
  formal_eligible: z.boolean(),
  total_scenarios: z.number().int(),
  completed_scenarios: z.number().int(),
  total_model_calls: z.number().int(),
  total_latency_ms: z.number(),
  scenarios: z.array(evaluationScenarioSchema),
  dimensions: z.array(evaluationDimensionSchema),
  p0_violations: z.array(z.object({ code: z.string(), title: z.string(), evidence: z.array(z.string()) }).readonly()),
  warnings: z.array(z.string()),
  error: z.string().nullable(),
}).readonly();
export const evaluationHistorySchema = z.object({
  items: z.array(evaluationRunSchema),
  baseline_run_ids: z.record(z.string(), z.string()),
});
export type ElfieListItem = z.infer<typeof elfieListSchema>["items"][number];
export type ElfieSession = z.infer<typeof sessionSchema>;
export type ElfieTurn = ElfieSession["turns"][number];
export type BigFive = z.infer<typeof bigFiveSchema>;
export type FoodItem = z.infer<typeof foodsSchema>["items"][number];
export type FoodConfiguration = Readonly<{
  readonly mode: "local" | "openai";
  readonly model: string;
  readonly api_base?: string;
  readonly api_key?: string;
  readonly alias?: string;
}>;
export type PreviewIntent = z.infer<typeof intentSchema>;
export type EvaluationPreset = z.infer<typeof evaluationPresetSchema>;
export type EvaluationRun = z.infer<typeof evaluationRunSchema>;
export type EvaluationScenario = EvaluationRun["scenarios"][number];
