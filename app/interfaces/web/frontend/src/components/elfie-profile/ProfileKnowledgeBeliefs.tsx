import cytoscape, { type Core, type EventObject } from "cytoscape"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import type { KnowledgeBeliefs } from "./model"
import {
  applyKnowledgeBeliefsFocus,
  applyKnowledgeBeliefsNodeDensity,
  buildKnowledgeBeliefsGraph,
  knowledgeBeliefsGraphLayout,
  type KnowledgeBeliefsGraph,
} from "./knowledge-beliefs-graph"

type ProfileKnowledgeBeliefsProps = {
  readonly knowledge: KnowledgeBeliefs
  readonly status: "ready" | "empty" | "unavailable"
}

type KnowledgeBeliefsGraphProps = {
  readonly graph: KnowledgeBeliefsGraph
  readonly knowledgeNodes: readonly KnowledgeBeliefs["nodes"][number][]
  readonly ariaLabel: string
  readonly nodeLabel: (name: string) => string
  readonly nodeListLabel: string
  readonly onSelect: (nodeId: string | null) => void
  readonly selectedId: string | null
}

export function ProfileKnowledgeBeliefs({ knowledge, status }: ProfileKnowledgeBeliefsProps) {
  const { t } = useTranslation("chat")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const knowledgeNodes = useMemo(
    () => knowledge.nodes.filter((node) => node.kind !== "source"),
    [knowledge.nodes],
  )
  const localizedKnowledge = useMemo(() => ({
    edges: knowledge.edges.map((edge) => ({
      ...edge,
      displayLabel: relationLabel(edge.relationKey, edge.displayLabel, t),
    })),
    nodes: knowledge.nodes,
  }), [knowledge.edges, knowledge.nodes, t])
  const graph = useMemo(() => buildKnowledgeBeliefsGraph(localizedKnowledge), [localizedKnowledge])
  const hasGraph = status === "ready" && graph.nodeIds.length > 0 && graph.edgeIds.length > 0
  const handleSelect = useCallback((nodeId: string | null) => setSelectedId(nodeId), [])

  useEffect(() => {
    if (selectedId !== null && !graph.nodeIds.includes(selectedId)) setSelectedId(null)
  }, [graph.nodeIds, selectedId])

  if (!hasGraph) {
    return <p className="profile-private-module__empty">{t("profile.private.knowledge.empty")}</p>
  }

  return (
    <div className="profile-private-knowledge">
      <div aria-label={t("profile.private.knowledge.legendLabel")} className="profile-private-knowledge__legend" role="list">
        <LegendItem kind="forms" label={t("profile.private.knowledge.relationKeys.derivedFrom")} />
        <LegendItem kind="supports" label={t("profile.private.knowledge.relationKeys.supports")} />
        <LegendItem kind="revises" label={t("profile.private.knowledge.relationKeys.revises")} />
        <LegendItem kind="conflicts" label={t("profile.private.knowledge.relationKeys.conflicts")} />
      </div>
      <div className="profile-private-knowledge__map-shell">
        <div aria-hidden="true" className="profile-private-knowledge__column-labels">
          <span className="profile-private-knowledge__column-label profile-private-knowledge__column-label--knowledge">
            {t("profile.private.knowledge.columns.knowledge")}
          </span>
          <span className="profile-private-knowledge__column-label profile-private-knowledge__column-label--belief">
            {t("profile.private.knowledge.columns.belief")}
          </span>
        </div>
        <KnowledgeBeliefsGraph
          ariaLabel={t("profile.private.knowledge.mapLabel")}
          graph={graph}
          knowledgeNodes={knowledgeNodes}
          nodeLabel={(name) => t("profile.private.knowledge.nodeLabel", { name })}
          nodeListLabel={t("profile.private.knowledge.nodeList")}
          onSelect={handleSelect}
          selectedId={selectedId}
        />
      </div>
    </div>
  )
}

