import { z } from "zod"

import { csrfHeaders, ownerWrite, requestJson } from "./http"

const OwnerUserSchema = z.object({
  account_id: z.string().min(1),
  username: z.string(),
  role: z.union([z.literal("owner"), z.literal("user")]),
  created_at: z.string(),
  gender: z.string().nullable(),
  birth_date: z.string().nullable(),
  elfie_count: z.number().int(),
  display_name: z.string(),
  elfie_quota_override: z.number().int().nullable(),
  effective_elfie_limit: z.number().int(),
  online_status: z.union([z.literal("online"), z.literal("offline")]),
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
  accountId: string,
  changes: { readonly elfie_quota_override: number | null },
  csrfToken: string,
): Promise<CreatedOwnerUser> {
  return CreatedOwnerUserSchema.parse(
    await ownerWrite("/api/owner/users/quota", "PUT", csrfToken, {
      account_id: accountId,
      ...changes,
    }),
  )
}

export async function resetManagedUserPassword(
  accountId: string,
  csrfToken: string,
): Promise<void> {
  await ownerWrite("/api/owner/users/reset-password", "POST", csrfToken, {
    account_id: accountId,
  })
}

export async function deleteManagedUser(accountId: string, csrfToken: string): Promise<void> {
  await ownerWrite("/api/owner/users/delete", "POST", csrfToken, {
    account_id: accountId,
  })
}
