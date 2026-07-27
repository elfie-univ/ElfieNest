import { z } from "zod"

import { requestJson } from "./http"

export const ProfileSchema = z.object({
  elfie_id: z.string(),
  name: z.string(),
  species_id: z.string(),
  gender: z.string().nullable(),
  birth_date: z.string().nullable(),
  summary: z.string().nullable(),
  online_status: z.union([z.literal("online"), z.literal("offline"), z.literal("unknown")]),
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

const OwnerElfieSchema = z.object({
  elfie_id: z.string(),
  owner: z.object({ user_id: z.number().int(), username: z.string() }),
  profile: ProfileSchema,
  food_policy: z.object({
    default_food: z.string(),
    allowed_foods: z.array(z.string()),
    fallback_food: z.string(),
  }),
  created_at: z.string(),
})

export type ElfieProfile = z.infer<typeof ProfileSchema>
export type OwnerElfie = z.infer<typeof OwnerElfieSchema>
export type OwnerElfieFilters = {
  readonly ownerUserId?: string
  readonly speciesId?: string
  readonly foodKey?: string
  readonly embodimentState?: string
}

export function ownerElfiePath(filters: OwnerElfieFilters = {}): string {
  const query = new URLSearchParams()
  if (filters.ownerUserId) query.set("owner_user_id", filters.ownerUserId)
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
