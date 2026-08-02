import { z } from "zod"

export const AccountRoleSchema = z.union([
  z.literal("owner"),
  z.literal("admin"),
  z.literal("user"),
])
export const ManagedCreationRoleSchema = z.union([z.literal("admin"), z.literal("user")])

export type AccountRole = z.infer<typeof AccountRoleSchema>
export type ManagedCreationRole = z.infer<typeof ManagedCreationRoleSchema>

export const MAX_ADMINS = 5
export const MAX_ACCOUNTS = 16

const ROLE_RANK: Readonly<Record<AccountRole, number>> = {
  admin: 2,
  owner: 3,
  user: 1,
}

const ROLE_LIST_ORDER: Readonly<Record<AccountRole, number>> = {
  owner: 0,
  admin: 1,
  user: 2,
}

export function isManagerRole(role: AccountRole): role is "owner" | "admin" {
  return role === "owner" || role === "admin"
}

export function canManageRole(actorRole: AccountRole, targetRole: AccountRole): boolean {
  return ROLE_RANK[actorRole] > ROLE_RANK[targetRole]
}

export function compareAccountListOrder(
  left: { readonly role: AccountRole; readonly user_id: number },
  right: { readonly role: AccountRole; readonly user_id: number },
): number {
  return ROLE_LIST_ORDER[left.role] - ROLE_LIST_ORDER[right.role] || left.user_id - right.user_id
}
