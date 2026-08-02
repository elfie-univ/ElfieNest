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
  it("renders English list chrome without translating names, species IDs, or entity IDs", () => {
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

    // Then: owned chrome is translated and stable entity content is preserved.
    expect(screen.getByRole("group", { name: "Elfie scope" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "All 2" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "My Elfies" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "View Happy's profile" })).toBeInTheDocument()
    expect(screen.getByText("fox · 12345678")).toBeInTheDocument()
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
