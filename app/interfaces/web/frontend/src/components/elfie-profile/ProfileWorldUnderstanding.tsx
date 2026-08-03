import { useTranslation } from "react-i18next"

import type { WorldUnderstanding } from "./model"

type ProfileWorldUnderstandingProps = {
  readonly status: "ready" | "empty" | "unavailable"
  readonly world: WorldUnderstanding
}

export function ProfileWorldUnderstanding({ status, world }: ProfileWorldUnderstandingProps) {
  const { t } = useTranslation("chat")
  const hasNodes = world.rings.some((ring) => ring.nodes.length > 0)
  if (status !== "ready" || !hasNodes) {
    return <p className="profile-private-module__empty">{t("profile.private.world.empty")}</p>
  }
  return (
    <div className="profile-private-world">
      {world.summary.trim() ? <p className="profile-private-world__summary">{world.summary}</p> : null}
      <div className="profile-private-world__map" role="img" aria-label={t("profile.private.world.mapLabel")}>
        {world.rings.map((ring, index) => (
          <section className={`profile-private-world__ring profile-private-world__ring--${ring.key}`} key={ring.key}>
            <h4>{ringLabel(ring.key, t)}</h4>
            <ul>
              {ring.nodes.map((node) => <li key={node.id}>{node.label}</li>)}
            </ul>
            {index === 0 ? <span className="profile-private-world__center">{t("profile.private.world.center")}</span> : null}
          </section>
        ))}
      </div>
    </div>
  )
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
