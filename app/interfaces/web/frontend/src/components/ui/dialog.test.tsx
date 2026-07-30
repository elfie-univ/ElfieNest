import { render, screen } from "@testing-library/react"
import type { i18n } from "i18next"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"

import { createI18n } from "@/i18n/config"
import { initializeLocale, type SupportedLocale } from "@/i18n/locale"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "./dialog"

function renderWithLocale(locale: SupportedLocale): i18n {
  const instance = createI18n()
  initializeLocale(instance, {
    storage: localStorage,
    browserLanguages: [locale],
    documentElement: document.documentElement,
  })
  render(
    <I18nextProvider i18n={instance}>
      <Dialog open>
        <DialogContent>
          <DialogTitle>Shared dialog title</DialogTitle>
          <DialogDescription>Shared dialog description</DialogDescription>
        </DialogContent>
      </Dialog>
    </I18nextProvider>,
  )
  return instance
}

describe("DialogContent", () => {
  it("localizes the close button accessible name in Chinese", () => {
    renderWithLocale("zh-CN")

    expect(screen.getByRole("button", { name: "关闭" })).toBeInTheDocument()
  })

  it("localizes the close button accessible name in English", () => {
    renderWithLocale("en-US")

    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument()
  })
})
