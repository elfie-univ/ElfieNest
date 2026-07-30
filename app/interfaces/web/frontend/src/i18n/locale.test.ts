import { readFile } from "node:fs/promises"
import { resolve } from "node:path"

import { describe, expect, it, vi } from "vitest"

import { createI18n } from "./config"
import * as localeModule from "./locale"
import {
  getBrowserStorage,
  initializeLocale,
  matchBrowserLocale,
  setLocale,
} from "./locale"

describe("locale bootstrap", () => {
  it("exposes one locale switch operation for UI consumers", () => {
    // Given: the locale module used by every language control.
    const moduleExports = localeModule

    // When: its public switching contract is inspected.
    const hasSetLocale = "setLocale" in moduleExports

    // Then: consumers share one operation instead of page-level locale state.
    expect(hasSetLocale).toBe(true)
  })

  it("uses a valid saved English locale before rendering", () => {
    // Given: the browser has a valid locale preference from a previous visit.
    localStorage.setItem("elfienest.locale", "en-US")

    // When: the current synchronous i18n bootstrap runs.
    const instance = createI18n()
    initializeLocale(instance, {
      storage: localStorage,
      browserLanguages: ["zh-CN"],
      documentElement: document.documentElement,
    })

    // Then: the first render must already use the saved locale.
    expect(instance.language).toBe("en-US")
  })

  it("matches English browser language families when no preference is saved", () => {
    // Given: no saved preference and a browser whose first supported family is English.
    const instance = createI18n()

    // When: locale bootstrap inspects the ordered browser language list.
    const locale = initializeLocale(instance, {
      storage: localStorage,
      browserLanguages: ["ja-JP", "en-GB", "zh-CN"],
      documentElement: document.documentElement,
    })

    // Then: regional English is normalized to the closed English locale.
    expect(locale).toBe("en-US")
    expect(instance.language).toBe("en-US")
  })

  it("matches Traditional Chinese browser tags to Simplified Chinese UI", () => {
    // Given: the browser prefers a Traditional Chinese regional tag.
    const browserLanguages = ["zh-Hant", "en-GB"] as const

    // When: the closed browser-language matcher evaluates it.
    const locale = matchBrowserLocale(browserLanguages)

    // Then: every Chinese family tag maps to the sole supported Chinese locale.
    expect(locale).toBe("zh-CN")
  })

  it("ignores and discards a damaged saved value before browser matching", () => {
    // Given: storage contains a value outside the supported locale set.
    localStorage.setItem("elfienest.locale", "not-a-locale")
    const instance = createI18n()

    // When: locale bootstrap parses the untrusted stored value.
    const locale = initializeLocale(instance, {
      storage: localStorage,
      browserLanguages: ["en-US"],
      documentElement: document.documentElement,
    })

    // Then: the invalid value is removed and browser matching remains available.
    expect(locale).toBe("en-US")
    expect(localStorage.getItem("elfienest.locale")).toBeNull()
  })

  it("rejects a regional tag stored outside the exact supported set", () => {
    // Given: storage was manually changed to a regional value the UI never writes.
    localStorage.setItem("elfienest.locale", "en-GB")
    const instance = createI18n()

    // When: bootstrap parses storage before matching the browser.
    const locale = initializeLocale(instance, {
      storage: localStorage,
      browserLanguages: ["zh-Hant"],
      documentElement: document.documentElement,
    })

    // Then: the invalid stored tag is discarded and the browser family is mapped.
    expect(locale).toBe("zh-CN")
    expect(localStorage.getItem("elfienest.locale")).toBeNull()
  })

  it("falls back to Chinese when storage is unreadable and the browser is unsupported", () => {
    // Given: privacy settings make storage unreadable and the browser reports Japanese.
    const unavailableStorage: Pick<Storage, "getItem" | "removeItem" | "setItem"> = {
      getItem() {
        throw new DOMException("Storage disabled", "SecurityError")
      },
      removeItem() {},
      setItem() {},
    }
    const instance = createI18n()

    // When: locale bootstrap crosses the unavailable storage boundary.
    const locale = initializeLocale(instance, {
      storage: unavailableStorage,
      browserLanguages: ["ja-JP"],
      documentElement: document.documentElement,
    })

    // Then: the application remains usable with the deterministic Chinese fallback.
    expect(locale).toBe("zh-CN")
    expect(instance.language).toBe("zh-CN")
    expect(document.documentElement.lang).toBe("zh-CN")
    expect(document.documentElement.dir).toBe("ltr")
  })

  it("continues bootstrap when the window localStorage getter throws", () => {
    // Given: a browser security policy rejects access to the storage property itself.
    const getterSpy = vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("Storage disabled", "SecurityError")
    })
    const instance = createI18n()

    try {
      // When: entry-level storage resolution and locale initialization run together.
      const storage = getBrowserStorage(window)
      const locale = initializeLocale(instance, {
        storage,
        browserLanguages: ["ja-JP"],
        documentElement: document.documentElement,
      })

      // Then: an unavailable-storage adapter permits the deterministic fallback.
      expect(locale).toBe("zh-CN")
      expect(instance.language).toBe("zh-CN")
      expect(document.documentElement.lang).toBe("zh-CN")
      expect(document.documentElement.dir).toBe("ltr")
    } finally {
      getterSpy.mockRestore()
    }
  })

  it("updates root language metadata synchronously without changing navigation", () => {
    // Given: a saved English locale and an existing deep link.
    localStorage.setItem("elfienest.locale", "en-US")
    window.history.replaceState({ source: "test" }, "", "/manage?section=users#active")
    const initialUrl = window.location.href
    const initialHistoryLength = window.history.length
    const instance = createI18n()

    // When: locale bootstrap completes before a caller can render.
    initializeLocale(instance, {
      storage: localStorage,
      browserLanguages: ["zh-CN"],
      documentElement: document.documentElement,
    })

    // Then: i18n and document metadata are immediately aligned without navigation.
    expect(instance.isInitialized).toBe(true)
    expect(instance.language).toBe("en-US")
    expect(document.documentElement.lang).toBe("en-US")
    expect(document.documentElement.dir).toBe("ltr")
    expect(window.location.href).toBe(initialUrl)
    expect(window.history.length).toBe(initialHistoryLength)
  })

  it("switches immediately, persists the choice, and preserves the current URL", () => {
    // Given: a Chinese instance on a deep-linked page.
    window.history.replaceState({ source: "switch" }, "", "/chat?view=profile#details")
    const initialUrl = window.location.href
    const initialHistoryLength = window.history.length
    const instance = createI18n()

    // When: the shared locale operation switches to English.
    setLocale(instance, "en-US", {
      storage: localStorage,
      browserLanguages: ["zh-CN"],
      documentElement: document.documentElement,
    })

    // Then: runtime, persistence, and metadata change without navigation state loss.
    expect(instance.language).toBe("en-US")
    expect(localStorage.getItem("elfienest.locale")).toBe("en-US")
    expect(document.documentElement.lang).toBe("en-US")
    expect(document.documentElement.dir).toBe("ltr")
    expect(window.location.href).toBe(initialUrl)
    expect(window.history.length).toBe(initialHistoryLength)
  })

  it("restores an explicitly switched locale in a fresh i18n instance", () => {
    // Given: a user explicitly switches one isolated instance to English.
    const firstInstance = createI18n()
    setLocale(firstInstance, "en-US", {
      storage: localStorage,
      browserLanguages: ["zh-CN"],
      documentElement: document.documentElement,
    })
    const refreshedInstance = createI18n()

    // When: a fresh bootstrap simulates the next page load.
    const restoredLocale = initializeLocale(refreshedInstance, {
      storage: localStorage,
      browserLanguages: ["zh-CN"],
      documentElement: document.documentElement,
    })

    // Then: the saved closed-set locale wins over the browser language.
    expect(restoredLocale).toBe("en-US")
    expect(refreshedInstance.language).toBe("en-US")
  })

  it("persists an explicit switch back to Chinese", () => {
    // Given: an instance initialized from a saved English preference.
    localStorage.setItem("elfienest.locale", "en-US")
    const instance = createI18n()
    initializeLocale(instance, {
      storage: localStorage,
      browserLanguages: ["en-US"],
      documentElement: document.documentElement,
    })

    // When: the user explicitly switches back to Chinese.
    setLocale(instance, "zh-CN", {
      storage: localStorage,
      browserLanguages: ["en-US"],
      documentElement: document.documentElement,
    })

    // Then: runtime, persistence, and metadata all use the closed Chinese locale.
    expect(instance.language).toBe("zh-CN")
    expect(localStorage.getItem("elfienest.locale")).toBe("zh-CN")
    expect(document.documentElement.lang).toBe("zh-CN")
    expect(document.documentElement.dir).toBe("ltr")
  })

  it("keeps the immediate switch usable when persistence is unavailable", () => {
    // Given: storage allows reads but rejects writes under a privacy policy.
    let writeAttempts = 0
    const unavailableStorage: Pick<Storage, "getItem" | "removeItem" | "setItem"> = {
      getItem() {
        return null
      },
      removeItem() {},
      setItem() {
        writeAttempts += 1
        throw new DOMException("Storage disabled", "SecurityError")
      },
    }
    const instance = createI18n()

    // When: the user switches to English.
    setLocale(instance, "en-US", {
      storage: unavailableStorage,
      browserLanguages: ["zh-CN"],
      documentElement: document.documentElement,
    })

    // Then: persistence was attempted, while runtime and metadata still switch safely.
    expect(writeAttempts).toBe(1)
    expect(instance.language).toBe("en-US")
    expect(document.documentElement.lang).toBe("en-US")
    expect(document.documentElement.dir).toBe("ltr")
  })
})

