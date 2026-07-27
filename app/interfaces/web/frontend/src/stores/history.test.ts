import { describe, expect, it, vi } from "vitest"

import { navigate, subscribeToLocation } from "./history"

describe("client location store", () => {
  it("notifies a History API navigation without reloading the document", () => {
    const listener = vi.fn()
    const release = subscribeToLocation(listener)

    navigate("/manage?section=nest")

    expect(listener).toHaveBeenCalledWith({
      pathname: "/manage",
      search: "?section=nest",
    })
    expect(window.location.pathname).toBe("/manage")
    release()
  })
})
