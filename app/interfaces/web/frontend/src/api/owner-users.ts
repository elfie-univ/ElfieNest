import { z } from "zod"

import { csrfHeaders, ownerWrite, requestJson } from "./http"

const OwnerUserSchema = z.object({
  user_id: z.number().int().positive(),
  account_id: z.string().min(1),
  display_name: z.string().nullable(),
  role: z.union([z.literal("owner"), z.literal("user")]),
  gender: z.string().nullable(),
  birth_date: z.string().nullable(),
  presence: z.union([z.literal("online"), z.literal("away"), z.literal("offline")]),
  last_seen_at: z.string().nullable(),
  language: z.string().min(1),
  created_at: z.string(),
  elfie_count: z.number().int(),
  elfie_quota_override: z.number().int().nullable(),
  effective_elfie_limit: z.number().int(),
  avatar_url: z.string().nullable(),
}).strict()
const CreatedOwnerUserSchema = OwnerUserSchema
const TemporaryPasswordSchema = z.object({ temporary_password: z.string().min(1) }).strict()
const DeleteUserResponseSchema = z.object({ detail: z.string() }).strict()

export type OwnerUser = z.infer<typeof OwnerUserSchema>
export type CreatedOwnerUser = z.infer<typeof CreatedOwnerUserSchema>

export async function ownerUsers(): Promise<readonly OwnerUser[]> {
  return z.array(OwnerUserSchema).parse(await requestJson("/api/owner/users"))
}

export async function createManagedUser(
  accountId: string,
  displayName: string | null,
  password: string,
  csrfToken: string,
): Promise<CreatedOwnerUser> {
  return CreatedOwnerUserSchema.parse(await requestJson("/api/owner/users", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ account_id: accountId, display_name: displayName, password, role: "user" }),
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

export async function resetManagedUserPassword(
  userId: number,
  csrfToken: string,
): Promise<{ readonly temporary_password: string }> {
  return TemporaryPasswordSchema.parse(await requestJson(`/api/owner/users/${userId}/reset-password`, {
    method: "POST",
    headers: csrfHeaders(csrfToken),
  }))
}

export async function deleteManagedUser(userId: number, csrfToken: string): Promise<void> {
  DeleteUserResponseSchema.parse(await ownerWrite(`/api/owner/users/${userId}`, "DELETE", csrfToken, {}))
}
