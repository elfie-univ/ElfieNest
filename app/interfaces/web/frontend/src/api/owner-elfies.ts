import { z } from "zod"

import { ElfieIdValueSchema } from "@/shared/elfie-id"

import { requestJson } from "./http"

export const ProfileSchema = z.object({
  elfie_id: ElfieIdValueSchema,
  name: z.string(),
  species_id: z.string(),
  gender: z.string().nullable(),
  birth_date: z.string().nullable(),
  summary: z.string().nullable(),
  online_status: z.union([z.literal("online"), z.literal("offline"), z.literal("unknown")]),
  status: z.object({
    code: z.string(),
    label: z.string().min(1),
    tone: z.string().min(1),
  }),
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
