import cytoscape, { type Core, type EventObject } from "cytoscape"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import type { RelationshipFilter, RelationshipWorld } from "./model"
import { applyRelationshipFocus, buildRelationshipGraph } from "./relationship-network-graph"

type ProfileRelationshipWorldProps = {
  readonly status: "ready" | "empty" | "unavailable"
  readonly world: RelationshipWorld
}

type RelationshipNetworkGraphProps = {
  readonly ariaLabel: string
  readonly onSelect: (nodeId: string | null) => void
  readonly selectedId: string | null
  readonly world: RelationshipWorld
}

const FILTERS: readonly RelationshipFilter[] = ["all", "human", "elfie"]
const RELATIONSHIP_NODE_LIMIT = 50

export function ProfileRelationshipWorld({ status, world }: ProfileRelationshipWorldProps) {
  const { t } = useTranslation("chat")
  const [filter, setFilter] = useState<RelationshipFilter>("all")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const visible = useMemo(
    () => filterRelationshipWorld(world, filter, RELATIONSHIP_NODE_LIMIT),
    [filter, world],
  )
  const graphWorld = useMemo(() => ({
    edges: visible.edges.map((edge) => ({
      ...edge,
      displayLabel: relationLabel(edge.relationKey, edge.displayLabel, t),
    })),
    nodes: visible.nodes,
  }), [t, visible])
  const handleSelect = useCallback((nodeId: string | null) => setSelectedId(nodeId), [])

  useEffect(() => {
    if (selectedId !== null && !visible.nodes.some((node) => node.id === selectedId)) setSelectedId(null)
  }, [selectedId, visible.nodes])

  const handleFilterChange = (candidate: RelationshipFilter) => {
    setFilter(candidate)
    setSelectedId(null)
  }

  return (
    <div className="profile-private-relationships">
      <div className="profile-private-relationships__controls">
        <div className="profile-private-relationships__filters" role="group" aria-label={t("profile.private.relationships.filterLabel")}>
          {FILTERS.map((candidate) => (
            <button
              aria-pressed={filter === candidate}
              className={filter === candidate ? "profile-private-relationships__filter profile-private-relationships__filter--active" : "profile-private-relationships__filter"}
              key={candidate}
              onClick={() => handleFilterChange(candidate)}
              type="button"
            >
              {t(`profile.private.relationships.filters.${candidate}`)}
            </button>
          ))}
        </div>
      </div>
      {status !== "ready" || visible.nodes.length === 0 ? (
        <p className="profile-private-module__empty">{t("profile.private.relationships.empty")}</p>
      ) : (
        <>
          <RelationshipNetworkGraph ariaLabel={t("profile.private.relationships.mapLabel")} onSelect={handleSelect} selectedId={selectedId} world={graphWorld} />
          <div aria-label={t("profile.private.relationships.nodeList")} className="profile-private-relationships__a11y">
            {visible.nodes.map((node) => (
              <button
                aria-label={t("profile.private.relationships.nodeLabel", { name: node.label })}
                aria-pressed={selectedId === node.id}
                className="profile-private-relationships__node-button"
                key={node.id}
                onClick={() => handleSelect(node.id === "self" ? null : node.id)}
                type="button"
              >
                {node.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function RelationshipNetworkGraph({ ariaLabel, onSelect, selectedId, world }: RelationshipNetworkGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const cyRef = useRef<Core | null>(null)
  const graph = useMemo(() => buildRelationshipGraph(world), [world])

  useEffect(() => {
    const container = containerRef.current
    if (container === null) return undefined
    const cy = cytoscape({
      autoungrabify: true,
      boxSelectionEnabled: false,
      container,
      elements: graph.elements,
      layout: graph.layout,
      maxZoom: 2.5,
      minZoom: 0.25,
      style: graph.style,
      wheelSensitivity: 0.3,
    })
    cyRef.current = cy
    cy.getElementById("self").lock()
    const fitGraph = () => {
      cy.resize()
      if (typeof cy.fit === "function") cy.fit(cy.elements(), 36)
    }
    cy.on("layoutstop", fitGraph)
    fitGraph()

    const handleNodeTap = (event: EventObject) => {
      const nodeId = event.target.id()
      onSelect(nodeId === "self" ? null : nodeId)
    }
    const handleCanvasTap = (event: EventObject) => {
      if (event.target === cy) onSelect(null)
    }
    cy.on("tap", "node", handleNodeTap)
    cy.on("tap", handleCanvasTap)

    const observer = new ResizeObserver(fitGraph)
    observer.observe(container)
    return () => {
      observer.disconnect()
      cy.destroy()
      cyRef.current = null
    }
  }, [graph, onSelect])

  useEffect(() => {
    if (cyRef.current === null) return
    applyRelationshipFocus(cyRef.current, selectedId)
  }, [selectedId])

  return <div aria-label={ariaLabel} className="profile-private-relationships__map" ref={containerRef} role="img" />
}

export function filterRelationshipWorld(
  world: RelationshipWorld,
  filter: RelationshipFilter,
  limit = RELATIONSHIP_NODE_LIMIT,
): RelationshipWorld {
  const self = world.nodes.find((node) => node.kind === "self")
  const candidates = world.nodes.filter((node) => node.kind !== "self" && (filter === "all" || node.kind === filter))
  const nodes = (self === undefined ? candidates : [self, ...candidates]).slice(0, limit)
  const visibleIds = new Set(nodes.map((node) => node.id))
  return {
    edges: world.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)),
    nodes,
  }
}

function relationLabel(
  relationKey: string,
  displayLabel: string,
  t: ReturnType<typeof useTranslation<"chat">>["t"],
): string {
  switch (relationKey) {
    case "owner":
      return t("profile.private.relationships.relationKeys.owner")
    case "family":
      return t("profile.private.relationships.relationKeys.family")
    case "friend":
      return t("profile.private.relationships.relationKeys.friend")
    case "acquaintance":
      return t("profile.private.relationships.relationKeys.acquaintance")
    case "relationship":
      return t("profile.private.relationships.relationKeys.relationship")
    case "same_owner":
      return t("profile.private.relationships.relationKeys.sameOwner")
    case "friend_elfie":
      return t("profile.private.relationships.relationKeys.friendElfie")
    case "acquaintance_elfie":
      return t("profile.private.relationships.relationKeys.acquaintanceElfie")
    case "neighbor":
      return t("profile.private.relationships.relationKeys.neighbor")
    default:
      return displayLabel || t("profile.private.relationships.relationFallback")
  }
}
