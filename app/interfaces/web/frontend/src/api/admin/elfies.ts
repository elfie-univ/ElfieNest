import { z } from "zod"

import { requestJson } from "../http"
import { ElfieProfileSchema } from "../elfies/profiles"

const OwnerSchema = z.object({
  user_id: z.number().int().positive(),
  account_id: z.string().min(1),
  display_name: z.string().nullable(),
}).strict()

const PermissionsSchema = z.object({
  can_view_profile: z.boolean(),
  can_view_cognition: z.boolean(),
}).strict()

export const AdminElfieSchema = z.object({
  owner: OwnerSchema,
  permissions: PermissionsSchema,
  profile: ElfieProfileSchema,
}).strict()

const AdminElfiesResponseSchema = z.object({ items: z.array(AdminElfieSchema) }).strict()

export type AdminElfie = z.infer<typeof AdminElfieSchema>
export type AdminElfieFilters = {
  readonly ownerUserId?: number
  readonly speciesId?: string
}

export function adminElfiesPath(filters: AdminElfieFilters = {}): string {
  const query = new URLSearchParams()
  if (filters.ownerUserId !== undefined) query.set("owner_user_id", String(filters.ownerUserId))
  if (filters.speciesId) query.set("species_id", filters.speciesId)
  const serialized = query.toString()
  return serialized ? `/api/v1/admin/elfies?${serialized}` : "/api/v1/admin/elfies"
}

export async function adminElfies(filters: AdminElfieFilters = {}): Promise<readonly AdminElfie[]> {
  return AdminElfiesResponseSchema.parse(await requestJson(adminElfiesPath(filters))).items
}
