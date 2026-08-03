import { z } from "zod"

import { ElfieIdValueSchema } from "@/shared/elfie-id"

import { requestJson } from "./http"

const ProfileStatusSchema = z.object({
  code: z.string(),
  label: z.string().min(1),
  tone: z.string().min(1),
})

const ProfilePayloadSchema = z.object({
  elfie_id: ElfieIdValueSchema,
  name: z.string(),
  species_id: z.string(),
  gender: z.string().nullable(),
  birth_date: z.string().nullable(),
  summary: z.string().nullable(),
  online_status: z.union([z.literal("online"), z.literal("offline"), z.literal("unknown")]),
  status: ProfileStatusSchema.optional(),
  portrait_url: z.string(),
  appearance: z.record(z.string(), z.unknown()),
  big_five: z.record(z.string(), z.number()),
  personality_tags: z.array(z.string()),
  nest: z.object({
    room_name: z.string().nullable(),
    bed_name: z.string().nullable(),
    posture: z.string(),
  }),
  embodiment: z.object({ state: z.string() }),
})

const CognitionStatusSchema = z.enum(["ready", "empty", "unavailable"])
const WeightSchema = z.number().min(0).max(1)
const RecentFocusSchema = z.object({
  topics: z.array(z.object({
    id: z.string().min(1),
    label: z.string().min(1),
    category: z.string().min(1),
    weight: WeightSchema,
  }).readonly()).max(20).readonly(),
}).readonly()
const ImportantExperiencesSchema = z.object({
  entries: z.array(z.object({
    id: z.string().min(1),
    occurred_at: z.string().min(1),
    title: z.string().min(1),
    changed: z.string(),
    importance: WeightSchema,
    people: z.array(z.string()).readonly(),
  }).readonly()).max(10).readonly(),
}).readonly()
const RelationshipWorldSchema = z.object({
  nodes: z.array(z.object({
    id: z.string().min(1),
    label: z.string().min(1),
    kind: z.enum(["self", "human", "elfie"]),
    weight: WeightSchema,
  }).readonly()).max(20).readonly(),
  edges: z.array(z.object({
    source: z.string().min(1),
    target: z.string().min(1),
    relation_key: z.string().min(1),
    display_label: z.string(),
    weight: WeightSchema,
  }).readonly()).readonly(),
}).readonly()
const WorldUnderstandingSchema = z.object({
  summary: z.string(),
  rings: z.array(z.object({
    key: z.enum(["self", "family", "nest", "society", "outside"]),
    nodes: z.array(z.object({
      id: z.string().min(1),
      label: z.string().min(1),
      kind: z.string().min(1),
      weight: WeightSchema,
    }).readonly()).readonly(),
  }).readonly()).length(5).readonly(),
}).readonly()
const KnowledgeBeliefsSchema = z.object({
  nodes: z.array(z.object({
    id: z.string().min(1),
    label: z.string().min(1),
    kind: z.enum(["source", "knowledge", "belief"]),
    weight: WeightSchema,
  }).readonly()).max(10).readonly(),
  edges: z.array(z.object({
    source: z.string().min(1),
    target: z.string().min(1),
    relation_key: z.string().min(1),
    display_label: z.string(),
    weight: WeightSchema,
  }).readonly()).readonly(),
}).readonly()
const PrivateCognitionSchema = z.object({
  status: CognitionStatusSchema,
  recent_focus: RecentFocusSchema,
  important_experiences: ImportantExperiencesSchema,
  relationship_world: RelationshipWorldSchema,
  world_understanding: WorldUnderstandingSchema,
  knowledge_beliefs: KnowledgeBeliefsSchema,
}).readonly()
const CareSettingsSchema = z.object({
  food: z.object({
    selected_id: z.string(),
    selected_label: z.string(),
    options: z.array(z.object({
      id: z.string(),
      label: z.string(),
    }).readonly()).readonly(),
    unavailable: z.boolean(),
  }).readonly(),
}).readonly()
const ProfileDetailPayloadSchema = ProfilePayloadSchema.extend({
  private_cognition: PrivateCognitionSchema,
  care_settings: CareSettingsSchema,
})

type ProfilePayload = z.infer<typeof ProfilePayloadSchema>
type ProfileStatus = z.infer<typeof ProfileStatusSchema>

export const ProfileSchema = ProfilePayloadSchema.transform(({ status, ...profile }) => ({
  ...profile,
  status: status ?? deriveProfileStatus(profile),
}))

export const ProfileDetailSchema = ProfileDetailPayloadSchema.transform(({ status, ...profile }) => ({
  ...profile,
  status: status ?? deriveProfileStatus(profile),
}))

function deriveProfileStatus(profile: Pick<ProfilePayload, "embodiment" | "online_status">): ProfileStatus {
  switch (profile.embodiment.state) {
    case "at_nest":
      return { code: "at_nest", label: "at_nest", tone: "active" }
    case "hosted":
      return { code: "awake", label: "awake", tone: "active" }
    case "sleeping":
      return { code: "sleeping", label: "sleeping", tone: "resting" }
    case "offline":
      return { code: "unknown", label: "offline", tone: "inactive" }
    default:
      return { code: "unknown", label: profile.embodiment.state || profile.online_status, tone: "transition" }
  }
}

export const OwnerSchema = z.object({
  user_id: z.number().int().positive(),
  account_id: z.string().min(1),
  display_name: z.string().nullable(),
}).strict()

export const OwnerElfieSchema = z.object({
  elfie_id: ElfieIdValueSchema,
  owner: OwnerSchema,
  profile: ProfileSchema,
  food_policy: z.object({
    main_food_id: z.string(),
    effective_main_food_id: z.string(),
    main_food_options: z.array(z.object({
      food_id: z.string(),
      display_name: z.string(),
    })),
    main_food_unavailable: z.boolean(),
  }),
  created_at: z.string(),
}).strict()

export type ElfieProfile = z.infer<typeof ProfileSchema>
export type ElfieProfileDetail = z.infer<typeof ProfileDetailSchema>
export type OwnerElfie = z.infer<typeof OwnerElfieSchema>
export type OwnerElfieFilters = {
  readonly ownerUserId?: number
  readonly speciesId?: string
  readonly foodKey?: string
  readonly embodimentState?: string
}

export function ownerElfiePath(filters: OwnerElfieFilters = {}): string {
  const query = new URLSearchParams()
  if (filters.ownerUserId !== undefined) query.set("owner_user_id", String(filters.ownerUserId))
  if (filters.speciesId) query.set("species_id", filters.speciesId)
  if (filters.foodKey) query.set("food_key", filters.foodKey)
  if (filters.embodimentState) query.set("embodiment_state", filters.embodimentState)
  const serialized = query.toString()
  return serialized ? `/api/owner/elfies?${serialized}` : "/api/owner/elfies"
}

export async function ownerElfies(
  filters: OwnerElfieFilters = {},
): Promise<readonly OwnerElfie[]> {
  return z.array(OwnerElfieSchema).parse(await requestJson(ownerElfiePath(filters)))
}
