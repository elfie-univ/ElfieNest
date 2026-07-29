import { describe, expect, it } from "vitest"

import { buildChatViewPath, parseChatViewState } from "./chat-view-state"

describe("chat view state", () => {
  it("parses each canonical view when the URL is well formed", () => {
    const profileParams = new URLSearchParams("?view=profile&elfie=elfie_default")

    expect(parseChatViewState("?view=elfies")).toEqual({ view: "elfies" })
    expect(parseChatViewState(profileParams)).toEqual({ view: "profile", elfie: "elfie_default" })
    expect(parseChatViewState("?view=conversation&elfie=resident-1")).toEqual({
      view: "conversation",
      elfie: "resident-1",
    })
  })

  it("canonicalizes missing unknown and invalid combinations to the Elfie list", () => {
    expect(parseChatViewState("")).toEqual({ view: "elfies" })
    expect(parseChatViewState("?view=profile")).toEqual({ view: "elfies" })
    expect(parseChatViewState("?view=unknown&elfie=12345678")).toEqual({ view: "elfies" })
    expect(parseChatViewState("?view=conversation&elfie=with%20space")).toEqual({ view: "elfies" })
    expect(parseChatViewState("?view=profile&elfie=..%2Felfie")).toEqual({ view: "elfies" })
  })

  it("accepts encoded stable ids and rejects encoded path-like values", () => {
    expect(parseChatViewState("?view=profile&elfie=elfie%5Fdefault")).toEqual({
      view: "profile",
      elfie: "elfie_default",
    })
    expect(parseChatViewState("?view=conversation&elfie=..%2Felfie")).toEqual({
      view: "elfies",
    })
  })

  it("serializes canonical paths while preserving only allowed unrelated flags", () => {
    expect(buildChatViewPath({ view: "elfies" }, "?mock=1&debug=1&elfie=99999999")).toBe(
      "/chat?view=elfies&mock=1",
    )
    expect(buildChatViewPath({ view: "profile", elfie: "elfie_default" }, "?mock=1")).toBe(
      "/chat?view=profile&elfie=elfie_default&mock=1",
    )
    expect(buildChatViewPath({ view: "conversation", elfie: "resident-1" }, "?mock=0")).toBe(
      "/chat?view=conversation&elfie=resident-1",
    )
  })

  it("keeps invalid input canonicalization stable across repeated parse and serialize cycles", () => {
    const once = buildChatViewPath(
      parseChatViewState("?view=profile&elfie=..%2Felfie&mock=1"),
      "?view=profile&elfie=..%2Felfie&mock=1",
    )
    const canonicalSearch = new URL(once, "http://localhost").search
    const twice = buildChatViewPath(parseChatViewState(canonicalSearch), canonicalSearch)

    expect(once).toBe("/chat?view=elfies&mock=1")
    expect(twice).toBe(once)
  })
})
