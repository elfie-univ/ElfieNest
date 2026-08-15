import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"
import { ElfieList } from "./ElfieList"
import type { ElfieListItem } from "./elfie-list-model"

const ITEMS = [
  {
    adopterAccountId: "owner-1",
    profile: { elfie_id: "12345678", name: "Happy", portrait_url: "", species_id: "fox" },
  },
  {
    adopterAccountId: "owner-2",
    profile: { elfie_id: "23456789", name: "Kettle", portrait_url: "", species_id: "dog" },
  },
] as const satisfies readonly ElfieListItem[]

describe("ElfieList i18n", () => {
  it("guides a first-time visitor from the empty Elfie list", () => {
    const instance = createI18n()
    void instance.changeLanguage("zh-CN")

    render(
      <I18nextProvider i18n={instance}>
        <ElfieList
          filter="all"
          items={[]}
          onFilterChange={vi.fn()}
          onProfile={vi.fn()}
          query=""
          selectedId={null}
          viewerAccountId="owner-1"
        />
      </I18nextProvider>,
    )

    expect(screen.getByRole("heading", { name: "你的巢还在等第一位住客" })).toBeInTheDocument()
    expect(screen.getByText("点击右上角的“＋领养”，开始第一段相遇。")).toBeInTheDocument()
    expect(document.querySelector(".elfie-list")).toHaveClass("elfie-list--empty")
    expect(screen.queryByRole("group", { name: "精灵范围" })).not.toBeInTheDocument()
  })

  it("renders English list chrome with only Elfie names visible", () => {
    // Given: a mixed ownership list under the English locale.
    const instance = createI18n()
    void instance.changeLanguage("en-US")

    // When: the list is rendered.
    render(
      <I18nextProvider i18n={instance}>
        <ElfieList
          filter="all"
          items={ITEMS}
          onFilterChange={vi.fn()}
          onProfile={vi.fn()}
          query=""
          selectedId="12345678"
          viewerAccountId="owner-1"
        />
      </I18nextProvider>,
    )

    // Then: owned chrome is translated, names remain visible, and identifiers stay hidden.
    expect(screen.getByRole("group", { name: "Elfie scope" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "All 2" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "My Elfies" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "View Happy's profile" })).toBeInTheDocument()
    expect(screen.getByText("Happy")).toBeInTheDocument()
    expect(screen.queryByText("fox · 12345678")).not.toBeInTheDocument()
    expect(screen.getByText("Kettle")).toBeInTheDocument()
  })

  it("uses each row only to select the Elfie profile", async () => {
    // Given: a mixed ownership list under the English locale.
    const user = userEvent.setup()
    const onProfile = vi.fn()
    const instance = createI18n()
    void instance.changeLanguage("en-US")

    // When: the list is rendered and a row is selected.
    render(
      <I18nextProvider i18n={instance}>
        <ElfieList
          filter="all"
          items={ITEMS}
          onFilterChange={vi.fn()}
          onProfile={onProfile}
          query=""
          selectedId={null}
          viewerAccountId="owner-1"
        />
      </I18nextProvider>,
    )
    const profileButton = screen.getByRole("button", { name: "View Kettle's profile" })
    const row = profileButton.closest("article")
    if (!(row instanceof HTMLElement)) throw new TypeError("Expected an Elfie list row")
    await user.click(profileButton)

    // Then: the row has one profile action and never exposes a chat action.
    expect(within(row).getAllByRole("button")).toHaveLength(1)
    expect(screen.queryByRole("button", { name: "Chat with Kettle" })).not.toBeInTheDocument()
    expect(onProfile).toHaveBeenCalledWith("23456789")
  })
})
