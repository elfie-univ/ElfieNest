import cytoscape from "cytoscape"
import { describe, expect, it } from "vitest"

import type { WorldUnderstanding } from "./model"
import {
  applyWorldUnderstandingFocus,
  buildWorldUnderstandingGraph,
  worldNodeElementId,
  worldUnderstandingLayout,
  WORLD_CENTER_NODE_ID,
} from "./world-understanding-graph"

const WORLD: WorldUnderstanding = {
  summary: "大多数时候世界是安全的。",
  rings: [
    {
      key: "self",
      nodes: [
        { id: "self:quiet", label: "先确认再靠近", kind: "belief", weight: 0.92 },
        { id: "self:rest", label: "安静下来", kind: "belief", weight: 0.7 },
      ],
    },
    {
      key: "family",
      nodes: [{ id: "family:owner", label: "主人的回应", kind: "relationship", weight: 0.84 }],
    },
    {
      key: "nest",
      nodes: [{ id: "nest:quiet", label: "安静的角落", kind: "place", weight: 0.68 }],
    },
    {
      key: "society",
      nodes: [{ id: "society:friend", label: "朋友可以慢慢认识", kind: "relationship", weight: 0.48 }],
    },
    {
      key: "outside",
      nodes: [{ id: "outside:unknown", label: "陌生声音先观察", kind: "event", weight: 0.2 }],
    },
  ],
}

describe("buildWorldUnderstandingGraph", () => {
  it("maps the five world layers to concentric levels and keeps size proportional to weight", () => {
    const graph = buildWorldUnderstandingGraph(WORLD)
    const nodes = graph.elements.filter((element) => element.group === "nodes")
    const center = nodes.find((element) => element.data.id === WORLD_CENTER_NODE_ID)
    const inner = nodes.find((element) => element.data.id === worldNodeElementId("self:quiet"))
    const outer = nodes.find((element) => element.data.id === worldNodeElementId("outside:unknown"))

    expect(nodes).toHaveLength(7)
    expect(center).toMatchObject({
      classes: "world-node world-node-center",
      data: { diameter: 84, layer: 5, label: "我" },
    })
    expect(inner).toMatchObject({ data: { layer: 4, ringKey: "self" } })
    expect(inner?.data["diameter"]).toBeGreaterThan(60)
    expect(outer).toMatchObject({ data: { layer: 0, ringKey: "outside" } })
    expect(outer?.data["diameter"]).toBeLessThan(36)
    expect(graph.layout.name).toBe("concentric")
    expect(graph.style.find((entry) => entry.selector === "node")).toMatchObject({
      style: { height: "data(diameter)", shape: "ellipse", width: "data(diameter)" },
    })
  })

  it("staggers concentric layers instead of aligning them on one radial axis", () => {
    const graph = buildWorldUnderstandingGraph(WORLD)
    const cy = cytoscape({ elements: graph.elements, headless: true, style: graph.style })
    cy.layout({
      ...worldUnderstandingLayout({ x: 300, y: 300 }),
      boundingBox: { h: 600, w: 600, x1: 0, y1: 0 },
      fit: false,
    }).run()

    const center = cy.getElementById(WORLD_CENTER_NODE_ID).position()
    const inner = cy.getElementById(worldNodeElementId("society:friend")).position()
    const outer = cy.getElementById(worldNodeElementId("outside:unknown")).position()
    const angleDifference = Math.atan2(outer.y - center.y, outer.x - center.x)
      - Math.atan2(inner.y - center.y, inner.x - center.x)

    expect(center.x).toBeCloseTo(300, 5)
    expect(center.y).toBeCloseTo(300, 5)
    expect(Math.abs(Math.sin(angleDifference))).toBeGreaterThan(0.8)
    cy.destroy()
  })
})

describe("applyWorldUnderstandingFocus", () => {
  it("highlights the selected node and its concentric context without changing node sizes", () => {
    const graph = buildWorldUnderstandingGraph(WORLD)
    const cy = cytoscape({ elements: graph.elements, headless: true, style: graph.style })

    applyWorldUnderstandingFocus(cy, "outside:unknown")

    expect(cy.getElementById(worldNodeElementId("outside:unknown")).hasClass("is-selected")).toBe(true)
    expect(cy.getElementById(worldNodeElementId("outside:unknown")).data("diameter")).toBeLessThan(36)
    expect(cy.getElementById(WORLD_CENTER_NODE_ID).hasClass("is-dimmed")).toBe(false)
    expect(cy.getElementById(worldNodeElementId("society:friend")).hasClass("is-dimmed")).toBe(true)

    applyWorldUnderstandingFocus(cy, null)

    expect(cy.getElementById(worldNodeElementId("outside:unknown")).hasClass("is-selected")).toBe(false)
    expect(cy.getElementById(worldNodeElementId("society:friend")).hasClass("is-dimmed")).toBe(false)
    cy.destroy()
  })
})
