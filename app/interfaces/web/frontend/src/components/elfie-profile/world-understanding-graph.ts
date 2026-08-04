import type { Core, ElementDefinition, LayoutOptions, Position, StylesheetJson } from "cytoscape"

import type { WorldUnderstanding } from "./model"

export const WORLD_CENTER_NODE_ID = "world:center"

export type WorldUnderstandingGraph = {
  readonly elements: ElementDefinition[]
  readonly layout: LayoutOptions
  readonly style: StylesheetJson
}

const CENTER_DIAMETER = 84
const NODE_MIN_DIAMETER = 28
const NODE_MAX_DIAMETER = 72

const GRAPH_STYLE: StylesheetJson = [
  {
    selector: "node",
    style: {
      "background-color": "#fffdf8",
      "border-color": "#a45f3d",
      "border-width": 2,
      color: "#342a24",
      "font-family": "inherit",
      "font-size": "mapData(importance, 0, 1, 10, 17)",
      "font-weight": 700,
      height: "data(diameter)",
      label: "data(label)",
      "line-height": 1.15,
      shape: "ellipse",
      "text-halign": "center",
      "text-max-width": "88px",
      "text-valign": "center",
      "text-wrap": "wrap",
      width: "data(diameter)",
    },
  },
  {
    selector: "node.world-node-center",
    style: {
      "background-color": "#a45f3d",
      "border-color": "#a45f3d",
      "border-width": 3,
      color: "#fffdf8",
      "font-size": 20,
      "font-weight": 900,
      height: CENTER_DIAMETER,
      shape: "ellipse",
      width: CENTER_DIAMETER,
    },
  },
  {
    selector: "node.world-node-ring-self",
    style: { "border-color": "#a45f3d" },
  },
  {
    selector: "node.world-node-ring-family",
    style: { "border-color": "#b57a4e" },
  },
  {
    selector: "node.world-node-ring-nest",
    style: { "border-color": "#8f8b68" },
  },
  {
    selector: "node.world-node-ring-society",
    style: { "border-color": "#6f9278" },
  },
  {
    selector: "node.world-node-ring-outside",
    style: { "border-color": "#8a7890" },
  },
  {
    selector: ".is-dimmed",
    style: { opacity: 0.16 },
  },
  {
    selector: "node.is-related",
    style: { "border-width": 4, "font-weight": 900 },
  },
  {
    selector: "node.is-selected",
    style: { "border-color": "#342a24", "border-width": 5, "font-weight": 900 },
  },
]

export function buildWorldUnderstandingGraph(world: WorldUnderstanding): WorldUnderstandingGraph {
  const elements: ElementDefinition[] = [{
    classes: "world-node world-node-center",
    data: {
      diameter: CENTER_DIAMETER,
      id: WORLD_CENTER_NODE_ID,
      importance: 1,
      label: "我",
      layer: world.rings.length,
      ringKey: "center",
    },
    group: "nodes",
  }]

  world.rings.forEach((ring, ringIndex) => {
    ring.nodes.forEach((node) => {
      const importance = boundedScore(node.weight)
      elements.push({
        classes: `world-node world-node-ring-${ring.key}`,
        data: {
          diameter: worldNodeDiameter(importance),
          id: worldNodeElementId(node.id),
          importance,
          label: node.label,
          layer: world.rings.length - ringIndex - 1,
          nodeId: node.id,
          ringKey: ring.key,
        },
        group: "nodes",
      })
    })
  })

  return {
    elements,
    layout: worldUnderstandingLayout(),
    style: GRAPH_STYLE,
  }
}

export function worldNodeElementId(nodeId: string): string {
  return `world:node:${nodeId}`
}

export function worldUnderstandingLayout(center: Position = { x: 0, y: 0 }): LayoutOptions {
  return {
    animate: false,
    avoidOverlap: true,
    clockwise: true,
    concentric: (node) => layerValue(node.data("layer")),
    equidistant: false,
    fit: true,
    levelWidth: () => 0.5,
    minNodeSpacing: 4,
    name: "concentric",
    nodeDimensionsIncludeLabels: false,
    padding: 44,
    spacingFactor: 1,
    startAngle: -Math.PI / 2,
    transform: (node, position) => node.id() === WORLD_CENTER_NODE_ID
      ? position
      : rotateWorldPosition(position, worldRingRotation(layerValue(node.data("layer"))), center),
  }
}

export function applyWorldUnderstandingFocus(cy: Core, selectedId: string | null): void {
  cy.elements().removeClass("is-dimmed is-selected is-related")
  if (selectedId === null) return

  const selected = cy.getElementById(worldNodeElementId(selectedId))
  if (selected.empty()) return
  const selectedRing = selected.data("ringKey")

  cy.nodes().forEach((node) => {
    if (node.id() === WORLD_CENTER_NODE_ID || node.id() === selected.id()) return
    if (node.data("ringKey") === selectedRing) node.addClass("is-related")
    else node.addClass("is-dimmed")
  })
  selected.addClass("is-selected")
}

function worldNodeDiameter(importance: number): number {
  const visualImportance = Math.pow(boundedScore(importance), 1.4)
  return NODE_MIN_DIAMETER + visualImportance * (NODE_MAX_DIAMETER - NODE_MIN_DIAMETER)
}

function boundedScore(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0
}

function layerValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0
}

function rotateWorldPosition(position: Position, rotation: number, center: Position): Position {
  if (rotation === 0) return position

  const relativeX = position.x - center.x
  const relativeY = position.y - center.y
  const cosine = Math.cos(rotation)
  const sine = Math.sin(rotation)

  return {
    x: center.x + relativeX * cosine - relativeY * sine,
    y: center.y + relativeX * sine + relativeY * cosine,
  }
}

function worldRingRotation(layer: number): number {
  return layer * ((Math.PI * 2) / 5)
}
