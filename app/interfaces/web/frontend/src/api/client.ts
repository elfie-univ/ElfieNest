import ky from "ky"
import { z } from "zod"

export const ThemeKeySchema = z.union([
  z.literal("warm-paper"),
  z.literal("harbor-blue"),
  z.literal("orchid-archive"),
  z.literal("moss-green"),
])

const ClientUserSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  role: z.union([z.literal("owner"), z.literal("user")]),
  nickname: z.string().nullable().optional(),
  avatar_color: z.number().int().min(0).max(7).optional(),
  avatar_kind: z.union([z.literal("initials"), z.literal("emoji")]).optional(),
  theme_key: ThemeKeySchema.default("warm-paper"),
  default_landing_page: z.union([z.literal("chat"), z.literal("manage")]).optional(),
  csrf_token: z.string().optional()
})

const LoginResponseSchema = z.object({ landing_path: z.union([z.literal("/chat"), z.literal("/manage")]) })
const SetupResponseSchema = z.object({ id: z.number().int(), username: z.string(), role: z.literal("owner"), csrf_token: z.string() })

export const ChatMessageSchema = z.object({
  id: z.number().int(), elfie_id: z.string(),
  sender: z.union([z.literal("user"), z.literal("elfie"), z.literal("system")]),
  text: z.string(), created_at: z.string()
})

const ConversationSchema = z.object({
  elfie_id: z.string(), name: z.string(), portrait_url: z.string(),
  last_message_preview: z.string(), last_message_at: z.string().nullable()
})

export const ProfileSchema = z.object({
  elfie_id: z.string(), name: z.string(), species_id: z.string(), portrait_url: z.string(),
  appearance: z.record(z.string(), z.unknown()), big_five: z.record(z.string(), z.number()),
  personality_tags: z.array(z.string()),
  nest: z.object({ room_name: z.string().nullable(), bed_name: z.string().nullable(), posture: z.string() }),
  embodiment: z.object({ state: z.string() })
})

const OwnerUserSchema = z.object({
  id: z.number().int(), username: z.string(), role: z.literal("user"), created_at: z.string(), elfie_count: z.number().int()
})
const CreatedOwnerUserSchema = OwnerUserSchema.omit({ elfie_count: true })
const OwnerElfieSchema = z.object({
  elfie_id: z.string(),
  owner: z.object({ user_id: z.number().int(), username: z.string() }),
  profile: ProfileSchema,
  food_policy: z.object({ default_food: z.string(), allowed_foods: z.array(z.string()), fallback_food: z.string() }),
  created_at: z.string()
})
const RoomSchema = z.object({
  id: z.string(), name: z.string(),
  desired_bed_count: z.number().int().nullable().optional(),
  beds: z.array(z.object({ id: z.number().int(), name: z.string(), occupant_name: z.string().nullable() }))
})
const AdoptionInfoSchema = z.object({
  personality_styles: z.array(z.string()), species_ids: z.array(z.string()), heights: z.array(z.string()), builds: z.array(z.string()),
  quota: z.object({ used: z.number().int(), max: z.number().int(), remaining: z.number().int(), can_adopt: z.boolean() })
})
const AdoptionResultSchema = z.object({ elfie_id: z.string(), name: z.string(), species_id: z.string() })
export const MobileAccessSchema = z.object({ available: z.boolean(), urls: z.array(z.string().url()) })

export type ClientUser = z.infer<typeof ClientUserSchema>
export type ThemeKey = z.infer<typeof ThemeKeySchema>
export type ChatMessage = z.infer<typeof ChatMessageSchema>
export type Conversation = z.infer<typeof ConversationSchema>
export type ElfieProfile = z.infer<typeof ProfileSchema>
export type OwnerUser = z.infer<typeof OwnerUserSchema>
export type CreatedOwnerUser = z.infer<typeof CreatedOwnerUserSchema>
export type OwnerElfie = z.infer<typeof OwnerElfieSchema>
export type NestRoom = z.infer<typeof RoomSchema>
export type AdoptionInfo = z.infer<typeof AdoptionInfoSchema>
export type MobileAccess = z.infer<typeof MobileAccessSchema>

export class ApiError extends Error {
  public constructor(readonly status: number, message: string) { super(message) }
}

async function requestJson(path: string, init?: RequestInit): Promise<unknown> {
  const response = await ky(path, { credentials: "same-origin", throwHttpErrors: false, ...init })
  const payload: unknown = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = z.object({ detail: z.string().optional() }).safeParse(payload)
    throw new ApiError(response.status, detail.success && detail.data.detail ? detail.data.detail : "请求未完成")
  }
  return payload
}

export async function ownerRead(path: string): Promise<unknown> {
  return requestJson(path)
}

export async function mobileAccess(): Promise<MobileAccess> {
  return MobileAccessSchema.parse(await ownerRead("/api/owner/mobile-access"))
}

export async function ownerWrite(
  path: string,
  method: "POST" | "PUT" | "DELETE",
  csrfToken: string,
  body?: unknown
): Promise<unknown> {
  const init: RequestInit = { method, headers: csrfHeaders(csrfToken, body !== undefined) }
  if (body !== undefined) init.body = JSON.stringify(body)
  return requestJson(path, init)
}

