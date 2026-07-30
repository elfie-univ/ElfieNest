import { z } from "zod"

import { csrfHeaders, requestJson } from "./http"

export const ThemeKeySchema = z.union([
  z.literal("warm-paper"),
  z.literal("harbor-blue"),
  z.literal("orchid-archive"),
  z.literal("moss-green"),
])

export const SafeLoginNextPathSchema = z.union([
  z.literal("/chat"),
  z.literal("/manage"),
  z.literal("/monitor"),
])

const ClientUserSchema = z.object({
  // The current server response identifies the signed-in account by `username`
  // (and retains a database-only `id`).  Keep the frontend's business-facing
  // account identifier stable without requiring a backend migration.
  account_id: z.string().min(1).optional(),
  id: z.union([z.string(), z.number()]).optional(),
  username: z.string().optional(),
  role: z.union([z.literal("owner"), z.literal("user")]),
  nickname: z.string().nullable().optional(),
  avatar_url: z.string().nullable().optional(),
  avatar_color: z.number().int().min(0).max(7).optional(),
  avatar_kind: z.union([z.literal("initials"), z.literal("emoji")]).optional(),
  theme_key: ThemeKeySchema.default("warm-paper"),
  default_landing_page: z.union([z.literal("chat"), z.literal("manage")]).optional(),
  csrf_token: z.string().optional(),
}).refine(
  (user) => user.account_id !== undefined || user.username !== undefined || user.id !== undefined,
  { message: "ERR_SESSION_ACCOUNT_ID_MISSING" },
).transform((user) => {
  const accountId = user.account_id ?? user.username ?? String(user.id)
  return { ...user, account_id: accountId, username: user.username ?? accountId }
})

const LoginResponseSchema = z.object({ landing_path: SafeLoginNextPathSchema })
const SetupResponseSchema = z.object({
  account_id: z.string().min(1),
  role: z.literal("owner"),
  csrf_token: z.string(),
}).transform((user) => ({ ...user, username: user.account_id }))

export type ClientUser = z.infer<typeof ClientUserSchema>
export type ThemeKey = z.infer<typeof ThemeKeySchema>
export type SafeLoginNextPath = z.infer<typeof SafeLoginNextPathSchema>

export function safeLoginNextPath(rawNext: string | null): SafeLoginNextPath | "" {
  const parsed = SafeLoginNextPathSchema.safeParse(rawNext)
  return parsed.success ? parsed.data : ""
}

export async function currentUser(): Promise<ClientUser> {
  return ClientUserSchema.parse(await requestJson("/api/auth/me"))
}

export async function saveTheme(themeKey: ThemeKey, csrfToken: string): Promise<ThemeKey> {
  const payload = z.object({ theme_key: ThemeKeySchema }).parse(
    await requestJson("/api/auth/me/theme", {
      method: "PUT",
      headers: csrfHeaders(csrfToken, true),
      body: JSON.stringify({ theme_key: themeKey }),
    }),
  )
  return payload.theme_key
}

export async function updateProfile(
  profileInput: { readonly nickname: string },
  csrfToken: string,
): Promise<void> {
  await requestJson("/api/auth/me/profile", {
    method: "PUT",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ nickname: profileInput.nickname }),
  })
}

export async function uploadAvatar(file: File, csrfToken: string): Promise<string> {
  const formData = new FormData()
  formData.append("file", file)
  const response = z.object({ avatar_url: z.string() }).parse(
    await requestJson("/api/auth/me/avatar", {
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
  await requestJson("/api/auth/me/password", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  })
}

export async function setup(
  username: string,
  password: string,
): Promise<z.infer<typeof SetupResponseSchema>> {
  return SetupResponseSchema.parse(await requestJson("/api/auth/setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  }))
}

export async function login(username: string, password: string, next: string): Promise<string> {
  const safeNext = safeLoginNextPath(next)
  const target = safeNext ? `?next=${safeNext}` : ""
  const result = await requestJson(`/api/auth/login${target}`, {
    method: "POST",
    body: new URLSearchParams({ username, password }),
  })
  return LoginResponseSchema.parse(result).landing_path
}

export async function saveLandingPage(
  page: "chat" | "manage",
  csrfToken: string,
): Promise<void> {
  await requestJson("/api/v1/me/default-landing-page", {
    method: "PUT",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ default_landing_page: page }),
  })
}

export async function logout(csrfToken: string): Promise<void> {
  await requestJson("/api/auth/logout", {
    method: "POST",
    headers: csrfHeaders(csrfToken),
  })
}

export async function heartbeat(csrfToken: string): Promise<number> {
  const result = z.object({
    status: z.literal("ok"),
    last_seen_at: z.number(),
  }).parse(await requestJson("/api/auth/heartbeat", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
  }))
  return result.last_seen_at
}
