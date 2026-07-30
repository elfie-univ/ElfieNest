import "@testing-library/jest-dom/vitest"

import { cleanup } from "@testing-library/react"
import { afterEach, beforeEach } from "vitest"

class TestResizeObserver implements ResizeObserver {
  public disconnect(): void {}
  public observe(): void {}
  public unobserve(): void {}
}

globalThis.ResizeObserver = TestResizeObserver

beforeEach(() => {
  localStorage.clear()
  window.history.replaceState(null, "", "/")
  document.documentElement.lang = "zh-CN"
  document.documentElement.dir = "ltr"
})

afterEach(cleanup)
