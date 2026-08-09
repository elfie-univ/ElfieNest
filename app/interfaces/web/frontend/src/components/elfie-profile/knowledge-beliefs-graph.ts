import type { BreadthFirstLayoutOptions, Core, ElementDefinition, StylesheetJson } from "cytoscape"

import type { KnowledgeBeliefs } from "./model"

export const KNOWLEDGE_BELIEFS_DIRECTIONS = ["rightward", "downward"] as const
export type KnowledgeBeliefsDirection = (typeof KNOWLEDGE_BELIEFS_DIRECTIONS)[number]

export type KnowledgeBeliefsGraph = {
  readonly elements: ElementDefinition[]
  readonly edgeIds: readonly string[]
  readonly layout: BreadthFirstLayoutOptions
  readonly nodeIds: readonly string[]
  readonly style: StylesheetJson
}

const KNOWLEDGE_NODE_MIN_HEIGHT = 48
const KNOWLEDGE_NODE_MAX_HEIGHT = 68
const KNOWLEDGE_NODE_MIN_WIDTH = 150
const KNOWLEDGE_NODE_MAX_WIDTH = 204
const BELIEF_NODE_MIN_HEIGHT = 54
const BELIEF_NODE_MAX_HEIGHT = 80
const BELIEF_NODE_MIN_WIDTH = 174
const BELIEF_NODE_MAX_WIDTH = 238
const NODE_TEXT_MARGIN_Y = -10

const GRAPH_STYLE: StylesheetJson = [
  {
    selector: "node",
    style: {
      "background-color": "#fffdf8",
      "border-color": "#9f6f16",
      "border-width": 2,
      color: "#342a24",
      "font-family": "inherit",
      "font-size": "data(fontSize)",
      "font-weight": 700,
      height: "data(nodeHeight)",
      label: "data(label)",
      "line-height": 1.15,
      "text-halign": "center",
      "text-justification": "center",
      "text-metrics": "glyph",
      "text-max-width": "data(nodeWidth)",
      "text-margin-y": NODE_TEXT_MARGIN_Y,
      "text-valign": "center",
      "text-wrap": "wrap",
      width: "data(nodeWidth)",
    },
  },
  {
    selector: "node.node-knowledge",
    style: {
      "background-color": "#fff3df",
      "border-color": "#9f6f16",
      shape: "roundrectangle",
    },
  },
  {
    selector: "node.node-belief",
    style: {
      "background-color": "#e4f1eb",
      "border-color": "#1f7a60",
      "border-width": 3,
      "font-weight": 900,
      shape: "ellipse",
    },
  },
  {
    selector: "edge",
    style: {
      "curve-style": "bezier",
      "line-color": "#a99c8d",
      "target-arrow-color": "#a99c8d",
      "target-arrow-shape": "triangle",
      "text-background-color": "#fffdf8",
      "text-background-opacity": 0.94,
      "text-background-padding": "3px",
      "text-halign": "center",
      "text-margin-y": -4,
      "text-rotation": "autorotate",
      "text-wrap": "wrap",
      "width": "mapData(weight, 0, 1, 1.5, 5)",
    },
  },
  {
    selector: "edge.relation-forms",
    style: { "line-color": "#9f6f16", "target-arrow-color": "#9f6f16" },
  },
  {
    selector: "edge.relation-supports",
    style: { "line-color": "#1f7a60", "line-style": "dashed", "target-arrow-color": "#1f7a60" },
  },
  {
    selector: "edge.relation-revises",
    style: { "line-color": "#5676b8", "line-style": "dotted", "target-arrow-color": "#5676b8" },
  },
  {
    selector: "edge.relation-conflicts",
    style: { "line-color": "#a6526f", "line-style": "dashed", "target-arrow-color": "#a6526f" },
  },
  {
    selector: "edge.is-related",
    style: {
      label: "data(label)",
      "line-style": "solid",
      "text-background-opacity": 1,
      "font-size": 11,
    },
  },
  {
    selector: ".is-dimmed",
    style: { opacity: 0.16 },
  },
  {
    selector: "node.is-related",
    style: { "border-width": 4 },
  },
  {
    selector: "node.is-selected",
    style: { "border-color": "#342a24", "border-width": 5 },
  },
]

