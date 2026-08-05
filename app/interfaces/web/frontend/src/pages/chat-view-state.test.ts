import { describe, expect, it } from "vitest"

import { buildChatViewPath, parseChatViewState } from "./chat-view-state"

describe("chat view state", () => {
  it("parses each canonical view when the URL is well formed", () => {
    const profileParams = new URLSearchParams("?view=profile&elfie=elfie_default")

    expect(parseChatViewState("?view=chats")).toEqual({ view: "chats" })
    expect(parseChatViewState("?view=elfies")).toEqual({ view: "elfies" })
    expect(parseChatViewState(profileParams)).toEqual({ view: "profile", elfie: "elfie_default" })
    expect(parseChatViewState("?view=conversation&elfie=resident-1")).toEqual({
      view: "conversation",
      elfie: "resident-1",
    })
  })

  it("canonicalizes missing unknown and invalid combinations to chat history", () => {
    expect(parseChatViewState("")).toEqual({ view: "chats" })
    expect(parseChatViewState("?view=profile")).toEqual({ view: "chats" })
    expect(parseChatViewState("?view=unknown&elfie=12345678")).toEqual({ view: "chats" })
    expect(parseChatViewState("?view=conversation&elfie=with%20space")).toEqual({ view: "chats" })
    expect(parseChatViewState("?view=profile&elfie=..%2Felfie")).toEqual({ view: "chats" })
  })

  it("accepts encoded stable ids and rejects encoded path-like values", () => {
    expect(parseChatViewState("?view=profile&elfie=elfie%5Fdefault")).toEqual({
      view: "profile",
      elfie: "elfie_default",
    })
    expect(parseChatViewState("?view=conversation&elfie=..%2Felfie")).toEqual({
      view: "chats",
    })
  })

  it("serializes only the canonical view state", () => {
    expect(buildChatViewPath({ view: "chats" })).toBe("/chat?view=chats")
    expect(buildChatViewPath({ view: "elfies" })).toBe("/chat?view=elfies")
    expect(buildChatViewPath({ view: "profile", elfie: "elfie_default" })).toBe(
      "/chat?view=profile&elfie=elfie_default",
    )
    expect(buildChatViewPath({ view: "conversation", elfie: "resident-1" })).toBe(
      "/chat?view=conversation&elfie=resident-1",
    )
  })

  it("keeps invalid input canonicalization stable across repeated parse and serialize cycles", () => {
    const once = buildChatViewPath(parseChatViewState("?view=profile&elfie=..%2Felfie&mock=1"))
    const canonicalSearch = new URL(once, "http://localhost").search
    const twice = buildChatViewPath(parseChatViewState(canonicalSearch))

    expect(once).toBe("/chat?view=chats")
    expect(twice).toBe(once)
  })
})
