import type { ElfieProfile } from "../../api/client"
import type { ChatMessage, Conversation } from "../../api/communication"
import type { ElfieListItem } from "./elfie-list-model"

const ACTION_MARKUP_DETECTOR = /\[ACTION\][\s\S]*?\[\/ACTION\]/i
const ACTION_MARKUP_PATTERN = /\s*\[ACTION\][\s\S]*?\[\/ACTION\]\s*/gi

export type ChatData = {
  readonly adopterAccountIds: Readonly<Record<string, string>>
  readonly conversations: readonly Conversation[]
  readonly elfies: readonly ElfieProfile[]
}

export function presentChatText(text: string): string {
  const candidate = text.trim()
  if (!candidate.startsWith("{") && !candidate.startsWith("[") && !candidate.startsWith("```")) {
    return stripActionMarkup(text)
  }
  const fenced = /^```(?:json)?\s*([\s\S]*?)\s*```$/i.exec(candidate)
  const jsonText = fenced?.[1]?.trim() ?? candidate
  let parsed: unknown
  try {
    parsed = JSON.parse(jsonText) as unknown
  } catch (reason: unknown) {
    if (reason instanceof SyntaxError) return ""
    throw reason
  }
  return extractDecisionPlanText(parsed) ?? ""
}

export function presentConversationPreview(text: string): string {
  const candidate = text.trim()
  if (!candidate.startsWith("{") && !candidate.startsWith("[") && !candidate.startsWith("```")) {
    return stripActionMarkup(text)
  }
  const fenced = /^```(?:json)?\s*([\s\S]*?)\s*```$/i.exec(candidate)
  const jsonText = fenced?.[1]?.trim() ?? candidate
  let parsed: unknown
  try {
    parsed = JSON.parse(jsonText) as unknown
  } catch (reason: unknown) {
    if (reason instanceof SyntaxError) return text
    throw reason
  }
  return extractDecisionPlanText(parsed) ?? text
}

function stripActionMarkup(text: string): string {
  if (!ACTION_MARKUP_DETECTOR.test(text)) return text
  return text
    .replace(ACTION_MARKUP_PATTERN, "")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

export function createOwnedChatData(
  elfies: readonly ElfieProfile[],
  conversations: readonly Conversation[],
  adopterAccountId: string,
): ChatData {
  const ownedElfies = elfies.filter((entry) => entry.relationship !== "other")
  const knownElfieIds = new Set(ownedElfies.map((entry) => entry.elfie_id))
  const conversationByElfieId = new Map<string, Conversation>()
  for (const entry of ownedElfies) {
    conversationByElfieId.set(entry.elfie_id, {
      elfie_id: entry.elfie_id,
      name: entry.name,
      portrait_url: entry.portrait_url,
      last_message_preview: "",
      last_message_at: null,
    })
  }
  for (const row of conversations) {
    if (!knownElfieIds.has(row.elfie_id)) continue
    conversationByElfieId.set(row.elfie_id, {
      ...row,
      last_message_preview: presentConversationPreview(row.last_message_preview),
    })
  }
  return {
    adopterAccountIds: Object.fromEntries(
      elfies.map((entry) => [
        entry.elfie_id,
        entry.relationship === "other" ? "" : adopterAccountId,
      ]),
    ),
    conversations: [...conversationByElfieId.values()],
    elfies,
  }
}

export function recordChatMessage(data: ChatData, message: ChatMessage): ChatData {
  const elfie = data.elfies.find((entry) => entry.elfie_id === message.elfie_id)
  if (elfie === undefined || elfie.relationship === "other") return data
  const conversation: Conversation = {
    elfie_id: elfie.elfie_id,
    name: elfie.name,
    portrait_url: elfie.portrait_url,
    last_message_preview: message.sender === "elfie"
      ? presentChatText(message.text)
      : message.text,
    last_message_at: message.created_at,
  }
  const existingIndex = data.conversations.findIndex((row) => row.elfie_id === conversation.elfie_id)
  const conversations = existingIndex === -1
    ? [...data.conversations, conversation]
    : data.conversations.map((row, index) => index === existingIndex ? conversation : row)
  return { ...data, conversations }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function extractDecisionPlanText(value: unknown): string | null {
  if (!isRecord(value)) return null
  const plan = isRecord(value["DecisionPlan"])
    ? value["DecisionPlan"]
    : value
  const actions = plan["actions"]
  if (Array.isArray(actions)) {
    for (const action of actions) {
      if (!isRecord(action) || action["action"] !== "respond" || !isRecord(action["parameters"])) continue
      for (const field of ["content", "text", "message"] as const) {
        const fieldValue = action["parameters"][field]
        if (typeof fieldValue !== "string") continue
        const visibleValue = stripActionMarkup(fieldValue)
        if (visibleValue.trim()) return visibleValue.trim()
      }
    }
    return ""
  }
  const intents = plan["intents"]
  if (!Array.isArray(intents)) return null
  for (const intent of intents) {
    if (!isRecord(intent)) continue
    const field = intent["type"] === "message" ? "content" : "text"
    const fieldValue = intent[field]
    if (typeof fieldValue !== "string") continue
    const visibleValue = stripActionMarkup(fieldValue)
    if (visibleValue.trim()) return visibleValue.trim()
  }
  return ""
}

export function createElfieListItems(data: ChatData | null): readonly ElfieListItem[] {
  return data?.elfies.map((profile) => ({
    adopterAccountId: data.adopterAccountIds[profile.elfie_id] ?? "",
    profile,
  })) ?? []
}
