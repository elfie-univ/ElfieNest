import { z } from "zod"

import { ownerWrite, requestJson } from "./http"

export const NestBedSchema = z.object({
  id: z.string(),
  anchor_id: z.string(),
  name: z.string(),
  occupant_id: z.string().nullable(),
  occupant_name: z.string().nullable(),
  occupant_species_id: z.string().nullable(),
})

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
