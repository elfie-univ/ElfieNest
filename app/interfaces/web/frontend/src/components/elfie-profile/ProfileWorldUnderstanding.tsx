import cytoscape, { type Core, type EventObject } from "cytoscape"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import type { WorldUnderstanding } from "./model"
import {
  applyWorldUnderstandingFocus,
  buildWorldUnderstandingGraph,
  WORLD_CENTER_NODE_ID,
  worldUnderstandingLayout,
} from "./world-understanding-graph"

type ProfileWorldUnderstandingProps = {
  readonly status: "ready" | "empty" | "unavailable"
  readonly world: WorldUnderstanding
}

const WORLD_VIEWPORT_PADDING = 42

export function ProfileWorldUnderstanding({ status, world }: ProfileWorldUnderstandingProps) {
  const { t } = useTranslation("chat")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const hasNodes = world.rings.some((ring) => ring.nodes.length > 0)
  const graph = useMemo(() => buildWorldUnderstandingGraph(world, t("profile.private.world.center")), [t, world])
  const handleSelect = useCallback((nodeId: string | null) => setSelectedId(nodeId), [])

  useEffect(() => {
    if (selectedId !== null && !world.rings.some((ring) => ring.nodes.some((node) => node.id === selectedId))) {
      setSelectedId(null)
    }
  }, [selectedId, world])

  if (status !== "ready" || !hasNodes) {
    return <p className="profile-private-module__empty">{t("profile.private.world.empty")}</p>
  }

  return (
    <div className="profile-private-world">
      {world.summary.trim() ? <p className="profile-private-world__summary">{world.summary}</p> : null}
      <div className="profile-private-world__map">
        <div aria-hidden="true" className="profile-private-world__guides">
          {world.rings.map((ring) => (
            <div className={`profile-private-world__ring-guide profile-private-world__ring-guide--${ring.key}`} key={ring.key}>
              <span className="profile-private-world__ring-label">{ringLabel(ring.key, t)}</span>
            </div>
          ))}
        </div>
        <WorldUnderstandingGraph ariaLabel={t("profile.private.world.mapLabel")} graph={graph} onSelect={handleSelect} selectedId={selectedId} />
      </div>
      <div aria-label={t("profile.private.world.nodeList")} className="profile-private-world__a11y">
        <button aria-label={t("profile.private.world.nodeLabel", { name: t("profile.private.world.center") })} aria-pressed={selectedId === null} onClick={() => handleSelect(null)} type="button">
          {t("profile.private.world.center")}
        </button>
        {world.rings.map((ring) => ring.nodes.map((node) => (
          <button aria-label={t("profile.private.world.nodeLabel", { name: node.label })} aria-pressed={selectedId === node.id} key={node.id} onClick={() => handleSelect(node.id)} type="button">
            {node.label}
          </button>
        )))}
      </div>
    </div>
  )
}

type WorldUnderstandingGraphProps = {
  readonly ariaLabel: string
  readonly graph: ReturnType<typeof buildWorldUnderstandingGraph>
  readonly onSelect: (nodeId: string | null) => void
  readonly selectedId: string | null
}

function WorldUnderstandingGraph({ ariaLabel, graph, onSelect, selectedId }: WorldUnderstandingGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const cyRef = useRef<Core | null>(null)

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
    const fitGraph = () => {
      cy.resize()
      const centerNode = cy.getElementById(WORLD_CENTER_NODE_ID)
      if (centerNode.empty()) {
        cy.fit(cy.elements(), WORLD_VIEWPORT_PADDING)
        return
      }

      const bounds = cy.nodes().boundingBox({ includeLabels: false })
      const centerPosition = centerNode.position()
      const horizontalRadius = Math.max(centerPosition.x - bounds.x1, bounds.x2 - centerPosition.x, 1)
      const verticalRadius = Math.max(centerPosition.y - bounds.y1, bounds.y2 - centerPosition.y, 1)
      const usableWidth = Math.max(container.clientWidth - WORLD_VIEWPORT_PADDING * 2, 1)
      const usableHeight = Math.max(container.clientHeight - WORLD_VIEWPORT_PADDING * 2, 1)
      const fitZoom = Math.min(usableWidth / (horizontalRadius * 2), usableHeight / (verticalRadius * 2))

      cy.zoom(Math.min(2.5, Math.max(0.25, fitZoom)))
      cy.center(centerNode)
    }
    const handleNodeTap = (event: EventObject) => {
      if (event.target.id() === WORLD_CENTER_NODE_ID) {
        onSelect(null)
        return
      }
      const nodeId = event.target.data("nodeId")
      if (typeof nodeId === "string") onSelect(nodeId)
    }
    const handleCanvasTap = (event: EventObject) => {
      if (event.target === cy) onSelect(null)
    }
    cy.on("layoutstop", fitGraph)
    cy.on("tap", "node", handleNodeTap)
    cy.on("tap", handleCanvasTap)
    const layoutWidth = Math.max(container.clientWidth, 1)
    const layoutHeight = Math.max(container.clientHeight, 1)
    cy.layout({
      ...worldUnderstandingLayout({ x: layoutWidth / 2, y: layoutHeight / 2 }),
      boundingBox: { h: layoutHeight, w: layoutWidth, x1: 0, y1: 0 },
    }).run()
    fitGraph()
    const observer = new ResizeObserver(fitGraph)
    observer.observe(container)
    return () => {
      observer.disconnect()
      cy.destroy()
      cyRef.current = null
    }
  }, [graph, onSelect])

  useEffect(() => {
    if (cyRef.current !== null) applyWorldUnderstandingFocus(cyRef.current, selectedId)
  }, [selectedId])

  return <div aria-label={ariaLabel} className="profile-private-world__graph" ref={containerRef} role="img" />
}

function ringLabel(
  key: WorldUnderstanding["rings"][number]["key"],
  t: ReturnType<typeof useTranslation<"chat">>["t"],
): string {
  switch (key) {
    case "self":
      return t("profile.private.world.rings.self")
    case "family":
      return t("profile.private.world.rings.family")
    case "nest":
      return t("profile.private.world.rings.nest")
    case "society":
      return t("profile.private.world.rings.society")
    case "outside":
      return t("profile.private.world.rings.outside")
    default:
      return key
  }
}
