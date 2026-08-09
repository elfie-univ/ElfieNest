import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeAll, describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"

import { ownerWrite } from "../../api/client"
import { HAPPY_EXPERIENCE } from "../../test/fixtures/elfie-profile"
import { ProfileCareSettings } from "./ProfileCareSettings"

vi.mock("../../api/client", () => ({ ownerWrite: vi.fn() }))

createI18n()

beforeAll(() => {
  Element.prototype.hasPointerCapture = vi.fn(() => false)
  Element.prototype.setPointerCapture = vi.fn()
  Element.prototype.releasePointerCapture = vi.fn()
  Element.prototype.scrollIntoView = vi.fn()
})

describe("ProfileCareSettings", () => {
  it("lets the owner choose and save a food strategy", async () => {
    const user = userEvent.setup()
    const onSaved = vi.fn<() => Promise<void>>().mockResolvedValue(undefined)
    const settings = {
      ...HAPPY_EXPERIENCE.careSettings,
      food: {
        ...HAPPY_EXPERIENCE.careSettings.food,
        options: [
          ...HAPPY_EXPERIENCE.careSettings.food.options,
          { id: "sensitive", label: "低敏粮" },
        ],
      },
    }
    vi.mocked(ownerWrite).mockResolvedValue({})

    render(<ProfileCareSettings csrfToken="csrf-token" elfieId="12345678" onSaved={onSaved} settings={settings} />)

    const selector = screen.getByRole("combobox", { name: "当前主粮" })
    expect(screen.getAllByText("当前主粮")).toHaveLength(1)
    expect(screen.queryByText("选择主粮")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "保存" })).toBeInTheDocument()
    selector.focus()
    await user.keyboard("{Enter}{ArrowDown}{Enter}")
    await user.click(screen.getByRole("button", { name: "保存" }))

    await waitFor(() => expect(ownerWrite).toHaveBeenCalledWith(
      "/api/user/elfies/12345678/food-policy/",
      "PUT",
      "csrf-token",
      { main_food_id: "sensitive" },
    ))
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
  })

  it("explains when no main food is available", () => {
    const settings = {
      ...HAPPY_EXPERIENCE.careSettings,
      food: {
        ...HAPPY_EXPERIENCE.careSettings.food,
        options: [],
      },
    }

    render(<ProfileCareSettings settings={settings} />)

    expect(screen.getByText("当前没有可用主粮，请联系管理员。")).toBeInTheDocument()
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "保存" })).not.toBeInTheDocument()
  })
})
