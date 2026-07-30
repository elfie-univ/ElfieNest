import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { i18n } from "i18next"
import { I18nextProvider } from "react-i18next"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"

import { createI18n } from "@/i18n/config"
import {
  initializeLocale,
  localeStorageKey,
  type SupportedLocale,
} from "@/i18n/locale"

import { LanguageSwitcher } from "./LanguageSwitcher"

const inaccessibleStorage = {
  getItem: () => null,
  removeItem: () => undefined,
  setItem: () => undefined,
} as const

type RenderOptions = {
  readonly disabled?: boolean
  readonly locale?: SupportedLocale
}

function renderSwitcher(options: RenderOptions = {}): i18n {
  const instance = createI18n()
  initializeLocale(instance, {
    storage: localStorage,
    browserLanguages: [options.locale ?? "zh-CN"],
    documentElement: document.documentElement,
  })
  render(
    <I18nextProvider i18n={instance}>
      <LanguageSwitcher disabled={options.disabled ?? false} />
    </I18nextProvider>,
  )
  return instance
}

describe("LanguageSwitcher", () => {
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.scrollIntoView = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("exposes one labelled combobox with the exact self-named locale options", async () => {
    // Given: the shared switcher starts in Simplified Chinese.
    const user = userEvent.setup()
    renderSwitcher()

    // When: the user opens its accessible combobox.
    const trigger = screen.getByRole("combobox", { name: "语言" })
    await user.click(trigger)

    // Then: the one listbox exposes only the supported locale names.
    expect(trigger).toHaveClass("focus-visible:ring-3")
    expect(screen.getByRole("listbox")).toBeInTheDocument()
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "简体中文",
      "English",
    ])
    expect(screen.getByRole("option", { name: "简体中文" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
  })

  it("switches immediately by pointer while persisting metadata without changing the URL", async () => {
    // Given: URL and history state belong to the current product flow.
    const user = userEvent.setup()
    window.history.replaceState({ step: 4 }, "", "/setup?step=4#model")
    const originalUrl = window.location.href
    const originalState = window.history.state
    const instance = renderSwitcher()

    // When: English is chosen with the pointer.
    const trigger = screen.getByRole("combobox", { name: "语言" })
    await user.click(trigger)
    await user.click(screen.getByRole("option", { name: "English" }))

    // Then: locale state changes in place and focus returns to the trigger.
    expect(instance.resolvedLanguage).toBe("en-US")
    expect(trigger).toHaveTextContent("English")
    expect(trigger).toHaveFocus()
    expect(localStorage.getItem(localeStorageKey)).toBe("en-US")
    expect(document.documentElement).toHaveAttribute("lang", "en-US")
    expect(document.documentElement).toHaveAttribute("dir", "ltr")
    expect(window.location.href).toBe(originalUrl)
    expect(window.history.state).toEqual(originalState)
  })

  it("switches from English back to Simplified Chinese", async () => {
    // Given: the provider and document start in English.
    const user = userEvent.setup()
    const instance = renderSwitcher({ locale: "en-US" })

    // When: the user selects the self-named Chinese option.
    await user.click(screen.getByRole("combobox", { name: "Language" }))
    await user.click(screen.getByRole("option", { name: "简体中文" }))

    // Then: provider, persistence, metadata, and visible selection agree.
    expect(instance.resolvedLanguage).toBe("zh-CN")
    expect(localStorage.getItem(localeStorageKey)).toBe("zh-CN")
    expect(document.documentElement).toHaveAttribute("lang", "zh-CN")
    expect(screen.getByRole("combobox", { name: "语言" })).toHaveTextContent(
      "简体中文",
    )
  })

  it("supports keyboard selection and preserves trigger focus", async () => {
    // Given: a keyboard-only user tabs to the Chinese trigger.
    const user = userEvent.setup()
    const instance = renderSwitcher()
    const trigger = screen.getByRole("combobox", { name: "语言" })
    await user.tab()

    // When: the user opens, moves once, and commits with Enter.
    await user.keyboard("{Enter}{ArrowDown}{Enter}")

    // Then: English is committed and the same trigger remains focused.
    expect(instance.resolvedLanguage).toBe("en-US")
    expect(trigger).toHaveTextContent("English")
    expect(trigger).toHaveFocus()
  })

  it("cancels keyboard selection with Escape without changing the locale", async () => {
    // Given: the switcher currently uses Chinese.
    const user = userEvent.setup()
    const instance = renderSwitcher()
    const trigger = screen.getByRole("combobox", { name: "语言" })
    trigger.focus()

    // When: the user moves to English but cancels the open listbox.
    await user.keyboard("{Enter}{ArrowDown}{Escape}")

    // Then: Chinese remains active and focus returns to the trigger.
    expect(instance.resolvedLanguage).toBe("zh-CN")
    expect(trigger).toHaveTextContent("简体中文")
    expect(trigger).toHaveFocus()
  })

  it("does not change locale while disabled", async () => {
    // Given: a product flow has disabled the shared language control.
    const user = userEvent.setup()
    const instance = renderSwitcher({ disabled: true })
    const trigger = screen.getByRole("combobox", { name: "语言" })

    // When: pointer and keyboard input target the disabled trigger.
    await user.click(trigger)
    trigger.focus()
    await user.keyboard("{Enter}{ArrowDown}{Enter}")

    // Then: no listbox or locale mutation occurs.
    expect(trigger).toBeDisabled()
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
    expect(instance.resolvedLanguage).toBe("zh-CN")
    expect(localStorage.getItem(localeStorageKey)).toBeNull()
  })

  it("falls back to Chinese for an invalid saved and browser locale", () => {
    // Given: persisted and browser locale inputs are outside the supported set.
    localStorage.setItem(localeStorageKey, "fr-FR")
    const instance = createI18n()
    initializeLocale(instance, {
      storage: localStorage,
      browserLanguages: ["ja-JP"],
      documentElement: document.documentElement,
    })

    // When: the shared switcher renders from the normalized provider state.
    render(
      <I18nextProvider i18n={instance}>
        <LanguageSwitcher />
      </I18nextProvider>,
    )

    // Then: it shows the safe Chinese option and discards invalid persistence.
    expect(screen.getByRole("combobox", { name: "语言" })).toHaveTextContent(
      "简体中文",
    )
    expect(localStorage.getItem(localeStorageKey)).toBeNull()
    expect(document.documentElement).toHaveAttribute("lang", "zh-CN")
  })

  it("renders the Chinese fallback when the provider reports an unsupported language", async () => {
    // Given: a foreign provider state crosses the component boundary.
    const instance = createI18n()
    await instance.changeLanguage("fr-FR")

    // When: the switcher derives its controlled value.
    render(
      <I18nextProvider i18n={instance}>
        <LanguageSwitcher />
      </I18nextProvider>,
    )

    // Then: the closed locale set safely resolves to Chinese.
    expect(screen.getByRole("combobox", { name: "语言" })).toHaveTextContent(
      "简体中文",
    )
  })

  it("keeps immediate switching available when the localStorage getter is unavailable", async () => {
    // Given: the provider is valid but browser storage access itself throws.
    const user = userEvent.setup()
    const instance = createI18n()
    initializeLocale(instance, {
      storage: inaccessibleStorage,
      browserLanguages: ["zh-CN"],
      documentElement: document.documentElement,
    })
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("storage blocked", "SecurityError")
    })
    render(
      <I18nextProvider i18n={instance}>
        <LanguageSwitcher />
      </I18nextProvider>,
    )

    // When: the user selects English.
    await user.click(screen.getByRole("combobox", { name: "语言" }))
    await user.click(screen.getByRole("option", { name: "English" }))

    // Then: immediate provider and document state still update.
    expect(instance.resolvedLanguage).toBe("en-US")
    expect(document.documentElement).toHaveAttribute("lang", "en-US")
    expect(screen.getByRole("combobox", { name: "Language" })).toHaveTextContent(
      "English",
    )
  })

  it("keeps immediate switching available when localStorage writes fail", async () => {
    // Given: browser storage can be read but rejects writes.
    const user = userEvent.setup()
    const instance = renderSwitcher()
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota exceeded", "QuotaExceededError")
    })

    // When: the user selects English.
    await user.click(screen.getByRole("combobox", { name: "语言" }))
    await user.click(screen.getByRole("option", { name: "English" }))

    // Then: locale and metadata still switch synchronously.
    expect(instance.resolvedLanguage).toBe("en-US")
    expect(document.documentElement).toHaveAttribute("lang", "en-US")
    expect(screen.getByRole("combobox", { name: "Language" })).toHaveTextContent(
      "English",
    )
  })

  it.each([375, 768, 1280])(
    "uses shrink-safe intrinsic sizing inside a %ipx container",
    (width) => {
      // Given: the switcher is placed in a supported responsive container.
      const instance = createI18n()
      initializeLocale(instance, {
        storage: localStorage,
        browserLanguages: ["en-US"],
        documentElement: document.documentElement,
      })

      // When: the shared component renders at the target contract width.
      const { container } = render(
        <div style={{ width }}>
          <I18nextProvider i18n={instance}>
            <LanguageSwitcher />
          </I18nextProvider>
        </div>,
      )

      // Then: its wrapper and control may shrink without a fixed inline width.
      const wrapper = container.querySelector<HTMLElement>("[data-language-switcher]")
      expect(wrapper).toHaveClass("min-w-0", "max-w-full")
      expect(wrapper).not.toHaveStyle({ width: expect.stringMatching(/px/) })
      expect(screen.getByRole("combobox", { name: "Language" })).toHaveClass(
        "w-full",
      )
    },
  )
})
