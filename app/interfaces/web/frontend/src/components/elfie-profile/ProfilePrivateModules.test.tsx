import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"

import { HAPPY_EXPERIENCE, PRIVATE_MODULE_TITLES, SIGNED_IN_ADMIN } from "./mock-data"
import { ProfilePrivateModules } from "./ProfilePrivateModules"
import type { ElfieProfileProjection } from "./projection"
import { projectElfieProfile } from "./projection"

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
  it("renders the approved six headings in order and keeps every body collapsed", () => {
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    const { container } = render(<ProfilePrivateModules projection={projection} />)

    const buttons = screen.getAllByRole("button")
    expect(buttons.map((button) => button.textContent?.trim())).toEqual(PRIVATE_MODULE_TITLES)
    for (const button of buttons) expect(button).toHaveAttribute("aria-expanded", "false")
    expect(container.querySelector('[role="region"]')).toBeNull()
  })

  it("opens multiple modules and uses one-glance visual summaries", async () => {
    const user = userEvent.setup()
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    render(<ProfilePrivateModules projection={projection} />)

    await user.click(screen.getByRole("button", { name: "近期关注" }))
    const focus = screen.getByRole("region", { name: "近期关注" })
    expect(within(focus).getByRole("img", { name: "近期关注主题" })).toBeInTheDocument()
    expect(within(focus).queryByText(/次|条经历/)).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "重要经历" }))
    const timeline = screen.getByRole("region", { name: "重要经历" })
    expect(within(timeline).getByRole("list", { name: "重要经历时间线" })).toBeInTheDocument()
    expect(timeline.querySelector("time[datetime='2026-06-30']")).not.toBeNull()

    await user.click(screen.getByRole("button", { name: "关系网络" }))
    const relationships = screen.getByRole("region", { name: "关系网络" })
    expect(within(relationships).getByRole("button", { name: "人类" })).toBeInTheDocument()
    expect(within(relationships).getByRole("button", { name: "精灵" })).toBeInTheDocument()
    expect(within(relationships).getByRole("img", { name: "关系网络图" })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "知识与信念" }))
    const knowledge = screen.getByRole("region", { name: "知识与信念" })
    expect(within(knowledge).getByRole("img", { name: "知识与信念图" })).toBeInTheDocument()
    expect(within(knowledge).queryByRole("list", { name: "知识与信念路径" })).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "粮食策略" }))
    const food = screen.getByRole("region", { name: "粮食策略" })
    expect(within(food).getByText("当前主粮")).toBeInTheDocument()
    expect(within(food).queryByRole("combobox")).not.toBeInTheDocument()
  })

  it("keeps the relationship filter bounded and always retains the Elfie itself", async () => {
    const user = userEvent.setup()
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)
    render(<ProfilePrivateModules projection={projection} />)
    await user.click(screen.getByRole("button", { name: "关系网络" }))
    const relationships = screen.getByRole("region", { name: "关系网络" })
    await user.click(within(relationships).getByRole("button", { name: "人类" }))
    expect(within(relationships).getByRole("button", { name: "关系节点：Happy" })).toBeInTheDocument()
    expect(within(relationships).getByRole("button", { name: "关系节点：主人" })).toBeInTheDocument()
    expect(within(relationships).queryByRole("button", { name: "关系节点：星星" })).not.toBeInTheDocument()
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
})
