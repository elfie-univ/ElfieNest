import { render, screen } from "@testing-library/react"
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
          onChat={vi.fn()}
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
})
