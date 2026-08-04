import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"

import type { RelationshipWorld } from "./model"
import { ProfileRelationshipWorld } from "./ProfileRelationshipWorld"

vi.mock("cytoscape", () => {
  const createCollection = () => ({
    addClass: vi.fn().mockReturnThis(),
    data: vi.fn(),
    dijkstra: () => ({ distanceTo: () => 0, pathTo: () => createCollection() }),
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
    batch: (callback: () => void) => callback(),
    destroy: vi.fn(),
    elements: () => createCollection(),
    getElementById: (id: string) => createElement(id),
    nodes: () => ({ forEach: vi.fn() }),
    on: vi.fn(),
    resize: vi.fn(),
  }
  return { default: () => instance }
})

createI18n()

const WORLD: RelationshipWorld = {
  nodes: [
    { id: "self", label: "Happy", kind: "self", weight: 1 },
    ...Array.from({ length: 59 }, (_, index) => ({
      id: index % 2 === 0 ? `human-${index}` : `elfie-${index}`,
      label: index % 2 === 0 ? `人类 ${index}` : `精灵 ${index}`,
      kind: index % 2 === 0 ? "human" as const : "elfie" as const,
      weight: Math.max(0.1, 0.95 - index / 30),
    })),
  ],
  edges: [],
}

describe("ProfileRelationshipWorld", () => {
  it("shows up to fifty nodes without a detail toggle", () => {
    render(<ProfileRelationshipWorld status="ready" world={WORLD} />)

    expect(screen.queryByRole("checkbox", { name: "详细" })).not.toBeInTheDocument()
    expect(screen.getByRole("img", { name: "关系网络图" })).toBeInTheDocument()
    expect(screen.queryByRole("list", { name: "关系连接" })).not.toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: /关系节点/ })).toHaveLength(50)
  })

  it("keeps the current Elfie centered while the human filter excludes other Elfies", async () => {
    const user = userEvent.setup()
    render(<ProfileRelationshipWorld status="ready" world={WORLD} />)

    await user.click(screen.getByRole("button", { name: "人类" }))
    const nodeButtons = screen.getAllByRole("button", { name: /关系节点/ })
    expect(nodeButtons).toHaveLength(31)
    expect(screen.getByRole("button", { name: "关系节点：Happy" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "关系节点：人类 0" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "关系节点：精灵 1" })).not.toBeInTheDocument()
  })

  it("exposes node selection without turning the selected node into the center", async () => {
    const user = userEvent.setup()
    render(<ProfileRelationshipWorld status="ready" world={WORLD} />)

    const selected = screen.getByRole("button", { name: "关系节点：人类 0" })
    await user.click(selected)

    expect(selected).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: "关系节点：Happy" })).toHaveAttribute("aria-pressed", "false")
  })
})
