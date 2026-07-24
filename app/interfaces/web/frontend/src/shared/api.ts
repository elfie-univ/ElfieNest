import ky from "ky"
import { z } from "zod"

const ClientUserSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  role: z.union([z.literal("owner"), z.literal("user")]),
  default_landing_page: z.union([z.literal("chat"), z.literal("manage")]).optional(),
  csrf_token: z.string().optional()
})

export const ChatMessageSchema = z.object({
  id: z.number().int(),
  elfie_id: z.string(),
  sender: z.union([z.literal("user"), z.literal("elfie"), z.literal("system")]),
  text: z.string(),
  created_at: z.string()
})

const ConversationSchema = z.object({
  elfie_id: z.string(),
  name: z.string(),
  portrait_url: z.string(),
  last_message_preview: z.string(),
  last_message_at: z.string().nullable()
})

const ProfileSchema = z.object({
  elfie_id: z.string(),
  name: z.string(),
  species_id: z.string(),
  portrait_url: z.string(),
  appearance: z.record(z.string(), z.unknown()),
  big_five: z.record(z.string(), z.number()),
  personality_tags: z.array(z.string()),
  nest: z.object({ room_name: z.string().nullable(), bed_name: z.string().nullable(), posture: z.string() }),
  embodiment: z.object({ state: z.string() })
})

const OwnerUserSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  role: z.literal("user"),
  created_at: z.string(),
  elfie_count: z.number().int()
})

const CreatedOwnerUserSchema = OwnerUserSchema.omit({ elfie_count: true })

const OwnerElfieSchema = z.object({
  elfie_id: z.string(),
  name: z.string(),
  owner_username: z.string().nullable(),
  species_id: z.string(),
  room_name: z.string().nullable(),
  bed_name: z.string().nullable()
}).passthrough()

const RoomSchema = z.object({
  id: z.string(),
  name: z.string(),
  beds: z.array(z.object({
    id: z.number().int(),
    name: z.string(),
    occupant_name: z.string().nullable()
  }).passthrough())
}).passthrough()

export type ClientUser = z.infer<typeof ClientUserSchema>
export type ChatMessage = z.infer<typeof ChatMessageSchema>
export type Conversation = z.infer<typeof ConversationSchema>
export type ElfieProfile = z.infer<typeof ProfileSchema>
export type OwnerUser = z.infer<typeof OwnerUserSchema>
export type CreatedOwnerUser = z.infer<typeof CreatedOwnerUserSchema>
export type OwnerElfie = z.infer<typeof OwnerElfieSchema>
export type NestRoom = z.infer<typeof RoomSchema>

export class ApiError extends Error {
  public constructor(readonly status: number, message: string) {
    super(message)
  }
}

async function requestJson(path: string, init?: RequestInit): Promise<unknown> {
  const response = await ky(path, {
    credentials: "same-origin",
    throwHttpErrors: false,
    ...init
  })
  const payload: unknown = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = z.object({ detail: z.string().optional() }).safeParse(payload)
    throw new ApiError(response.status, detail.success && detail.data.detail ? detail.data.detail : "请求未完成")
  }
  return payload
}

export async function currentUser(): Promise<ClientUser> {
  return ClientUserSchema.parse(await requestJson("/api/auth/me"))
}

export async function conversations(): Promise<readonly Conversation[]> {
  return z.array(ConversationSchema).parse(await requestJson("/api/v1/conversations"))
}

export async function elfies(): Promise<readonly ElfieProfile[]> {
  return z.array(ProfileSchema).parse(await requestJson("/api/v1/elfies"))
}

export async function messages(elfieId: string): Promise<readonly ChatMessage[]> {
  return z.array(ChatMessageSchema).parse(await requestJson(`/api/v1/conversations/${encodeURIComponent(elfieId)}/messages`))
}

export async function profile(elfieId: string): Promise<ElfieProfile> {
  return ProfileSchema.parse(await requestJson(`/api/v1/elfies/${encodeURIComponent(elfieId)}/profile`))
}

export async function sendMessage(elfieId: string, text: string, csrfToken: string): Promise<ChatMessage> {
  return ChatMessageSchema.parse(await requestJson(`/api/v1/conversations/${encodeURIComponent(elfieId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ text })
  }))
}

export async function saveLandingPage(page: "chat" | "manage", csrfToken: string): Promise<void> {
  await requestJson("/api/v1/me/default-landing-page", {
    method: "PUT",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ default_landing_page: page })
  })
}

export async function ownerUsers(): Promise<readonly OwnerUser[]> {
  return z.array(OwnerUserSchema).parse(await requestJson("/api/owner/users"))
}

export async function ownerElfies(): Promise<readonly OwnerElfie[]> {
  return z.array(OwnerElfieSchema).parse(await requestJson("/api/owner/elfies"))
}

export async function ownerRooms(): Promise<readonly NestRoom[]> {
  return z.array(RoomSchema).parse(await requestJson("/api/owner/nest/rooms"))
}

export async function createManagedUser(
  username: string,
  password: string,
  csrfToken: string
): Promise<CreatedOwnerUser> {
  return CreatedOwnerUserSchema.parse(await requestJson("/api/owner/users", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ username, password, role: "user" })
  }))
}

export async function logout(csrfToken: string): Promise<void> {
  await requestJson("/api/auth/logout", { method: "POST", headers: { "X-CSRF-Token": csrfToken } })
}
