import { z } from "zod"

import { ElfieIdValueSchema } from "@/shared/elfie-id"

import { csrfHeaders, requestJson } from "./http"

export const ChatMessageSchema = z.object({
  id: z.number().int(),
  elfie_id: ElfieIdValueSchema,
  sender: z.union([z.literal("user"), z.literal("elfie"), z.literal("system")]),
  text: z.string(),
  created_at: z.string(),
}).strict()

export const ConversationSchema = z.object({
  elfie_id: ElfieIdValueSchema,
  name: z.string(),
  portrait_url: z.string(),
  last_message_preview: z.string(),
  last_message_at: z.string().nullable(),
}).strict()

const ConversationsResponseSchema = z.object({
  items: z.array(ConversationSchema),
}).strict()

const MessagesResponseSchema = z.object({
  items: z.array(ChatMessageSchema),
}).strict()

export type ChatMessage = z.infer<typeof ChatMessageSchema>
export type Conversation = z.infer<typeof ConversationSchema>

export async function conversations(): Promise<readonly Conversation[]> {
  const response = ConversationsResponseSchema.parse(
    await requestJson("/api/v1/me/conversations"),
  )
  return response.items
}

export async function messages(elfieId: string): Promise<readonly ChatMessage[]> {
  const response = MessagesResponseSchema.parse(
    await requestJson(`/api/v1/me/conversations/${encodeURIComponent(elfieId)}/messages`),
  )
  return response.items
}

export async function sendMessage(
  elfieId: string,
  text: string,
  csrfToken: string,
): Promise<ChatMessage> {
  return ChatMessageSchema.parse(await requestJson(
    `/api/v1/me/conversations/${encodeURIComponent(elfieId)}/messages`,
    {
      method: "POST",
      headers: csrfHeaders(csrfToken, true),
      body: JSON.stringify({ text }),
    },
  ))
}
