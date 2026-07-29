import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  interceptProductNavigation,
  navigate,
  replaceLocation,
  subscribeToLocation,
} from "./history"

describe("client location store", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/chat")
  })

  it("notifies a History API navigation without reloading the document", () => {
    const listener = vi.fn()
    const release = subscribeToLocation(listener)
    const documentMarker = document.createElement("meta")
    documentMarker.dataset["testMarker"] = "kept"
    document.head.append(documentMarker)

    navigate("/manage?section=nest")

    expect(listener).toHaveBeenCalledWith({
      pathname: "/manage",
      search: "?section=nest",
    })
    expect(window.location.pathname).toBe("/manage")
    expect(document.querySelector("meta[data-test-marker='kept']")).toBe(documentMarker)
    release()
  })

  it("emits the location-change custom event when navigate pushes state", () => {
    const listener = vi.fn()
    window.addEventListener("elfienest:location-change", listener)

    navigate("/chat?view=profile&elfie=12345678")

    expect(listener).toHaveBeenCalledTimes(1)
    expect(window.location.search).toBe("?view=profile&elfie=12345678")
    window.removeEventListener("elfienest:location-change", listener)
  })

  it("replaces an invalid location without adding a correction entry", () => {
    const listener = vi.fn()
    const release = subscribeToLocation(listener)
    const replaceState = vi.spyOn(window.history, "replaceState")
    const pushState = vi.spyOn(window.history, "pushState")

    replaceLocation("/chat?view=elfies&mock=1")

    expect(replaceState).toHaveBeenCalledWith({}, "", "/chat?view=elfies&mock=1")
    expect(pushState).not.toHaveBeenCalled()
    expect(listener).toHaveBeenCalledWith({ pathname: "/chat", search: "?view=elfies&mock=1" })
    replaceState.mockRestore()
    pushState.mockRestore()
    release()
  })

  it("observes browser back and forward through popstate", () => {
    const listener = vi.fn()
    const release = subscribeToLocation(listener)

    window.history.pushState({}, "", "/chat?view=elfies")
    window.history.pushState({}, "", "/chat?view=profile&elfie=12345678")
    window.history.replaceState({}, "", "/chat?view=elfies")
    window.dispatchEvent(new PopStateEvent("popstate"))
    window.history.replaceState({}, "", "/chat?view=profile&elfie=12345678")
    window.dispatchEvent(new PopStateEvent("popstate"))

    expect(listener).toHaveBeenNthCalledWith(1, { pathname: "/chat", search: "?view=elfies" })
    expect(listener).toHaveBeenNthCalledWith(2, { pathname: "/chat", search: "?view=profile&elfie=12345678" })
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
