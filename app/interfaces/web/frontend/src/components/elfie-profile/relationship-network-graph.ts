import type {
  Core,
  EdgeSingular,
  ElementDefinition,
  LayoutOptions,
  StylesheetJson,
} from "cytoscape"

import type { RelationshipWorld } from "./model"

export type RelationshipGraph = {
  readonly elements: ElementDefinition[]
  readonly layout: LayoutOptions
  readonly style: StylesheetJson
}

const NODE_DIAMETER = 120
const HEXAGON_HEIGHT_RATIO = Math.sqrt(3) / 2

const GRAPH_STYLE: StylesheetJson = [
  {
    selector: "node",
    style: {
      "background-color": "#fffdf8",
      "border-color": "#a45f3d",
      "border-width": 2,
      color: "#342a24",
      "font-family": "inherit",
      "font-size": "mapData(importance, 0, 1, 10, 16)",
      "font-weight": 700,
      height: "data(diameter)",
      "text-halign": "center",
      label: "data(label)",
      "line-height": 1.15,
      "padding-left": "8px",
      "padding-right": "8px",
      "text-max-width": "96px",
      "text-valign": "center",
      "text-wrap": "wrap",
      width: "data(diameter)",
    },
  },
  {
    selector: "node.node-self",
    style: {
      "background-color": "#a45f3d",
      color: "#fffdf8",
      "font-size": 20,
      "font-weight": 900,
      shape: "ellipse",
    },
  },
  {
    selector: "node.node-human",
    style: {
      "border-color": "#a45f3d",
      height: "data(hexagonHeight)",
      shape: "hexagon",
      width: "data(diameter)",
    },
  },
  {
    selector: "node.node-owner",
    style: {
      "background-color": "#f3dfcd",
      "border-width": 3,
    },
  },
  {
    selector: "node.node-elfie",
    style: {
      "border-color": "#5676b8",
      shape: "ellipse",
    },
  },
  {
    selector: "edge",
    style: {
      "curve-style": "bezier",
      "font-family": "inherit",
      "font-size": 10,
      "font-weight": 700,
      label: "data(label)",
      "line-color": "#b8a998",
      "line-style": "solid",
      "text-background-color": "#fff8ed",
      "text-background-opacity": 0.92,
      "text-background-padding": "3px",
      "text-margin-y": -4,
      "text-rotation": "autorotate",
      "text-wrap": "wrap",
      width: "mapData(closeness, 0, 1, 1.5, 8)",
    },
  },
  {
    selector: "edge.is-self-edge",
    style: { "line-color": "#a45f3d" },
  },
  {
    selector: ".is-dimmed",
    style: { opacity: 0.2 },
  },
  {
    selector: "node.is-neighbor",
    style: { "border-color": "#8c4e31", "border-width": 4 },
  },
  {
    selector: "edge.is-neighbor",
    style: { "line-color": "#8c4e31" },
  },
  {
    selector: "node.is-selected",
    style: { "border-color": "#342a24", "border-width": 5 },
  },
  {
    selector: "edge.is-path",
    style: { "line-color": "#a45f3d", "z-index": 4 },
  },
]

export function buildRelationshipGraph(world: RelationshipWorld): RelationshipGraph {
  const nodeIds = new Set(world.nodes.map((node) => node.id))
  const ownerNodeIds = relationshipOwnerNodeIds(world)
  const elements: ElementDefinition[] = world.nodes.map((node) => ({
    classes: [
      `node-${node.kind}`,
      ...(ownerNodeIds.has(node.id) ? ["node-owner"] : []),
    ].join(" "),
    data: {
      diameter: relationshipNodeDiameter(node.weight),
      hexagonHeight: relationshipHexagonHeight(node.weight),
      id: node.id,
      importance: boundedScore(node.weight),
      label: node.label,
    },
    group: "nodes",
  }))

  for (const edge of world.edges) {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target) || edge.source === edge.target) continue
    const element: ElementDefinition = {
      data: {
        id: relationshipEdgeId(edge.source, edge.target, edge.relationKey),
        label: edge.displayLabel || edge.relationKey,
        closeness: boundedScore(edge.weight),
        relationKey: edge.relationKey,
        source: edge.source,
        target: edge.target,
      },
      group: "edges",
    }
    if (edge.source === "self" || edge.target === "self") element.classes = "is-self-edge"
    elements.push(element)
  }

  return {
    elements,
    layout: relationshipGraphLayout(),
    style: GRAPH_STYLE,
  }
}

export function relationshipEdgeId(source: string, target: string, relationKey: string): string {
  return `relationship:${source}:${target}:${relationKey}`
}

export function relationshipGraphLayout(): LayoutOptions {
  return {
    animate: false,
    avoidOverlap: true,
    componentSpacing: 80,
    coolingFactor: 0.97,
    edgeElasticity: (edge) => 40 - boundedScore(edge.data("closeness")) * 18,
    fit: true,
    gravity: 0.6,
    idealEdgeLength: relationshipIdealEdgeLength,
    initialTemp: 800,
    minTemp: 1,
    name: "cose",
    nodeDimensionsIncludeLabels: true,
    nodeOverlap: 24,
    nodeRepulsion: (node) => 6000 + boundedScore(node.data("importance")) * 6000,
    numIter: 1000,
    padding: 36,
    randomize: true,
    spacingFactor: 1.05,
  }
}

export function relationshipIdealEdgeLength(edge: EdgeSingular): number {
  const sourceDiameter = boundedDiameter(edge.source().data("diameter"))
  const targetDiameter = boundedDiameter(edge.target().data("diameter"))
  const relationshipGap = 24 + (1 - boundedScore(edge.data("closeness"))) * 36
  return sourceDiameter / 2 + targetDiameter / 2 + relationshipGap
}

export function applyRelationshipFocus(cy: Core, selectedId: string | null): void {
  cy.elements().removeClass("is-dimmed is-selected is-neighbor is-path")
  const focusId = selectedId ?? "self"
  const focus = cy.getElementById(focusId)
  if (focus.empty()) return

  if (selectedId === null || selectedId === "self") return
  const self = cy.getElementById("self")
  const selected = cy.getElementById(selectedId)
  if (self.empty() || selected.empty()) return

  const path = cy.elements().dijkstra({
    directed: false,
    root: self,
    weight: (edge) => {
      const closeness = boundedScore(edge.data("closeness"))
      return closeness > 0 ? -Math.log(closeness) : Number.MAX_SAFE_INTEGER
    },
  }).pathTo(selected)
  cy.elements().addClass("is-dimmed")
  self.removeClass("is-dimmed")
  selected.removeClass("is-dimmed").addClass("is-selected")
  selected.neighborhood().removeClass("is-dimmed").addClass("is-neighbor")
  path.removeClass("is-dimmed").addClass("is-path")
}

function relationshipOwnerNodeIds(world: RelationshipWorld): ReadonlySet<string> {
  const ownerNodeIds = new Set<string>()
  for (const edge of world.edges) {
    if (edge.relationKey !== "owner") continue
    if (edge.source !== "self") ownerNodeIds.add(edge.source)
    if (edge.target !== "self") ownerNodeIds.add(edge.target)
  }
  return ownerNodeIds
}

function relationshipNodeDiameter(sizeScore: number): number {
  return boundedScore(sizeScore) * NODE_DIAMETER
}

function relationshipHexagonHeight(sizeScore: number): number {
  return relationshipNodeDiameter(sizeScore) * HEXAGON_HEIGHT_RATIO
}

function boundedScore(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0
}

function boundedDiameter(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, value) : 0
}
