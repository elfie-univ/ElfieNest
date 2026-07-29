import { describe, expect, it, vi } from "vitest"

import { interceptProductNavigation, navigate, subscribeToLocation } from "./history"

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

  it("keeps the Owner monitor link inside product history", () => {
    const originalLocation = `${window.location.pathname}${window.location.search}${window.location.hash}`
    const anchor = document.createElement("a")
    anchor.href = "/monitor"
    document.body.append(anchor)
    document.addEventListener("click", interceptProductNavigation)

    try {
      const event = new MouseEvent("click", { bubbles: true, button: 0, cancelable: true })
      anchor.dispatchEvent(event)

      expect(event.defaultPrevented).toBe(true)
      expect(window.location.pathname).toBe("/monitor")
    } finally {
      document.removeEventListener("click", interceptProductNavigation)
      anchor.remove()
      window.history.replaceState({}, "", originalLocation)
    }

    expect(`${window.location.pathname}${window.location.search}${window.location.hash}`).toBe(originalLocation)
  })
})
