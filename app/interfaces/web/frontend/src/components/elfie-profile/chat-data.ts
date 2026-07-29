import type { Conversation, ElfieProfile } from "../../api/client"
import { MOCK_ELFIES } from "../owner-card-mock-data"
import type { ElfieListItem } from "./elfie-list-model"

export type ChatData = {
  readonly adopterAccountIds: Readonly<Record<string, string>>
  readonly conversations: readonly Conversation[]
  readonly elfies: readonly ElfieProfile[]
}

export function createDemoChatData(): ChatData {
  const demoElfies = MOCK_ELFIES.map((entry) => entry.profile)
  return {
    adopterAccountIds: Object.fromEntries(
      MOCK_ELFIES.map((entry) => [entry.elfie_id, entry.owner.account_id]),
    ),
    conversations: demoElfies.map((entry) => ({
      elfie_id: entry.elfie_id,
      name: entry.name,
      portrait_url: entry.portrait_url,
      last_message_preview: "演示聊天记录",
      last_message_at: null,
    })),
    elfies: demoElfies,
  }
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
    conversations,
    elfies,
  }
}

export function createElfieListItems(data: ChatData | null): readonly ElfieListItem[] {
  return data?.elfies.map((profile) => ({
    adopterAccountId: data.adopterAccountIds[profile.elfie_id] ?? "",
    profile,
  })) ?? []
}
