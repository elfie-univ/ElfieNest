import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { createI18n } from "../../i18n/config"

import { ProfileKnowledgeBeliefs } from "./ProfileKnowledgeBeliefs"

vi.mock("cytoscape", () => {
  const createCollection = () => ({
    addClass: vi.fn().mockReturnThis(),
    removeClass: vi.fn().mockReturnThis(),
  })
  const createElement = (id: string) => ({
    ...createCollection(),
    empty: () => false,
    id: () => id,
    neighborhood: () => createCollection(),
  })
  const instance = {
    destroy: vi.fn(),
    elements: () => createCollection(),
    fit: vi.fn(),
    getElementById: (id: string) => createElement(id),
    layout: vi.fn(() => ({ run: vi.fn() })),
    nodes: () => [],
    on: vi.fn(),
    resize: vi.fn(),
  }
  return { default: () => instance }
})

createI18n()

const KNOWLEDGE = {
  nodes: [
    { id: "source:owner", label: "主人会照顾我", kind: "source" as const, weight: 0.95 },
    { id: "knowledge:routine", label: "照顾是稳定的日常", kind: "knowledge" as const, weight: 0.87 },
    { id: "knowledge:patience", label: "等待能换来回应", kind: "knowledge" as const, weight: 0.7 },
    { id: "belief:trust", label: "可靠的人会持续回应", kind: "belief" as const, weight: 0.8 },
    { id: "belief:explore", label: "熟悉之后可以主动探索", kind: "belief" as const, weight: 0.62 },
  ],
  edges: [
    { source: "source:owner", target: "knowledge:routine", relationKey: "derived_from", displayLabel: "形成", weight: 0.9 },
    { source: "knowledge:routine", target: "belief:trust", relationKey: "supports", displayLabel: "支持", weight: 0.84 },
    { source: "knowledge:routine", target: "belief:explore", relationKey: "supports", displayLabel: "支持", weight: 0.68 },
    { source: "knowledge:patience", target: "belief:trust", relationKey: "revises", displayLabel: "修正", weight: 0.55 },
  ],
} as const

describe("ProfileKnowledgeBeliefs", () => {
  it("renders a two-sided graph without exposing source nodes or edge cards", () => {
    render(<ProfileKnowledgeBeliefs knowledge={KNOWLEDGE} status="ready" />)

    expect(screen.getByRole("img", { name: "知识与信念图" })).toBeInTheDocument()
    expect(screen.getByText("知识")).toBeInTheDocument()
    expect(screen.getByText("信念")).toBeInTheDocument()
    expect(screen.queryByText("主人会照顾我")).not.toBeInTheDocument()
    expect(screen.queryByRole("list", { name: "知识与信念路径" })).not.toBeInTheDocument()
  })

  it("uses the same focus path for an accessible node button", async () => {
    const user = userEvent.setup()
    render(<ProfileKnowledgeBeliefs knowledge={KNOWLEDGE} status="ready" />)

    const node = screen.getByRole("button", { name: "知识与信念节点：照顾是稳定的日常" })
    await user.click(node)

    expect(node).toHaveAttribute("aria-pressed", "true")
  })
})
