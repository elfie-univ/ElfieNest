import type { ChatMessage, Conversation, ElfieProfile } from "../../api/client"
import type { ElfieListItem } from "./elfie-list-model"

export type ChatData = {
  readonly adopterAccountIds: Readonly<Record<string, string>>
  readonly conversations: readonly Conversation[]
  readonly elfies: readonly ElfieProfile[]
}

export function createOwnedChatData(
  elfies: readonly ElfieProfile[],
  conversations: readonly Conversation[],
  adopterAccountId: string,
): ChatData {
  return {
    adopterAccountIds: Object.fromEntries(
      elfies.map((entry) => [entry.elfie_id, adopterAccountId]),
    ),
    conversations: conversations.filter((row) => row.last_message_at !== null),
    elfies,
  }
}

export function recordChatMessage(data: ChatData, message: ChatMessage): ChatData {
  const elfie = data.elfies.find((entry) => entry.elfie_id === message.elfie_id)
  if (elfie === undefined) return data
  const conversation: Conversation = {
    elfie_id: elfie.elfie_id,
    name: elfie.name,
    portrait_url: elfie.portrait_url,
    last_message_preview: message.text,
    last_message_at: message.created_at,
  }
  const existingIndex = data.conversations.findIndex((row) => row.elfie_id === conversation.elfie_id)
  const conversations = existingIndex === -1
    ? [...data.conversations, conversation]
    : data.conversations.map((row, index) => index === existingIndex ? conversation : row)
  return { ...data, conversations }
}

export function createElfieListItems(data: ChatData | null): readonly ElfieListItem[] {
  return data?.elfies.map((profile) => ({
    adopterAccountId: data.adopterAccountIds[profile.elfie_id] ?? "",
    profile,
  })) ?? []
}
