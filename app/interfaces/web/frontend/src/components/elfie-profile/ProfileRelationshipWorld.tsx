import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import type { RelationshipFilter, RelationshipWorld } from "./model"

type ProfileRelationshipWorldProps = {
  readonly status: "ready" | "empty" | "unavailable"
  readonly world: RelationshipWorld
}

const FILTERS: readonly RelationshipFilter[] = ["all", "human", "elfie"]

export function ProfileRelationshipWorld({ status, world }: ProfileRelationshipWorldProps) {
  const { t } = useTranslation("chat")
  const [filter, setFilter] = useState<RelationshipFilter>("all")
  const visible = useMemo(() => filterRelationshipWorld(world, filter), [filter, world])
  const visibleIds = new Set(visible.nodes.map((node) => node.id))
  const edges = world.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))

  return (
    <div className="profile-private-relationships">
      <div className="profile-private-relationships__filters" role="group" aria-label={t("profile.private.relationships.filterLabel")}>
        {FILTERS.map((candidate) => (
          <button
            aria-pressed={filter === candidate}
            className={filter === candidate ? "profile-private-relationships__filter profile-private-relationships__filter--active" : "profile-private-relationships__filter"}
            key={candidate}
            onClick={() => setFilter(candidate)}
            type="button"
          >
            {t(`profile.private.relationships.filters.${candidate}`)}
          </button>
        ))}
      </div>
      {status !== "ready" || visible.nodes.length === 0 ? (
        <p className="profile-private-module__empty">{t("profile.private.relationships.empty")}</p>
      ) : (
        <>
          <div className="profile-private-relationships__map" role="img" aria-label={t("profile.private.relationships.mapLabel")}>
            {visible.nodes.map((node, index) => {
              const position = node.kind === "self" ? { left: "50%", top: "50%" } : relationshipPosition(index, visible.nodes.length)
              return (
                <span
                  className={`profile-private-relationships__node profile-private-relationships__node--${node.kind}`}
                  key={node.id}
                  style={position}
                >
                  {node.label}
                </span>
              )
            })}
          </div>
          {edges.length > 0 ? (
            <ul aria-label={t("profile.private.relationships.connections")} className="profile-private-relationships__connections">
              {edges.map((edge) => (
                <li key={`${edge.source}-${edge.target}-${edge.relationKey}`}>
                  <span>{nodeLabel(visible.nodes, edge.source)}</span>
                  <small>{relationLabel(edge.relationKey, edge.displayLabel, t)}</small>
                  <span>{nodeLabel(visible.nodes, edge.target)}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </div>
  )
}

export function filterRelationshipWorld(world: RelationshipWorld, filter: RelationshipFilter): RelationshipWorld {
  const self = world.nodes.find((node) => node.kind === "self")
  const candidates = world.nodes
    .filter((node) => node.kind !== "self" && (filter === "all" || node.kind === filter))
    .slice(0, 19)
  const nodes = self === undefined ? candidates.slice(0, 20) : [self, ...candidates].slice(0, 20)
  const visibleIds = new Set(nodes.map((node) => node.id))
  return {
    nodes,
    edges: world.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)),
  }
}

function relationshipPosition(index: number, total: number): { readonly left: string; readonly top: string } {
  const angle = ((index - 1) / Math.max(1, total - 1)) * Math.PI * 2 - Math.PI / 2
  return {
    left: `${50 + Math.cos(angle) * 38}%`,
    top: `${50 + Math.sin(angle) * 38}%`,
  }
}

function nodeLabel(nodes: readonly RelationshipWorld["nodes"][number][], id: string): string {
  return nodes.find((node) => node.id === id)?.label ?? id
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
    default:
      return displayLabel || t("profile.private.relationships.relationFallback")
  }
}
