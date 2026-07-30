import { useEffect, useState } from "react"
import type { ReactNode } from "react"
import type { TFunction } from "i18next"
import { ChevronDown, ChevronUp } from "lucide-react"
import { useTranslation } from "react-i18next"

import {
  ConfigModuleBody,
  MemoryModuleBody,
  TimelineModuleBody,
} from "./ProfilePrivateModuleBodies"
import { ProfileGraphSection } from "./ProfileGraphSection"
import { loadProfileChartRuntime, type ProfileChartRuntime } from "./ProfileChart"
import type { ElfieProfileProjection } from "./projection"

type ProfilePrivateModulesProps = {
  readonly loadChartRuntime?: () => Promise<ProfileChartRuntime>
  readonly projection: ElfieProfileProjection
}

type ModuleItem = {
  readonly displayTitle: string
  readonly title: string
  readonly renderBody: () => ReactNode
}

type AccordionState = {
  readonly resetKey: string
  readonly openTitles: readonly string[]
}

const NO_OPEN_TITLES: readonly string[] = []

export function ProfilePrivateModules({
  loadChartRuntime = loadProfileChartRuntime,
  projection,
}: ProfilePrivateModulesProps) {
  const { t } = useTranslation("chat")
  const elfieId = projection.publicProfile.elfieId
  const resetKey = `${elfieId}:${projection.kind}`
  const [accordion, setAccordion] = useState<AccordionState>({
    resetKey,
    openTitles: NO_OPEN_TITLES,
  })

  useEffect(() => {
    setAccordion((current) => {
      if (current.resetKey === resetKey && current.openTitles.length === 0) {
        return current
      }
      return { resetKey, openTitles: NO_OPEN_TITLES }
    })
  }, [resetKey])

  if (projection.kind === "visitor") {
    return null
  }

  const openTitles = accordion.resetKey === resetKey ? accordion.openTitles : NO_OPEN_TITLES
  const items = moduleItems(projection.privateCognition.modules, elfieId, loadChartRuntime, t)

  const toggle = (title: string): void => {
    setAccordion((current) => {
      const currentTitles = current.resetKey === resetKey ? current.openTitles : NO_OPEN_TITLES
      return {
        resetKey,
        openTitles: currentTitles.includes(title)
          ? currentTitles.filter((candidate) => candidate !== title)
          : [...currentTitles, title],
      }
    })
  }

  return (
    <section className="profile-dossier__private-modules" aria-label={t("profile.private.archive")}>
      {items.map((item, index) => {
        const open = openTitles.includes(item.title)
        const triggerId = `private-module-trigger-${elfieId}-${index}`
        const panelId = `private-module-panel-${elfieId}-${index}`
        return (
          <section className="profile-dossier__private-module" key={item.title}>
            <h3>
              <button
                id={triggerId}
                type="button"
                aria-controls={panelId}
                aria-expanded={open}
                onClick={() => toggle(item.title)}
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
  modules: Extract<ElfieProfileProjection, { readonly kind: "adopter" }>["privateCognition"]["modules"],
  elfieId: Extract<ElfieProfileProjection, { readonly kind: "adopter" }>["publicProfile"]["elfieId"],
  loadChartRuntime: () => Promise<ProfileChartRuntime>,
  t: TFunction<"chat">,
): readonly ModuleItem[] {
  const [memory, timeline, relationships, knowledge, world, config] = modules
  return [
    { title: memory.title, displayTitle: t("profile.private.titles.memory"), renderBody: () => <MemoryModuleBody module={memory} /> },
    { title: timeline.title, displayTitle: t("profile.private.titles.timeline"), renderBody: () => <TimelineModuleBody module={timeline} /> },
    {
      title: relationships.title,
      displayTitle: t("profile.private.titles.relationships"),
      renderBody: () => (
        <ProfileGraphSection elfieId={elfieId} loadChartRuntime={loadChartRuntime} module={relationships} />
      ),
    },
    {
      title: knowledge.title,
      displayTitle: t("profile.private.titles.knowledge"),
      renderBody: () => (
        <ProfileGraphSection elfieId={elfieId} loadChartRuntime={loadChartRuntime} module={knowledge} />
      ),
    },
    {
      title: world.title,
      displayTitle: t("profile.private.titles.world"),
      renderBody: () => (
        <ProfileGraphSection elfieId={elfieId} loadChartRuntime={loadChartRuntime} module={world} />
      ),
    },
    { title: config.title, displayTitle: t("profile.private.titles.food"), renderBody: () => <ConfigModuleBody module={config} /> },
  ]
}
