import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"

import { HAPPY_EXPERIENCE, PRIVATE_MODULE_TITLES, SIGNED_IN_ADMIN } from "../../test/fixtures/elfie-profile"
import { projectElfieProfile } from "../../test/fixtures/project-elfie-profile"
import { ProfilePrivateModules } from "./ProfilePrivateModules"
import type { ElfieProfileProjection } from "./projection"

vi.mock("@visx/wordcloud", () => ({ Wordcloud: () => null }))
vi.mock("cytoscape", () => {
  const createCollection = () => ({
    addClass: vi.fn().mockReturnThis(),
    dijkstra: () => ({ pathTo: () => createCollection() }),
    removeClass: vi.fn().mockReturnThis(),
  })
  const createElement = (id: string) => ({
    ...createCollection(),
    empty: () => false,
    id: () => id,
    lock: vi.fn(),
    neighborhood: () => createCollection(),
  })
  const instance = {
    destroy: vi.fn(),
    elements: () => createCollection(),
    getElementById: (id: string) => createElement(id),
    layout: vi.fn(() => ({ run: vi.fn() })),
    nodes: () => [],
    on: vi.fn(),
    resize: vi.fn(),
  }
  return { default: () => instance }
})

createI18n()

describe("ProfilePrivateModules", () => {
  it("hides the five cognition modules while their feature switch is disabled", () => {
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    const { container } = render(<ProfilePrivateModules projection={projection} />)

    const buttons = screen.getAllByRole("button")
    expect(buttons.map((button) => button.textContent?.trim())).toEqual(PRIVATE_MODULE_TITLES.slice(5))
    for (const title of PRIVATE_MODULE_TITLES.slice(0, 5)) {
      expect(screen.queryByRole("button", { name: title })).not.toBeInTheDocument()
    }
    for (const button of buttons) expect(button).toHaveAttribute("aria-expanded", "false")
    expect(container.querySelector('[role="region"]')).toBeNull()
  })

  it("keeps the enabled care module interactive", async () => {
    const user = userEvent.setup()
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    render(<ProfilePrivateModules projection={projection} />)

    await user.click(screen.getByRole("button", { name: "粮食策略" }))
    const food = screen.getByRole("region", { name: "粮食策略" })
    expect(within(food).getByText("当前主粮")).toBeInTheDocument()
    expect(within(food).queryByRole("combobox")).not.toBeInTheDocument()
  })

  it("does not expose the disabled relationship module", () => {
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    render(<ProfilePrivateModules projection={projection} />)
    expect(screen.queryByRole("button", { name: "关系网络" })).not.toBeInTheDocument()
  })

  it("renders no private headings or payload for visitors", () => {
    const adopter = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    const visitor: ElfieProfileProjection = {
      ageLabel: "1 个月",
      kind: "visitor",
      ownerDisplayName: "管理员",
      publicProfile: adopter.publicProfile,
    }
    const { container } = render(<ProfilePrivateModules projection={visitor} />)
    expect(container).toBeEmptyDOMElement()
    expect(container).not.toHaveTextContent(PRIVATE_MODULE_TITLES.join("|"))
  })

  it("keeps archive and management sections as two views over the existing modules", () => {
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    const { container, unmount } = render(<ProfilePrivateModules projection={projection} section="archive" />)

    for (const title of PRIVATE_MODULE_TITLES.slice(0, 5)) {
      expect(container).not.toHaveTextContent(title)
    }
    expect(container).not.toHaveTextContent("粮食策略")
    unmount()

    const { container: managementContainer } = render(<ProfilePrivateModules projection={projection} section="manage" />)
    const managementButtons = screen.getAllByRole("button")
    expect(managementButtons.map((button) => button.textContent?.trim())).toEqual(["粮食策略", "Telegram 聊天", "Discord 聊天"])
    for (const button of managementButtons) expect(button).toHaveAttribute("aria-expanded", "false")
    expect(screen.getByRole("button", { name: "粮食策略" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Telegram 聊天" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Discord 聊天" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "近期关注" })).not.toBeInTheDocument()
    expect(managementContainer.querySelector('[role="region"]')).toBeNull()
  })
})
