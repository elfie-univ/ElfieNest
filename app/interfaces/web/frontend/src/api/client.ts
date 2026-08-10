import { z } from "zod"

import { ElfieIdValueSchema } from "@/shared/elfie-id"

import { csrfHeaders, requestJson } from "./http"
import { ProfileDetailSchema, ProfileSchema } from "./owner-elfies"

export * from "./http"
export * from "./owner-elfies"
export * from "./admin/food-packages"
export * from "./elfies/food-policy"
export * from "./owner-nest"
export * from "./owner-providers"
export * from "./owner-users"
export * from "./roles"
export * from "./session"

export const ChatMessageSchema = z.object({
  id: z.number().int(),
  elfie_id: ElfieIdValueSchema,
  sender: z.union([z.literal("user"), z.literal("elfie"), z.literal("system")]),
  text: z.string(),
  created_at: z.string(),
})
const ConversationSchema = z.object({
  elfie_id: ElfieIdValueSchema,
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
  life_stages: z.array(z.string()).optional(),
  quota: z.object({
    used: z.number().int(),
    max: z.number().int(),
    remaining: z.number().int(),
    can_adopt: z.boolean(),
  }),
})
const AdoptionResultSchema = z.object({
  elfie_id: ElfieIdValueSchema,
  name: z.string(),
  species_id: z.string(),
})
const AdoptionCandidateSchema = z.object({
  candidate_id: z.string(),
  original_name: z.string(),
  suggested_name: z.string(),
  species_id: z.union([z.literal("dog"), z.literal("fox")]),
  life_stage: z.string(),
  gender: z.union([z.literal("male"), z.literal("female")]),
  image_url: z.string(),
  appearance_tags: z.array(z.string()),
  personality_tags: z.array(z.string()),
  introduction: z.string(),
  compatibility: z.string(),
})
const AdoptionCandidateSetSchema = z.object({
  candidate_set_id: z.string(),
  candidates: z.array(AdoptionCandidateSchema).length(5),
})
const AdoptionReplySchema = AdoptionCandidateSchema.extend({
  status: z.union([z.literal("accepted"), z.literal("unsure")]),
  message: z.string(),
})
const AdoptionRepliesSchema = z.object({
  candidate_set_id: z.string(),
  replies: z.array(AdoptionReplySchema).min(1),
})

export type ChatMessage = z.infer<typeof ChatMessageSchema>
export type Conversation = z.infer<typeof ConversationSchema>
export type AdoptionInfo = z.infer<typeof AdoptionInfoSchema>
export type AdoptionCandidate = z.infer<typeof AdoptionCandidateSchema>
export type AdoptionCandidateSet = z.infer<typeof AdoptionCandidateSetSchema>
export type AdoptionReply = z.infer<typeof AdoptionReplySchema>
export type AdoptionReplies = z.infer<typeof AdoptionRepliesSchema>
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

export async function profile(elfieId: string): Promise<z.infer<typeof ProfileDetailSchema>> {
  return ProfileDetailSchema.parse(
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

export async function adoptionCandidates(
  input: Record<string, unknown>,
  csrfToken: string,
): Promise<AdoptionCandidateSet> {
  return AdoptionCandidateSetSchema.parse(await requestJson("/api/user/adoption/candidates", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify(input),
  }))
}

export async function adoptionReplies(
  candidateSetId: string,
  candidateIds: readonly string[],
  csrfToken: string,
): Promise<AdoptionReplies> {
  return AdoptionRepliesSchema.parse(await requestJson("/api/user/adoption/replies", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ candidate_set_id: candidateSetId, candidate_ids: candidateIds }),
  }))
}

export async function commitAdoption(
  candidateSetId: string,
  candidateId: string,
  name: string,
  csrfToken: string,
): Promise<z.infer<typeof AdoptionResultSchema>> {
  return AdoptionResultSchema.parse(await requestJson("/api/user/adoption/commit", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({ candidate_set_id: candidateSetId, candidate_id: candidateId, name }),
  }))
}
