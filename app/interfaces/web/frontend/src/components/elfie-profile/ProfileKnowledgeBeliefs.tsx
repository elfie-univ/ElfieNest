import { useTranslation } from "react-i18next"

import type { KnowledgeBeliefs } from "./model"

type ProfileKnowledgeBeliefsProps = {
  readonly knowledge: KnowledgeBeliefs
  readonly status: "ready" | "empty" | "unavailable"
}

export function ProfileKnowledgeBeliefs({ knowledge, status }: ProfileKnowledgeBeliefsProps) {
  const { t } = useTranslation("chat")
  if (status !== "ready" || knowledge.edges.length === 0) {
    return <p className="profile-private-module__empty">{t("profile.private.knowledge.empty")}</p>
  }
  const labels = new Map(knowledge.nodes.map((node) => [node.id, node.label]))
  return (
    <ol aria-label={t("profile.private.knowledge.paths")} className="profile-private-knowledge">
      {knowledge.edges.map((edge) => (
        <li key={`${edge.source}-${edge.target}-${edge.relationKey}`}>
          <span className={`profile-private-knowledge__node profile-private-knowledge__node--${nodeKind(knowledge, edge.source)}`}>{labels.get(edge.source) ?? edge.source}</span>
          <small>{relationLabel(edge.relationKey, edge.displayLabel, t)}</small>
          <span className={`profile-private-knowledge__node profile-private-knowledge__node--${nodeKind(knowledge, edge.target)}`}>{labels.get(edge.target) ?? edge.target}</span>
        </li>
      ))}
    </ol>
  )
}

function nodeKind(knowledge: KnowledgeBeliefs, id: string): "source" | "knowledge" | "belief" {
  return knowledge.nodes.find((node) => node.id === id)?.kind ?? "knowledge"
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
