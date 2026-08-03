import { z } from "zod"

import { ElfieIdValueSchema } from "@/shared/elfie-id"

import { AccountRoleSchema } from "../../api/roles"

export const BIG_FIVE_TRAITS = [
  "openness",
  "conscientiousness",
  "extraversion",
  "agreeableness",
  "neuroticism",
] as const

export const AccountIdSchema = z.string().min(1).brand("AccountId")
export const ElfieIdSchema = ElfieIdValueSchema.brand("ElfieId")

export type AccountId = z.infer<typeof AccountIdSchema>
export type ElfieId = z.infer<typeof ElfieIdSchema>

const ViewerSchema = z.object({
  accountId: AccountIdSchema,
  role: AccountRoleSchema,
  displayName: z.string().min(1),
}).readonly()

const AdopterSchema = z.object({
  accountId: AccountIdSchema,
  displayName: z.string().min(1),
}).readonly()

const AdoptionMetadataSchema = z.object({
  adoptedAt: z.string().min(1),
  ageLabel: z.string().min(1),
}).readonly()

const BigFiveSchema = z.object({
  openness: z.number().min(0).max(1),
  conscientiousness: z.number().min(0).max(1),
  extraversion: z.number().min(0).max(1),
  agreeableness: z.number().min(0).max(1),
  neuroticism: z.number().min(0).max(1),
}).readonly()

const AppearanceSchema = z.object({
  bodyPlan: z.string().min(1),
  palette: z.string().min(1),
  signature: z.string().min(1),
}).readonly()

const GodotAppearanceSchema = z.object({
  species_id: z.string().min(1),
  profile_version: z.number().int().min(0),
  height_scale: z.number().finite(),
  build_scale: z.number().finite(),
  height_label: z.string().min(1),
  build_label: z.string().min(1),
  bone_scales: z.record(z.string(), z.number().finite()).readonly(),
  blend_shapes: z.record(z.string(), z.number().finite()).readonly(),
  material_parameters: z.record(z.string(), z.unknown()).readonly(),
  species_traits: z.record(z.string(), z.number().finite()).readonly(),
}).readonly()

const PublicProfileSchema = z.object({
  elfieId: ElfieIdSchema,
  name: z.string().min(1),
  speciesId: z.string().min(1),
  gender: z.string().min(1).nullable().default(null),
  biography: z.string().default(""),
  portraitUrl: z.string().default(""),
  appearance: AppearanceSchema,
  runtimeAppearance: GodotAppearanceSchema.nullable().default(null),
  bigFive: BigFiveSchema,
}).readonly()

const CognitionStatusSchema = z.enum(["ready", "empty", "unavailable"])
const WeightSchema = z.number().min(0).max(1)
const RecentFocusSchema = z.object({
  topics: z.array(z.object({
    id: z.string().min(1),
    label: z.string().min(1),
    category: z.string().min(1),
    weight: WeightSchema,
  }).readonly()).max(50).readonly(),
}).readonly()

const ImportantExperiencesSchema = z.object({
  entries: z.array(z.object({
    id: z.string().min(1),
    occurredAt: z.string().min(1),
    title: z.string().min(1),
    changed: z.string(),
    importance: WeightSchema,
    people: z.array(z.string()).readonly(),
  }).readonly()).max(10).readonly(),
}).readonly()

const RelationshipNodeSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  kind: z.enum(["self", "human", "elfie"]),
  weight: WeightSchema,
}).readonly()

const RelationshipEdgeSchema = z.object({
  source: z.string().min(1),
  target: z.string().min(1),
  relationKey: z.string().min(1),
  displayLabel: z.string(),
  weight: WeightSchema,
}).readonly()

const RelationshipWorldSchema = z.object({
  nodes: z.array(RelationshipNodeSchema).max(20).readonly(),
  edges: z.array(RelationshipEdgeSchema).readonly(),
}).readonly()

const WorldNodeSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  kind: z.string().min(1),
  weight: WeightSchema,
}).readonly()

const WorldRingSchema = z.object({
  key: z.enum(["self", "family", "nest", "society", "outside"]),
  nodes: z.array(WorldNodeSchema).readonly(),
}).readonly()

const WorldUnderstandingSchema = z.object({
  summary: z.string(),
  rings: z.array(WorldRingSchema).length(5).readonly(),
}).readonly()

const KnowledgeNodeSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  kind: z.enum(["source", "knowledge", "belief"]),
  weight: WeightSchema,
}).readonly()

const KnowledgeEdgeSchema = z.object({
  source: z.string().min(1),
  target: z.string().min(1),
  relationKey: z.string().min(1),
  displayLabel: z.string(),
  weight: WeightSchema,
}).readonly()

const KnowledgeBeliefsSchema = z.object({
  nodes: z.array(KnowledgeNodeSchema).max(10).readonly(),
  edges: z.array(KnowledgeEdgeSchema).readonly(),
}).readonly()

const PrivateCognitionSchema = z.object({
  status: CognitionStatusSchema,
  recentFocus: RecentFocusSchema,
  importantExperiences: ImportantExperiencesSchema,
  relationshipWorld: RelationshipWorldSchema,
  worldUnderstanding: WorldUnderstandingSchema,
  knowledgeBeliefs: KnowledgeBeliefsSchema,
}).readonly()

const CareSettingsSchema = z.object({
  food: z.object({
    selectedId: z.string(),
    selectedLabel: z.string(),
    options: z.array(z.object({
      id: z.string(),
      label: z.string(),
    }).readonly()).readonly(),
    unavailable: z.boolean(),
  }).readonly(),
}).readonly()

const ExperienceFixtureSchema = z.object({
  adopter: AdopterSchema,
  adoption: AdoptionMetadataSchema.default({ adoptedAt: "未登记", ageLabel: "未登记" }),
  publicProfile: PublicProfileSchema,
  privateCognition: PrivateCognitionSchema,
  careSettings: CareSettingsSchema,
}).readonly()

export type Viewer = z.infer<typeof ViewerSchema>
export type PublicProfile = z.infer<typeof PublicProfileSchema>
export type GodotAppearance = z.infer<typeof GodotAppearanceSchema>
export type PrivateCognition = z.infer<typeof PrivateCognitionSchema>
export type CareSettings = z.infer<typeof CareSettingsSchema>
export type ExperienceFixture = z.infer<typeof ExperienceFixtureSchema>
export type RecentFocus = z.infer<typeof RecentFocusSchema>
export type ImportantExperiences = z.infer<typeof ImportantExperiencesSchema>
export type RelationshipWorld = z.infer<typeof RelationshipWorldSchema>
export type WorldUnderstanding = z.infer<typeof WorldUnderstandingSchema>
export type KnowledgeBeliefs = z.infer<typeof KnowledgeBeliefsSchema>
export type RelationshipNode = z.infer<typeof RelationshipNodeSchema>
export type RelationshipFilter = "all" | "human" | "elfie"

export function parseViewer(input: unknown): Viewer {
  return ViewerSchema.parse(input)
}

export function parseExperienceFixture(input: unknown): ExperienceFixture {
  return ExperienceFixtureSchema.parse(input)
}

export function parseGodotAppearance(input: unknown): GodotAppearance | null {
  const parsed = GodotAppearanceSchema.safeParse(input)
  return parsed.success ? parsed.data : null
}
