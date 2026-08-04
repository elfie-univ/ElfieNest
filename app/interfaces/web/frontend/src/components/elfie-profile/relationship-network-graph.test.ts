import cytoscape from "cytoscape"
import { describe, expect, it } from "vitest"

import type { RelationshipWorld } from "./model"
import {
  applyRelationshipFocus,
  buildRelationshipGraph,
  relationshipIdealEdgeLength,
} from "./relationship-network-graph"

const WORLD: RelationshipWorld = {
  nodes: [
    { id: "self", label: "Happy", kind: "self", weight: 1 },
    { id: "owner", label: "主人", kind: "human", weight: 0.95 },
    { id: "star", label: "星星", kind: "elfie", weight: 0.62 },
  ],
  edges: [
    { source: "self", target: "owner", relationKey: "owner", displayLabel: "主人", weight: 0.35 },
    { source: "owner", target: "star", relationKey: "friend", displayLabel: "朋友", weight: 0.8 },
  ],
}

describe("buildRelationshipGraph", () => {
  it("uses one proportional diameter scale without giving the owner a size override", () => {
    const graph = buildRelationshipGraph(WORLD)
    const self = graph.elements.find((element) => element.group === "nodes" && element.data.id === "self")
    const owner = graph.elements.find((element) => element.group === "nodes" && element.data.id === "owner")
    const star = graph.elements.find((element) => element.group === "nodes" && element.data.id === "star")
    const ownerToStar = graph.elements.find((element) => element.group === "edges" && element.data.id === "relationship:owner:star:friend")

    expect(self).toMatchObject({ classes: "node-self", data: { diameter: 120, importance: 1 } })
    expect(owner).toMatchObject({
      classes: "node-human node-owner",
      data: { diameter: 114, hexagonHeight: (114 * Math.sqrt(3)) / 2, importance: 0.95 },
    })
    expect(star).toMatchObject({ classes: "node-elfie", data: { diameter: 74.4, importance: 0.62 } })
    expect(ownerToStar).toMatchObject({ data: { closeness: 0.8, label: "朋友", source: "owner", target: "star" } })
    expect(self?.position).toBeUndefined()
    expect(graph.layout.name).toBe("cose")
    if ("idealEdgeLength" in graph.layout && "nodeRepulsion" in graph.layout) {
      expect(graph.layout.idealEdgeLength).toEqual(expect.any(Function))
      expect(graph.layout.nodeRepulsion).toEqual(expect.any(Function))
    }
  })

  it("uses different shapes for Elfies and people", () => {
    const graph = buildRelationshipGraph(WORLD)
    const styleFor = (selector: string) => {
      const entry = graph.style.find((candidate) => candidate.selector === selector)
      return entry !== undefined && "style" in entry ? entry.style : undefined
    }
    const selfStyle = styleFor("node.node-self")
    const humanStyle = styleFor("node.node-human")
    const elfieStyle = styleFor("node.node-elfie")

    expect(selfStyle).toMatchObject({ shape: "ellipse" })
    expect(humanStyle).toMatchObject({ height: "data(hexagonHeight)", shape: "hexagon", width: "data(diameter)" })
    expect(elfieStyle).toMatchObject({ shape: "ellipse" })
  })

  it("keeps node importance sizes independent from edge closeness when focus changes", () => {
    const graph = buildRelationshipGraph(WORLD)
    const cy = cytoscape({ elements: graph.elements, headless: true, style: graph.style })

    applyRelationshipFocus(cy, null)
    expect(cy.getElementById("self").data("diameter")).toBe(120)
    expect(cy.getElementById("owner").data("diameter")).toBe(114)
    expect(cy.getElementById("star").data("diameter")).toBe(74.4)

    applyRelationshipFocus(cy, "owner")
    expect(cy.getElementById("self").data("diameter")).toBe(120)
    expect(cy.getElementById("owner").data("diameter")).toBe(114)
    expect(cy.getElementById("star").data("diameter")).toBe(74.4)

    cy.destroy()
  })

  it("keeps connected nodes farther apart than their combined radii", () => {
    const graph = buildRelationshipGraph(WORLD)
    const cy = cytoscape({ elements: graph.elements, headless: true, style: graph.style })
    const ownerEdge = cy.getElementById("relationship:self:owner:owner")

    expect(relationshipIdealEdgeLength(ownerEdge)).toBeGreaterThan(117)

    cy.destroy()
  })
})
