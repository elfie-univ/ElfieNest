import { z } from "zod"

import { ElfieIdValueSchema } from "@/shared/elfie-id"

const CHAT_PATH = "/chat"

const ChatElfieIdSchema = ElfieIdValueSchema.brand<"ChatElfieId">()
export type ChatElfieId = z.infer<typeof ChatElfieIdSchema>

export type ChatViewState =
  | { readonly view: "elfies" }
  | { readonly view: "profile"; readonly elfie: ChatElfieId }
  | { readonly view: "conversation"; readonly elfie: ChatElfieId }

export type ChatViewPathTarget =
  | { readonly view: "elfies" }
  | { readonly view: "profile"; readonly elfie: string }
  | { readonly view: "conversation"; readonly elfie: string }

const ChatViewStateSchema = z.discriminatedUnion("view", [
  z.object({ view: z.literal("elfies") }),
  z.object({ view: z.literal("profile"), elfie: ChatElfieIdSchema }),
  z.object({ view: z.literal("conversation"), elfie: ChatElfieIdSchema }),
])

const ELFIE_LIST_STATE: ChatViewState = { view: "elfies" }

class UnexpectedChatViewStateError extends Error {
  constructor() {
    super("Unexpected chat view state")
    this.name = "UnexpectedChatViewStateError"
  }
}

function assertNever(value: never): never {
  void value
  throw new UnexpectedChatViewStateError()
}

function searchParamsFrom(input: string | URLSearchParams): URLSearchParams {
  if (input instanceof URLSearchParams) return new URLSearchParams(input)
  const queryStart = input.indexOf("?")
  const query = queryStart === -1 ? input : input.slice(queryStart)
  return new URLSearchParams(query.startsWith("?") ? query.slice(1) : query)
}

function rawStateFrom(params: URLSearchParams): unknown {
  const view = params.get("view") ?? "elfies"
  switch (view) {
    case "elfies":
      return { view }
    case "profile":
    case "conversation":
      return { view, elfie: params.get("elfie") ?? undefined }
    default:
      return { view }
  }
}

function appendViewState(output: URLSearchParams, state: ChatViewState): void {
  switch (state.view) {
    case "elfies":
      output.set("view", "elfies")
      return
    case "profile":
      output.set("view", "profile")
      output.set("elfie", state.elfie)
      return
    case "conversation":
      output.set("view", "conversation")
      output.set("elfie", state.elfie)
      return
    default:
      return assertNever(state)
  }
}

export function parseChatViewState(input: string | URLSearchParams): ChatViewState {
  const parsed = ChatViewStateSchema.safeParse(rawStateFrom(searchParamsFrom(input)))
  return parsed.success ? parsed.data : ELFIE_LIST_STATE
}

export function buildChatViewPath(target: ChatViewPathTarget): string {
  const parsed = ChatViewStateSchema.safeParse(target)
  const state = parsed.success ? parsed.data : ELFIE_LIST_STATE
  const output = new URLSearchParams()
  appendViewState(output, state)
  return `${CHAT_PATH}?${output.toString()}`
}
