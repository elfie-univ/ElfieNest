import { useEffect, useState } from "react"
import type { ReactNode } from "react"
import type { TFunction } from "i18next"
import { ChevronDown, ChevronUp } from "lucide-react"
import { useTranslation } from "react-i18next"

import { ProfileCareSettings } from "./ProfileCareSettings"
import { ProfileImportantExperiences } from "./ProfileImportantExperiences"
import { ProfileKnowledgeBeliefs } from "./ProfileKnowledgeBeliefs"
import { ProfileRecentFocus } from "./ProfileRecentFocus"
import { ProfileRelationshipWorld } from "./ProfileRelationshipWorld"
import { ProfileWorldUnderstanding } from "./ProfileWorldUnderstanding"
import type { CareSettings, PrivateCognition } from "./model"
import type { ElfieProfileProjection } from "./projection"

type ProfilePrivateModulesProps = {
  readonly csrfToken?: string | undefined
  readonly onFoodSaved?: (() => Promise<void>) | undefined
  readonly projection: ElfieProfileProjection
}

type ModuleKey = "focus" | "timeline" | "relationships" | "world" | "knowledge" | "food"

type ModuleItem = {
  readonly displayTitle: string
  readonly key: ModuleKey
  readonly renderBody: () => ReactNode
}

type AccordionState = {
  readonly openKeys: readonly ModuleKey[]
  readonly resetKey: string
}

const NO_OPEN_KEYS: readonly ModuleKey[] = []

export function ProfilePrivateModules({ csrfToken, onFoodSaved, projection }: ProfilePrivateModulesProps) {
  const { t } = useTranslation("chat")
  const elfieId = projection.publicProfile.elfieId
  const resetKey = `${elfieId}:${projection.kind}`
  const [accordion, setAccordion] = useState<AccordionState>({
    openKeys: NO_OPEN_KEYS,
    resetKey,
  })

  useEffect(() => {
    setAccordion((current) => {
      if (current.resetKey === resetKey && current.openKeys.length === 0) return current
      return { openKeys: NO_OPEN_KEYS, resetKey }
    })
  }, [resetKey])

  if (projection.kind === "visitor") return null

  const openKeys = accordion.resetKey === resetKey ? accordion.openKeys : NO_OPEN_KEYS
  const items = moduleItems(projection.privateCognition, projection.careSettings, elfieId, csrfToken, onFoodSaved, t)
  const toggle = (key: ModuleKey): void => {
    setAccordion((current) => {
      const currentKeys = current.resetKey === resetKey ? current.openKeys : NO_OPEN_KEYS
      return {
        resetKey,
        openKeys: currentKeys.includes(key)
          ? currentKeys.filter((candidate) => candidate !== key)
          : [...currentKeys, key],
      }
    })
  }

  return (
    <section className="profile-dossier__private-modules" aria-label={t("profile.private.archive")}>
      {items.map((item, index) => {
        const open = openKeys.includes(item.key)
        const triggerId = `private-module-trigger-${elfieId}-${index}`
        const panelId = `private-module-panel-${elfieId}-${index}`
        return (
          <section className="profile-dossier__private-module" key={item.key}>
            <h3>
              <button
                id={triggerId}
                type="button"
                aria-controls={panelId}
                aria-expanded={open}
                onClick={() => toggle(item.key)}
              >
                <span>{item.displayTitle}</span>
                {open ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
              </button>
            </h3>
            {open ? (
              <div
                id={panelId}
                className="profile-dossier__private-body"
                role="region"
                aria-labelledby={triggerId}
              >
                {item.renderBody()}
              </div>
            ) : null}
          </section>
        )
      })}
    </section>
  )
}

function moduleItems(
  cognition: PrivateCognition,
  careSettings: CareSettings,
  elfieId: string,
  csrfToken: string | undefined,
  onFoodSaved: (() => Promise<void>) | undefined,
  t: TFunction<"chat">,
): readonly ModuleItem[] {
  return [
    { key: "focus", displayTitle: t("profile.private.titles.focus"), renderBody: () => <ProfileRecentFocus focus={cognition.recentFocus} status={cognition.status} /> },
    { key: "timeline", displayTitle: t("profile.private.titles.timeline"), renderBody: () => <ProfileImportantExperiences experiences={cognition.importantExperiences} status={cognition.status} /> },
    { key: "relationships", displayTitle: t("profile.private.titles.relationships"), renderBody: () => <ProfileRelationshipWorld world={cognition.relationshipWorld} status={cognition.status} /> },
    { key: "world", displayTitle: t("profile.private.titles.world"), renderBody: () => <ProfileWorldUnderstanding world={cognition.worldUnderstanding} status={cognition.status} /> },
    { key: "knowledge", displayTitle: t("profile.private.titles.knowledge"), renderBody: () => <ProfileKnowledgeBeliefs knowledge={cognition.knowledgeBeliefs} status={cognition.status} /> },
    { key: "food", displayTitle: t("profile.private.titles.food"), renderBody: () => <ProfileCareSettings csrfToken={csrfToken} elfieId={elfieId} onSaved={onFoodSaved} settings={careSettings} /> },
  ]
}
