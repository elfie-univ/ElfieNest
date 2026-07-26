import { z } from "zod"

import { csrfHeaders, requestJson } from "./http"
import { ProfileSchema } from "./owner-elfies"

export * from "./http"
export * from "./owner-elfies"
export * from "./owner-foods"
export * from "./owner-nest"
export * from "./owner-providers"
export * from "./owner-users"
export * from "./session"

export const ChatMessageSchema = z.object({
  id: z.number().int(),
  elfie_id: z.string(),
  sender: z.union([z.literal("user"), z.literal("elfie"), z.literal("system")]),
  text: z.string(),
  created_at: z.string(),
})
const ConversationSchema = z.object({
  elfie_id: z.string(),
  name: z.string(),
  portrait_url: z.string(),
  last_message_preview: z.string(),
  last_message_at: z.string().nullable(),
})
const AdoptionInfoSchema = z.object({
  personality_styles: z.array(z.string()),
  species_ids: z.array(z.string()),
  heights: z.array(z.string()),
  builds: z.array(z.string()),
  quota: z.object({
    used: z.number().int(),
    max: z.number().int(),
    remaining: z.number().int(),
    can_adopt: z.boolean(),
  }),
})
const AdoptionResultSchema = z.object({
  elfie_id: z.string(),
  name: z.string(),
  species_id: z.string(),
})

export type ChatMessage = z.infer<typeof ChatMessageSchema>
export type Conversation = z.infer<typeof ConversationSchema>
export type AdoptionInfo = z.infer<typeof AdoptionInfoSchema>

export async function conversations(): Promise<readonly Conversation[]> {
  return z.array(ConversationSchema).parse(await requestJson("/api/v1/conversations"))
}

export async function elfies(): Promise<readonly z.infer<typeof ProfileSchema>[]> {
  return z.array(ProfileSchema).parse(await requestJson("/api/v1/elfies"))
}

export async function messages(elfieId: string): Promise<readonly ChatMessage[]> {
  return z.array(ChatMessageSchema).parse(
    await requestJson(`/api/v1/conversations/${encodeURIComponent(elfieId)}/messages`),
  )
}

export async function profile(elfieId: string): Promise<z.infer<typeof ProfileSchema>> {
  return ProfileSchema.parse(
    await requestJson(`/api/v1/elfies/${encodeURIComponent(elfieId)}/profile`),
  )
}

export async function sendMessage(
  elfieId: string,
  text: string,
  csrfToken: string,
): Promise<ChatMessage> {
  return ChatMessageSchema.parse(await requestJson(
    `/api/v1/conversations/${encodeURIComponent(elfieId)}/messages`,
    {
      method: "POST",
      headers: csrfHeaders(csrfToken, true),
      body: JSON.stringify({ text }),
    },
  ))
}

export async function adoptionInfo(): Promise<AdoptionInfo> {
  return AdoptionInfoSchema.parse(await requestJson("/api/user/adoption-info"))
}

export async function adoptElfie(
  input: {
    readonly name: string
    readonly speciesId: string
    readonly personalityStyle: string
    readonly height: string
    readonly build: string
  },
  csrfToken: string,
): Promise<z.infer<typeof AdoptionResultSchema>> {
  return AdoptionResultSchema.parse(await requestJson("/api/user/adopt", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({
      name: input.name,
      species_id: input.speciesId,
      personality_style: input.personalityStyle,
      height: input.height,
      build: input.build,
    }),
  }))
}
