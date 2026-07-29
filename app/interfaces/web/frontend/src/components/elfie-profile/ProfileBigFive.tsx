import { useEffect, useMemo, useState } from "react"

import type { ElfieId } from "./model"
import {
  BIG_FIVE_COPY,
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
  const theme = useDocumentTheme()
  const option = useMemo(() => buildBigFiveRadarOption(
    values,
    resolveChartTheme(window.getComputedStyle(document.documentElement)),
  ), [theme, values])
  const descriptors = strongestBigFiveDescriptors(values)
  const valueList = (
    <ul aria-label="大五人格数值" className="profile-radar__values">
      {Object.values(BIG_FIVE_COPY).map((copy) => (
        <li key={copy.trait}>
          <span>{copy.label}</span>
          <strong>{Math.round(values[copy.trait] * 100)} 分</strong>
        </li>
      ))}
    </ul>
  )

  return (
    <section aria-labelledby={`big-five-${elfieId}`} className="profile-dossier__section profile-radar">
      <header className="profile-dossier__section-title">
        <span>内在画像</span>
        <h2 id={`big-five-${elfieId}`}>大五人格</h2>
      </header>
      <div className="profile-dossier__radar">
        <div className="profile-radar__chart">
          <ProfileChart
            chartKey={elfieId}
            label="大五人格雷达图"
            loadRuntime={loadChartRuntime}
            option={option}
            summary={valueList}
          />
        </div>
        <div className="profile-radar__descriptors">
          <p>最突出的公开特征</p>
          <ul aria-label="突出人格特征">
            {descriptors.map((copy) => (
              <li key={copy.trait}>
                <strong>{copy.label}</strong>
                <span>{copy.description}</span>
              </li>
            ))}
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