function LegendItem({ kind, label }: { readonly kind: string; readonly label: string }) {
  return (
    <span className="profile-private-knowledge__legend-item" role="listitem">
      <span aria-hidden="true" className={`profile-private-knowledge__legend-line profile-private-knowledge__legend-line--${kind}`} />
      {label}
    </span>
  )
}

function KnowledgeBeliefsGraph({ ariaLabel, graph, knowledgeNodes, nodeLabel, nodeListLabel, onSelect, selectedId }: KnowledgeBeliefsGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const cyRef = useRef<Core | null>(null)
  const [layoutDirection, setLayoutDirection] = useState<"rightward" | "downward">("rightward")

  useEffect(() => {
    const container = containerRef.current
    if (container === null) return undefined
    const cy = cytoscape({
      autoungrabify: true,
      boxSelectionEnabled: false,
      container,
      elements: graph.elements,
      layout: { name: "preset" },
      maxZoom: 2.5,
      minZoom: 0.25,
      style: graph.style,
      wheelSensitivity: 0.3,
    })
    cyRef.current = cy
    let currentDirection: "rightward" | "downward" | null = null
    const fitGraph = () => {
      const isMobile = container.clientWidth <= 640
      cy.resize()
      if (cy.elements().length > 0) cy.fit(cy.elements(), isMobile ? 4 : 12)
    }
    const runLayout = () => {
      const isMobile = container.clientWidth <= 640
      const nextDirection = "rightward" as const
      applyKnowledgeBeliefsNodeDensity(cy, isMobile)
      if (nextDirection === currentDirection) {
        fitGraph()
        return
      }
      currentDirection = nextDirection
      setLayoutDirection(nextDirection)
      cy.layout({
        ...knowledgeBeliefsGraphLayout(knowledgeNodes, nextDirection, true, isMobile ? 3 : 1.6),
        fit: false,
        padding: isMobile ? 8 : 20,
        spacingFactor: isMobile ? 0.56 : 0.82,
      }).run()
    }
    const handleNodeTap = (event: EventObject) => onSelect(event.target.id())
    const handleCanvasTap = (event: EventObject) => {
      if (event.target === cy) onSelect(null)
    }
    cy.on("layoutstop", fitGraph)
    cy.on("tap", "node", handleNodeTap)
    cy.on("tap", handleCanvasTap)
    runLayout()
    const observer = new ResizeObserver(runLayout)
    observer.observe(container)
    return () => {
      observer.disconnect()
      cy.destroy()
      cyRef.current = null
    }
  }, [graph, knowledgeNodes, onSelect])

  useEffect(() => {
    if (cyRef.current !== null) applyKnowledgeBeliefsFocus(cyRef.current, selectedId)
  }, [selectedId])

  return (
    <>
      <div aria-label={ariaLabel} className={`profile-private-knowledge__graph profile-private-knowledge__graph--${layoutDirection}`} ref={containerRef} role="img" />
      <div aria-label={nodeListLabel} className="profile-private-knowledge__a11y">
        {knowledgeNodes.map((node) => (
          <button
            aria-label={nodeLabel(node.label)}
            aria-pressed={selectedId === node.id}
            key={node.id}
            onClick={() => onSelect(node.id)}
            type="button"
          >
            {node.label}
          </button>
        ))}
      </div>
    </>
  )
}

function relationLabel(
  relationKey: string,
  displayLabel: string,
  t: ReturnType<typeof useTranslation<"chat">>["t"],
): string {
  switch (relationKey) {
    case "derived_from":
      return t("profile.private.knowledge.relationKeys.derivedFrom")
    case "supports":
      return t("profile.private.knowledge.relationKeys.supports")
    case "conflicts":
      return t("profile.private.knowledge.relationKeys.conflicts")
    case "revises":
      return t("profile.private.knowledge.relationKeys.revises")
    default:
      return displayLabel || t("profile.private.knowledge.relationFallback")
  }
}
