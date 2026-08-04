import cytoscape from "cytoscape"
import { describe, expect, it } from "vitest"

import type { KnowledgeBeliefs } from "./model"
import {
  applyKnowledgeBeliefsFocus,
  applyKnowledgeBeliefsNodeDensity,
  buildKnowledgeBeliefsGraph,
  knowledgeBeliefsGraphLayout,
} from "./knowledge-beliefs-graph"

const KNOWLEDGE: KnowledgeBeliefs = {
  nodes: [
    { id: "source:owner", label: "主人会照顾我", kind: "source", weight: 0.95 },
    { id: "knowledge:routine", label: "照顾是稳定的日常", kind: "knowledge", weight: 0.87 },
    { id: "knowledge:patience", label: "等待能换来回应", kind: "knowledge", weight: 0.7 },
    { id: "belief:trust", label: "可靠的人会持续回应", kind: "belief", weight: 0.8 },
    { id: "belief:explore", label: "熟悉之后可以主动探索", kind: "belief", weight: 0.62 },
  ],
  edges: [
    { source: "source:owner", target: "knowledge:routine", relationKey: "derived_from", displayLabel: "形成", weight: 0.9 },
    { source: "knowledge:routine", target: "belief:trust", relationKey: "supports", displayLabel: "支持", weight: 0.84 },
    { source: "knowledge:routine", target: "belief:explore", relationKey: "supports", displayLabel: "支持", weight: 0.68 },
    { source: "belief:trust", target: "knowledge:patience", relationKey: "revises", displayLabel: "修正", weight: 0.55 },
    { source: "belief:trust", target: "belief:explore", relationKey: "supports", displayLabel: "支持", weight: 0.3 },
  ],
}

describe("buildKnowledgeBeliefsGraph", () => {
  it("keeps only knowledge and beliefs while preserving one-to-many and many-to-one edges", () => {
    const graph = buildKnowledgeBeliefsGraph(KNOWLEDGE)
    const nodes = graph.elements.filter((element) => element.group === "nodes")
    const edges = graph.elements.filter((element) => element.group === "edges")
    const pairs = edges.map((edge) => `${String(edge.data?.source)}>${String(edge.data?.target)}`)

    expect(graph.nodeIds).not.toContain("source:owner")
    expect(nodes).toHaveLength(4)
    expect(edges).toHaveLength(3)
    expect(pairs).toEqual([
      "knowledge:patience>belief:trust",
      "knowledge:routine>belief:explore",
      "knowledge:routine>belief:trust",
    ])
    expect(graph.layout).toMatchObject({ direction: "rightward", name: "breadthfirst" })
  })

  it("uses the same breadthfirst graph with a downward mobile direction", () => {
    const graph = buildKnowledgeBeliefsGraph(KNOWLEDGE)
    const mobileLayout = knowledgeBeliefsGraphLayout(
      KNOWLEDGE.nodes.filter((node) => node.kind !== "source"),
      "downward",
    )

    expect(graph.layout.name).toBe("breadthfirst")
    expect(mobileLayout).toMatchObject({ direction: "downward", name: "breadthfirst" })
  })

  it("uses compact label-sized bounds on mobile while preserving desktop bounds", () => {
    const graph = buildKnowledgeBeliefsGraph(KNOWLEDGE)
    const cy = cytoscape({ elements: graph.elements, headless: true, style: graph.style })
    const node = cy.getElementById("belief:trust")
    const desktopWidth = node.data("desktopNodeWidth")
    const desktopFontSize = node.data("desktopFontSize")

    applyKnowledgeBeliefsNodeDensity(cy, true)

    expect(node.data("nodeWidth")).toBeLessThan(desktopWidth)
    expect(node.data("nodeHeight")).toBeLessThan(node.data("desktopNodeHeight"))
    expect(node.data("fontSize")).toBeLessThan(desktopFontSize)
    expect(node.data("nodeWidth")).toBeGreaterThanOrEqual(100)

    applyKnowledgeBeliefsNodeDensity(cy, false)

    expect(node.data("nodeWidth")).toBe(desktopWidth)
    expect(node.data("fontSize")).toBe(desktopFontSize)
    cy.destroy()
  })

  it("keeps node labels large enough to read in both graph modes", () => {
    const graph = buildKnowledgeBeliefsGraph(KNOWLEDGE)
    const node = graph.elements.find((element) => element.data?.id === "belief:trust")

    expect(node?.data?.["desktopFontSize"]).toBeGreaterThan(34)
    expect(node?.data?.["compactFontSize"]).toBeGreaterThan(27)
    expect(graph.style.find((rule) => rule.selector === "node")).toMatchObject({
      style: {
        "text-justification": "center",
        "text-margin-y": -10,
        "text-metrics": "glyph",
      },
    })
  })
})

describe("applyKnowledgeBeliefsFocus", () => {
  it("dims unrelated content and reveals every direct connection", () => {
    const graph = buildKnowledgeBeliefsGraph(KNOWLEDGE)
    const cy = cytoscape({ elements: graph.elements, headless: true, style: graph.style })

    applyKnowledgeBeliefsFocus(cy, "knowledge:routine")

    expect(cy.getElementById("knowledge:routine").hasClass("is-selected")).toBe(true)
    expect(cy.getElementById("belief:trust").hasClass("is-related")).toBe(true)
    expect(cy.getElementById("belief:explore").hasClass("is-related")).toBe(true)
    expect(cy.getElementById("knowledge:patience").hasClass("is-dimmed")).toBe(true)
    expect(cy.getElementById("knowledge-belief:knowledge:routine:belief:trust:supports").hasClass("is-related")).toBe(true)

    applyKnowledgeBeliefsFocus(cy, null)

    expect(cy.getElementById("knowledge:routine").hasClass("is-selected")).toBe(false)
    expect(cy.getElementById("knowledge:patience").hasClass("is-dimmed")).toBe(false)
    cy.destroy()
  })
})
