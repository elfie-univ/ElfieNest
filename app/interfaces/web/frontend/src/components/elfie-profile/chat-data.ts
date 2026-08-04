import type { Conversation, ElfieProfile } from "../../api/client"
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