export function buildKnowledgeBeliefsGraph(knowledge: KnowledgeBeliefs): KnowledgeBeliefsGraph {
  const visibleNodes = knowledge.nodes
    .filter((node) => node.kind !== "source")
    .sort(compareKnowledgeNodes)
  const nodesById = new Map(visibleNodes.map((node) => [node.id, node]))
  const nodeIds = visibleNodes.map((node) => node.id)
  const elements: ElementDefinition[] = visibleNodes.map((node) => ({
    classes: `node-${node.kind}`,
    data: {
      id: node.id,
      importance: boundedScore(node.weight),
      kind: node.kind,
      label: node.label,
      ...knowledgeBeliefNodeSize(node.kind, node.weight),
    },
    group: "nodes",
  }))
  const edgeElements = knowledge.edges
    .map((edge) => knowledgeBeliefEdgeElement(edge, nodesById))
    .filter((edge): edge is ElementDefinition => edge !== null)
    .sort(compareGraphElements)
  const edgeIds = edgeElements.map((edge) => String(edge.data?.id ?? ""))

  return {
    elements: [...elements, ...edgeElements],
    edgeIds,
    layout: knowledgeBeliefsGraphLayout(visibleNodes, "rightward"),
    nodeIds,
    style: GRAPH_STYLE,
  }
}

export function knowledgeBeliefsGraphLayout(
  nodes: readonly KnowledgeBeliefs["nodes"][number][],
  direction: KnowledgeBeliefsDirection,
  nodeDimensionsIncludeLabels = true,
  horizontalScale = 1,
): BreadthFirstLayoutOptions {
  const rootIds = nodes.filter((node) => node.kind === "knowledge").map((node) => node.id)
  return {
    animate: false,
    avoidOverlap: true,
    directed: true,
    fit: false,
    maximal: true,
    name: "breadthfirst",
    nodeDimensionsIncludeLabels,
    padding: 20,
    roots: rootIds,
    spacingFactor: 0.82,
    direction,
    transform: (node, position) => {
      if (horizontalScale === 1) return position
      const extent = node.cy().extent()
      const centerX = extent.x1 + extent.w / 2
      return { x: centerX + (position.x - centerX) * horizontalScale, y: position.y }
    },
  }
}

export function applyKnowledgeBeliefsFocus(cy: Core, selectedId: string | null): void {
  cy.elements().removeClass("is-dimmed is-selected is-related")
  if (selectedId === null) return

  const selected = cy.getElementById(selectedId)
  if (selected.empty()) return

  cy.elements().addClass("is-dimmed")
  selected.removeClass("is-dimmed").addClass("is-selected")
  selected.neighborhood().removeClass("is-dimmed").addClass("is-related")
}

export function applyKnowledgeBeliefsNodeDensity(cy: Core, compact: boolean): void {
  cy.nodes().forEach((node) => {
    const widthKey = compact ? "compactNodeWidth" : "desktopNodeWidth"
    const heightKey = compact ? "compactNodeHeight" : "desktopNodeHeight"
    const fontSizeKey = compact ? "compactFontSize" : "desktopFontSize"
    const fontSize = Number(node.data(fontSizeKey))
    const nodeHeight = Number(node.data(heightKey))
    const nodeWidth = Number(node.data(widthKey))
    node.data({
      fontSize,
      nodeHeight,
      nodeWidth,
    })
    node.style({
      "font-size": fontSize,
      height: nodeHeight,
      "text-max-width": nodeWidth,
      width: nodeWidth,
    })
  })
}

