import { z } from "zod"

import { csrfHeaders, requestJson } from "./http"
import { AccountRoleSchema } from "./roles"

export { AccountRoleSchema }
export type { AccountRole } from "./roles"

export const ThemeKeySchema = z.union([
  z.literal("warm-paper"),
  z.literal("harbor-blue"),
  z.literal("orchid-archive"),
  z.literal("moss-green"),
])
export const GenderSchema = z.union([z.literal("male"), z.literal("female")])

export const SafeLoginNextPathSchema = z.union([
  z.literal("/chat"),
  z.literal("/manage"),
  z.literal("/monitor"),
])

const ClientUserSchema = z.object({
  user_id: z.number().int().positive(),
  account_id: z.string().min(1),
  display_name: z.string().nullable(),
  gender: GenderSchema.optional(),
  birth_date: z.string().nullable().optional(),
  role: AccountRoleSchema,
  avatar_url: z.string().nullable().optional(),
  avatar_color: z.number().int().min(0).max(7).optional(),
  avatar_kind: z.union([z.literal("initials"), z.literal("emoji")]).optional(),
  theme_key: ThemeKeySchema.default("warm-paper"),
  default_landing_page: z.union([z.literal("chat"), z.literal("manage")]).optional(),
  created_at: z.string().optional(),
  elfie_count: z.number().int().min(0).optional(),
  csrf_token: z.string().optional(),
}).strict()
const CurrentAccountResponseSchema = ClientUserSchema.required()

const LoginResponseSchema = z.object({ landing_path: SafeLoginNextPathSchema })
const ProfileResponseSchema = z.object({
  user_id: z.number().int().positive(),
  account_id: z.string().min(1),
  display_name: z.string().nullable(),
  gender: GenderSchema,
  birth_date: z.string().nullable(),
  avatar_url: z.string().nullable(),
  avatar_color: z.number().int().min(0).max(7),
  avatar_kind: z.union([z.literal("initials"), z.literal("emoji")]),
}).strict()
const DetailResponseSchema = z.object({ detail: z.string() }).strict()
const LandingPageResponseSchema = z.object({
  default_landing_page: z.union([z.literal("chat"), z.literal("manage")]),
}).strict()
export type ClientUser = z.infer<typeof ClientUserSchema>
export type Gender = z.infer<typeof GenderSchema>
export type ThemeKey = z.infer<typeof ThemeKeySchema>
export type SafeLoginNextPath = z.infer<typeof SafeLoginNextPathSchema>

export function safeLoginNextPath(rawNext: string | null): SafeLoginNextPath | "" {
  const parsed = SafeLoginNextPathSchema.safeParse(rawNext)
  return parsed.success ? parsed.data : ""
}

export async function currentUser(): Promise<ClientUser> {
  return CurrentAccountResponseSchema.parse(await requestJson("/api/v1/me", { cache: "no-store" }))
}

export async function saveTheme(themeKey: ThemeKey, csrfToken: string): Promise<ThemeKey> {
  const payload = z.object({ theme_key: ThemeKeySchema }).parse(
    await requestJson("/api/v1/me/theme", {
      method: "PUT",
      headers: csrfHeaders(csrfToken, true),
      body: JSON.stringify({ theme_key: themeKey }),
    }),
  )
  return payload.theme_key
}

export async function updateProfile(
  profileInput: {
    readonly account_id?: string
    readonly birth_date?: string | null
    readonly display_name?: string
    readonly gender?: Gender
  },
  csrfToken: string,
): Promise<void> {
  const body = {
    ...(profileInput.account_id === undefined ? {} : { account_id: profileInput.account_id }),
    ...(profileInput.birth_date === undefined ? {} : { birth_date: profileInput.birth_date }),
    ...(profileInput.display_name === undefined ? {} : { display_name: profileInput.display_name }),
    ...(profileInput.gender === undefined ? {} : { gender: profileInput.gender }),
  }
  ProfileResponseSchema.parse(await requestJson("/api/v1/me/profile", {
    method: "PATCH",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify(body),
  }))
}

export async function uploadAvatar(file: File, csrfToken: string): Promise<string> {
  const formData = new FormData()
  formData.append("file", file)
  const response = z.object({ avatar_url: z.string() }).parse(
    await requestJson("/api/v1/me/avatar", {
      method: "POST",
      headers: csrfHeaders(csrfToken),
      body: formData,
    }),
  )
  return response.avatar_url
}

export async function changePassword(
  oldPassword: string,
  newPassword: string,
  csrfToken: string,
): Promise<void> {
  DetailResponseSchema.parse(await requestJson("/api/v1/me/password", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  }))
}

export async function login(accountId: string, password: string, next: string): Promise<string> {
  const safeNext = safeLoginNextPath(next)
  const target = safeNext ? `?next=${safeNext}` : ""
  const result = await requestJson(`/api/v1/auth/login${target}`, {
    method: "POST",
    body: new URLSearchParams({ account_id: accountId, password }),
  })
  return LoginResponseSchema.parse(result).landing_path
}

export async function register(
  displayName: string,
  accountId: string,
  password: string,
  next: string,
): Promise<string> {
  const safeNext = safeLoginNextPath(next)
  const target = safeNext ? `?next=${safeNext}` : ""
  const result = await requestJson(`/api/v1/auth/register${target}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      account_id: accountId,
      display_name: displayName,
      password,
    }),
  })
  return LoginResponseSchema.parse(result).landing_path
}

export async function saveLandingPage(
  page: "chat" | "manage",
  csrfToken: string,
): Promise<void> {
  LandingPageResponseSchema.parse(await requestJson("/api/v1/me/default-landing-page", {
    method: "PUT",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ default_landing_page: page }),
  }))
}

export async function logout(csrfToken: string): Promise<void> {
  await requestJson("/api/v1/auth/logout", {
    method: "POST",
    headers: csrfHeaders(csrfToken),
  })
}

export async function heartbeat(csrfToken: string): Promise<string> {
  const result = z.object({
    status: z.literal("ok"),
    last_seen_at: z.string().datetime({ offset: true }),
  }).strict().parse(await requestJson("/api/v1/me/heartbeat", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
  }))
  return result.last_seen_at
}
