import { z } from "zod"

import { ownerWrite, requestJson } from "./http"

const BedPayloadFields = {
  anchor_id: z.string(),
  occupant_id: z.string().nullable(),
  occupant_name: z.string().nullable(),
  occupant_species_id: z.string().nullable(),
}

const UiNestBedSchema = z.object({
  ...BedPayloadFields,
  id: z.string(),
  name: z.string(),
})

const BackendNestBedSchema = z.object({
  ...BedPayloadFields,
  id: z.number().int(),
  label: z.string(),
})

export const NestBedSchema = z.union([UiNestBedSchema, BackendNestBedSchema]).transform((bed) => ({
  id: typeof bed.id === "number" ? String(bed.id) : bed.id,
  anchor_id: bed.anchor_id,
  name: "label" in bed ? bed.label : bed.name,
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
})
export const MobileAccessSchema = z.object({
  available: z.boolean(),
  urls: z.array(z.string().url()),
})

export type NestRoom = z.infer<typeof RoomSchema>
export type NestBed = z.infer<typeof NestBedSchema>
export type MobileAccess = z.infer<typeof MobileAccessSchema>

export async function ownerRooms(): Promise<readonly NestRoom[]> {
  return z.array(RoomSchema).parse(await requestJson("/api/owner/nest/rooms"))
}

export async function ownerUpdateBedCount(bedCount: number, csrfToken: string): Promise<void> {
  await ownerWrite("/api/owner/nest/rooms/default/bed-count", "PUT", csrfToken, { bed_count: bedCount })
}

export async function ownerAssignBed(elfieId: string, anchorId: string | null, csrfToken: string): Promise<void> {
  await ownerWrite(`/api/owner/nest/elfies/${encodeURIComponent(elfieId)}/bed`, "PUT", csrfToken, { home_anchor_id: anchorId })
}

export async function mobileAccess(): Promise<MobileAccess> {
  return MobileAccessSchema.parse(await requestJson("/api/owner/mobile-access"))
}