function knowledgeBeliefEdgeElement(
  edge: KnowledgeBeliefs["edges"][number],
  nodesById: ReadonlyMap<string, KnowledgeBeliefs["nodes"][number]>,
): ElementDefinition | null {
  const source = nodesById.get(edge.source)
  const target = nodesById.get(edge.target)
  if (source === undefined || target === undefined) return null

  const isKnowledgeToBelief = source.kind === "knowledge" && target.kind === "belief"
  const isBeliefToKnowledge = source.kind === "belief" && target.kind === "knowledge"
  if (!isKnowledgeToBelief && !isBeliefToKnowledge) return null

  const sourceId = isKnowledgeToBelief ? source.id : target.id
  const targetId = isKnowledgeToBelief ? target.id : source.id
  const id = knowledgeBeliefEdgeId(sourceId, targetId, edge.relationKey)
  return {
    classes: relationClass(edge.relationKey),
    data: {
      id,
      label: edge.displayLabel || edge.relationKey,
      relationKey: edge.relationKey,
      source: sourceId,
      target: targetId,
      weight: boundedScore(edge.weight),
    },
    group: "edges",
  }
}

export function knowledgeBeliefEdgeId(source: string, target: string, relationKey: string): string {
  return `knowledge-belief:${source}:${target}:${relationKey}`
}

function compareGraphElements(left: ElementDefinition, right: ElementDefinition): number {
  return compareStableText(String(left.data?.id ?? ""), String(right.data?.id ?? ""))
}

function compareKnowledgeNodes(
  left: KnowledgeBeliefs["nodes"][number],
  right: KnowledgeBeliefs["nodes"][number],
): number {
  return boundedScore(right.weight) - boundedScore(left.weight)
    || compareStableText(left.kind, right.kind)
    || compareStableText(left.label, right.label)
    || compareStableText(left.id, right.id)
}

function compareStableText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0
}

function knowledgeBeliefNodeSize(
  kind: KnowledgeBeliefs["nodes"][number]["kind"],
  weight: number,
): {
  readonly compactFontSize: number
  readonly compactNodeHeight: number
  readonly compactNodeWidth: number
  readonly desktopFontSize: number
  readonly desktopNodeHeight: number
  readonly desktopNodeWidth: number
  readonly fontSize: number
  readonly nodeHeight: number
  readonly nodeWidth: number
} {
  const score = Math.pow(boundedScore(weight), 1.2)
  const [minHeight, maxHeight, minWidth, maxWidth] = kind === "belief"
    ? [BELIEF_NODE_MIN_HEIGHT, BELIEF_NODE_MAX_HEIGHT, BELIEF_NODE_MIN_WIDTH, BELIEF_NODE_MAX_WIDTH]
    : [KNOWLEDGE_NODE_MIN_HEIGHT, KNOWLEDGE_NODE_MAX_HEIGHT, KNOWLEDGE_NODE_MIN_WIDTH, KNOWLEDGE_NODE_MAX_WIDTH]
  const [compactMinHeight, compactMaxHeight, compactMinWidth, compactMaxWidth] = kind === "belief"
    ? [38, 58, 116, 160]
    : [34, 50, 104, 142]
  const desktopFontSize = (18 + score * 8) * 2.2
  const compactFontSize = (15 + score * 5) * 2.2
  return {
    compactFontSize,
    compactNodeHeight: compactMinHeight + score * (compactMaxHeight - compactMinHeight),
    compactNodeWidth: compactMinWidth + score * (compactMaxWidth - compactMinWidth),
    desktopFontSize,
    desktopNodeHeight: minHeight + score * (maxHeight - minHeight),
    desktopNodeWidth: minWidth + score * (maxWidth - minWidth),
    fontSize: desktopFontSize,
    nodeHeight: minHeight + score * (maxHeight - minHeight),
    nodeWidth: minWidth + score * (maxWidth - minWidth),
  }
}

function relationClass(relationKey: string): string {
  switch (relationKey) {
    case "derived_from":
      return "relation-forms"
    case "supports":
      return "relation-supports"
    case "revises":
      return "relation-revises"
    case "conflicts":
      return "relation-conflicts"
    default:
      return "relation-custom"
  }
}

function boundedScore(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0
}
