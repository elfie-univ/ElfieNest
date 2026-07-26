import { z } from "zod"

import { csrfHeaders, ownerWrite, requestJson } from "./http"

const OwnerUserSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  role: z.literal("user"),
  created_at: z.string(),
  elfie_count: z.number().int(),
  display_name: z.string(),
  elfie_quota_override: z.number().int().nullable(),
  effective_elfie_limit: z.number().int(),
  online_status: z.literal("unknown"),
  avatar_url: z.string().nullable(),
})
const CreatedOwnerUserSchema = OwnerUserSchema

export type OwnerUser = z.infer<typeof OwnerUserSchema>
export type CreatedOwnerUser = z.infer<typeof CreatedOwnerUserSchema>

export async function ownerUsers(): Promise<readonly OwnerUser[]> {
  return z.array(OwnerUserSchema).parse(await requestJson("/api/owner/users"))
}

export async function createManagedUser(
  username: string,
  password: string,
  csrfToken: string,
): Promise<CreatedOwnerUser> {
  return CreatedOwnerUserSchema.parse(await requestJson("/api/owner/users", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ username, password, role: "user" }),
  }))
}

export async function updateManagedUser(
  userId: number,
  changes: { readonly elfie_quota_override: number | null },
  csrfToken: string,
): Promise<CreatedOwnerUser> {
  return CreatedOwnerUserSchema.parse(
    await ownerWrite(`/api/owner/users/${userId}`, "PUT", csrfToken, changes),
  )
}

export async function deleteManagedUser(userId: number, csrfToken: string): Promise<void> {
  await ownerWrite(`/api/owner/users/${userId}`, "DELETE", csrfToken)
}