function csrfHeaders(csrfToken: string, json = false): HeadersInit {
  return json ? { "Content-Type": "application/json", "X-CSRF-Token": csrfToken } : { "X-CSRF-Token": csrfToken }
}

export async function currentUser(): Promise<ClientUser> { return ClientUserSchema.parse(await requestJson("/api/auth/me")) }
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
  profileInput: { readonly nickname: string; readonly avatarColor: number; readonly avatarKind: "initials" | "emoji" },
  csrfToken: string,
): Promise<void> {
  await requestJson("/api/auth/me/profile", {
    method: "PUT",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({
      nickname: profileInput.nickname,
      avatar_color: profileInput.avatarColor,
      avatar_kind: profileInput.avatarKind,
    }),
  })
}
export async function changePassword(oldPassword: string, newPassword: string, csrfToken: string): Promise<void> {
  await requestJson("/api/auth/me/password", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  })
}
export async function setup(username: string, password: string): Promise<z.infer<typeof SetupResponseSchema>> {
  return SetupResponseSchema.parse(await requestJson("/api/auth/setup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) }))
}
export async function login(username: string, password: string, next: string): Promise<string> {
  const target = next === "/chat" || next === "/manage" ? `?next=${next}` : ""
  const result = await requestJson(`/api/auth/login${target}`, { method: "POST", body: new URLSearchParams({ username, password }) })
  return LoginResponseSchema.parse(result).landing_path
}
export async function conversations(): Promise<readonly Conversation[]> { return z.array(ConversationSchema).parse(await requestJson("/api/v1/conversations")) }
export async function elfies(): Promise<readonly ElfieProfile[]> { return z.array(ProfileSchema).parse(await requestJson("/api/v1/elfies")) }
export async function messages(elfieId: string): Promise<readonly ChatMessage[]> { return z.array(ChatMessageSchema).parse(await requestJson(`/api/v1/conversations/${encodeURIComponent(elfieId)}/messages`)) }
export async function profile(elfieId: string): Promise<ElfieProfile> { return ProfileSchema.parse(await requestJson(`/api/v1/elfies/${encodeURIComponent(elfieId)}/profile`)) }
export async function sendMessage(elfieId: string, text: string, csrfToken: string): Promise<ChatMessage> { return ChatMessageSchema.parse(await requestJson(`/api/v1/conversations/${encodeURIComponent(elfieId)}/messages`, { method: "POST", headers: csrfHeaders(csrfToken, true), body: JSON.stringify({ text }) })) }
export async function saveLandingPage(page: "chat" | "manage", csrfToken: string): Promise<void> { await requestJson("/api/v1/me/default-landing-page", { method: "PUT", headers: csrfHeaders(csrfToken, true), body: JSON.stringify({ default_landing_page: page }) }) }
export async function ownerUsers(): Promise<readonly OwnerUser[]> { return z.array(OwnerUserSchema).parse(await requestJson("/api/owner/users")) }
export type OwnerElfieFilters = { readonly ownerUserId?: string; readonly speciesId?: string; readonly foodKey?: string; readonly embodimentState?: string }
export function ownerElfiePath(filters: OwnerElfieFilters = {}): string {
  const query = new URLSearchParams()
  if (filters.ownerUserId) query.set("owner_user_id", filters.ownerUserId)
  if (filters.speciesId) query.set("species_id", filters.speciesId)
  if (filters.foodKey) query.set("food_key", filters.foodKey)
  if (filters.embodimentState) query.set("embodiment_state", filters.embodimentState)
  const serialized = query.toString()
  return serialized ? `/api/owner/elfies?${serialized}` : "/api/owner/elfies"
}
export async function ownerElfies(filters: OwnerElfieFilters = {}): Promise<readonly OwnerElfie[]> {
  return z.array(OwnerElfieSchema).parse(await requestJson(ownerElfiePath(filters)))
}
export async function ownerRooms(): Promise<readonly NestRoom[]> { return z.array(RoomSchema).parse(await requestJson("/api/owner/nest/rooms")) }
export async function adoptionInfo(): Promise<AdoptionInfo> { return AdoptionInfoSchema.parse(await requestJson("/api/user/adoption-info")) }
export async function adoptElfie(input: { readonly name: string; readonly speciesId: string; readonly personalityStyle: string; readonly height: string; readonly build: string }, csrfToken: string): Promise<z.infer<typeof AdoptionResultSchema>> {
  return AdoptionResultSchema.parse(await requestJson("/api/user/adopt", { method: "POST", headers: csrfHeaders(csrfToken, true), body: JSON.stringify({ name: input.name, species_id: input.speciesId, personality_style: input.personalityStyle, height: input.height, build: input.build }) }))
}
export async function createManagedUser(username: string, password: string, csrfToken: string): Promise<CreatedOwnerUser> { return CreatedOwnerUserSchema.parse(await requestJson("/api/owner/users", { method: "POST", headers: csrfHeaders(csrfToken, true), body: JSON.stringify({ username, password, role: "user" }) })) }
export async function logout(csrfToken: string): Promise<void> { await requestJson("/api/auth/logout", { method: "POST", headers: csrfHeaders(csrfToken) }) }