describe("locale entry contract", () => {
  it("initializes one React i18n provider before createRoot", async () => {
    // Given: the browser entry source used for every production route.
    const mainSource = await readFile(resolve(import.meta.dirname, "../main.tsx"), "utf8")

    // When: initialization and render-boundary positions are inspected.
    const createInstancePosition = mainSource.indexOf("createI18n()")
    const initializePosition = mainSource.indexOf("initializeLocale(")
    const createRootPosition = mainSource.indexOf("createRoot(mount)")
    const providerCount = mainSource.match(/<I18nextProvider\b/g)?.length ?? 0

    // Then: one provider receives a synchronously initialized instance before render.
    expect(createInstancePosition).toBeGreaterThan(-1)
    expect(initializePosition).toBeGreaterThan(createInstancePosition)
    expect(createRootPosition).toBeGreaterThan(initializePosition)
    expect(providerCount).toBe(1)
  })

  it("resolves browser storage through the safe locale boundary", async () => {
    // Given: the browser entry source can run where the localStorage getter itself throws.
    const mainSource = await readFile(resolve(import.meta.dirname, "../main.tsx"), "utf8")

    // When: its storage dependency is inspected before locale initialization.
    const readsStorageDirectly = /storage:\s*(?:window\.)?localStorage\b/.test(mainSource)

    // Then: the entry delegates access to the locale boundary instead of evaluating the getter.
    expect(readsStorageDirectly).toBe(false)
    expect(mainSource).toContain("getBrowserStorage(")
  })

  it("ships deterministic fallback document metadata before JavaScript runs", async () => {
    // Given: the static HTML document served before the application bundle executes.
    const htmlSource = await readFile(resolve(import.meta.dirname, "../../index.html"), "utf8")

    // When: the root document element is inspected.
    const htmlTag = htmlSource.match(/<html\b[^>]*>/)?.[0]

    // Then: fallback language and direction are valid before runtime detection.
    expect(htmlTag).toContain('lang="zh-CN"')
    expect(htmlTag).toContain('dir="ltr"')
  })
})
