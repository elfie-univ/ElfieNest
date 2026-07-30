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
  const traitCopy = BIG_FIVE_TRAITS.map((trait) => ({
    trait,
    label: t(`profile.bigFive.traits.${trait}.label`),
    description: t(`profile.bigFive.traits.${trait}.description`),
  }))
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
  const valueList = (
    <ul aria-label={t("profile.bigFive.values")} className="profile-radar__values">
      {traitCopy.map((copy) => (
        <li key={copy.trait}>
          <span>{copy.label}</span>
          <strong>{t("profile.bigFive.score", { score: Math.round(values[copy.trait] * 100) })}</strong>
        </li>
      ))}
    </ul>
  )

  return (
    <section aria-labelledby={`big-five-${elfieId}`} className="profile-dossier__section profile-radar">
      <header className="profile-dossier__section-title">
        <span>{t("profile.bigFive.eyebrow")}</span>
        <h2 id={`big-five-${elfieId}`}>{t("profile.bigFive.title")}</h2>
      </header>
      <div className="profile-dossier__radar">
        <div className="profile-radar__chart">
          <ProfileChart
            chartKey={elfieId}
            label={t("profile.bigFive.chart")}
            loadRuntime={loadChartRuntime}
            option={option}
            summary={valueList}
          />
        </div>
        <div className="profile-radar__descriptors">
          <p>{t("profile.bigFive.strongest")}</p>
          <ul aria-label={t("profile.bigFive.strongestList")}>
            {descriptorTraits.map((trait) => {
              const copy = traitCopy.find((candidate) => candidate.trait === trait)
              if (copy === undefined) throw new RangeError(`Missing trait copy: ${trait}`)
              return (
              <li key={trait}>
                <strong>{copy.label}</strong>
                <span>{copy.description}</span>
              </li>
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
