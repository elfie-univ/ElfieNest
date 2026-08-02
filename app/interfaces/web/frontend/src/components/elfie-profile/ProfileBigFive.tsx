import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { BIG_FIVE_TRAITS, type ElfieId } from "./model"
import {
  buildBigFiveRadarOption,
  resolveChartTheme,
  strongestBigFiveDescriptors,
  type BigFiveValues,
} from "./chart-options"
import {
  loadProfileChartRuntime,
  ProfileChart,
  type ProfileChartRuntime,
} from "./ProfileChart"

type ProfileBigFiveProps = {
  readonly elfieId: ElfieId
  readonly loadChartRuntime?: () => Promise<ProfileChartRuntime>
  readonly values: BigFiveValues
}

export function ProfileBigFive({
  elfieId,
  loadChartRuntime = loadProfileChartRuntime,
  values,
}: ProfileBigFiveProps) {
  const { t, i18n } = useTranslation("chat")
  const theme = useDocumentTheme()
  const traitLabels = {
    openness: t("profile.bigFive.traits.openness.label"),
    conscientiousness: t("profile.bigFive.traits.conscientiousness.label"),
    extraversion: t("profile.bigFive.traits.extraversion.label"),
    agreeableness: t("profile.bigFive.traits.agreeableness.label"),
    neuroticism: t("profile.bigFive.traits.neuroticism.label"),
  } satisfies Readonly<Record<keyof BigFiveValues, string>>
  const option = useMemo(() => buildBigFiveRadarOption(
    values,
    resolveChartTheme(window.getComputedStyle(document.documentElement)),
    traitLabels,
    t("profile.bigFive.title"),
  ), [i18n.resolvedLanguage, theme, values])
  const descriptorTraits = strongestBigFiveDescriptors(values).map((copy) => copy.trait)
  const accessibleValues = (
    <ul aria-label={t("profile.bigFive.values")} className="profile-radar__values profile-radar__values--accessible">
      {BIG_FIVE_TRAITS.map((trait) => (
        <li key={trait}>
          <span>{traitLabels[trait]}</span>
          <strong>{t("profile.bigFive.score", { score: Math.round(values[trait] * 100) })}</strong>
        </li>
      ))}
    </ul>
  )

  return (
    <section aria-labelledby={`big-five-${elfieId}`} className="profile-dossier__section profile-radar profile-radar--compact">
      <header className="profile-dossier__section-title">
        <span>{t("profile.bigFive.eyebrow")}</span>
        <p className="profile-dossier__section-name" id={`big-five-${elfieId}`}>
          {t("profile.bigFive.title")}
        </p>
      </header>
      <div className="profile-radar__content">
        <div className="profile-radar__chart">
          <ProfileChart
            chartKey={elfieId}
            label={t("profile.bigFive.chart")}
            loadRuntime={loadChartRuntime}
            option={option}
            summary={accessibleValues}
          />
        </div>
        <div className="profile-radar__descriptors">
          <ul aria-label={t("profile.bigFive.strongestList")}>
            {descriptorTraits.map((trait) => {
              return (
                <li className="profile-radar__descriptor" key={trait}><strong>{traitLabels[trait]}</strong></li>
              )
            })}
          </ul>
        </div>
      </div>
    </section>
  )
}

function useDocumentTheme(): string {
  const root = document.documentElement
  const readTheme = () => root.dataset["theme"] ?? ""
  const [theme, setTheme] = useState(readTheme)

  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(readTheme()))
    observer.observe(root, { attributeFilter: ["data-theme"], attributes: true })
    setTheme(readTheme())
    return () => observer.disconnect()
  }, [root])

  return theme
}
