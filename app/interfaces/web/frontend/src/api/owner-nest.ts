import { z } from "zod"

import { ownerWrite, requestJson } from "./http"

const BackendNestBedSchema = z.object({
  id: z.string(),
  anchor_id: z.string(),
  kind: z.literal("bed"),
  label: z.string(),
  order: z.number().int(),
  active: z.boolean(),
  occupant_id: z.string().nullable(),
  occupant_name: z.string().nullable(),
  occupant_owner_user_id: z.number().int().nullable(),
  occupant_species_id: z.string().nullable(),
  occupant_owner_account_id: z.string().nullable(),
  occupant_owner_display_name: z.string().nullable(),
}).strict()

export const NestBedSchema = BackendNestBedSchema.transform((bed) => ({
  id: bed.id,
  anchor_id: bed.anchor_id,
  name: bed.label,
  occupant_id: bed.occupant_id,
  occupant_name: bed.occupant_name,
  occupant_species_id: bed.occupant_species_id,
}))

export const RoomSchema = z.object({
  id: z.string(),
  name: z.string(),
  desired_bed_count: z.number().int().nullable().optional(),
  applied_world_revision: z.number().int().nullable().optional(),
  beds: z.array(NestBedSchema),
}).strict()
const NestRoomsResponseSchema = z.object({ items: z.array(RoomSchema) }).strict()
export type NestRoom = z.infer<typeof RoomSchema>
export type NestBed = z.infer<typeof NestBedSchema>

export async function ownerRooms(): Promise<readonly NestRoom[]> {
  return NestRoomsResponseSchema.parse(await requestJson("/api/v1/admin/nest/rooms")).items
}

export async function ownerUpdateBedCount(bedCount: number, csrfToken: string): Promise<void> {
  await ownerWrite("/api/v1/admin/nest/rooms/default/bed-count", "PUT", csrfToken, { bed_count: bedCount })
}

export async function ownerAssignBed(elfieId: string, anchorId: string | null, csrfToken: string): Promise<void> {
  await ownerWrite(`/api/v1/admin/nest/elfies/${encodeURIComponent(elfieId)}/bed`, "PUT", csrfToken, { home_anchor_id: anchorId })
}
