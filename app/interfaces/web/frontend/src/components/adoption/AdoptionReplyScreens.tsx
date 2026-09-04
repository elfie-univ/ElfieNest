import type {
  AdoptionAction,
  CandidateReply,
  NameMode,
} from "./adoption-model"
import { Button } from "../ui/button"

type JourneyT = (key: string, options?: Record<string, unknown>) => string
type CandidateImageUrl = (candidate: Pick<CandidateReply, "headshotImageUrl" | "fullBodyImageUrl" | "speciesId">, kind?: "headshot" | "fullBody") => string

function candidateAgeLabel(t: JourneyT, ageYears: number): string {
  return t("adoption.journey.shortlist.ageYears", { count: ageYears })
}

function trimTrailingPeriods(value: string): string {
  return value.replace(/[。.]+$/u, "")
}

type ArrivalWelcomeScreenProps = {
  readonly candidate: CandidateReply
  readonly candidateImageUrl: CandidateImageUrl
  readonly candidateLabel: string
  readonly customName: string
  readonly nameMode: NameMode
  readonly dispatch: React.Dispatch<AdoptionAction>
  readonly onFinish: () => void
  readonly pending: boolean
  readonly t: JourneyT
}

export function ArrivalWelcomeScreen({ candidate, candidateImageUrl, candidateLabel, customName, nameMode, dispatch, onFinish, pending, t }: ArrivalWelcomeScreenProps) {
  const originalName = candidate.reveal?.originalName ?? candidateLabel
  const displayName = nameMode === "custom" && customName.trim() ? customName.trim() : originalName
  const introduction = trimTrailingPeriods(candidate.reveal?.personalStory ?? t("adoption.journey.arrival.introFallback"))

  return <section className="adoption-arrival adoption-arrival--welcome">
    <div className="adoption-arrival__person">
      <div className="adoption-arrival__portal"><img alt={t("adoption.journey.naming.portraitAlt", { name: originalName })} src={candidateImageUrl(candidate)} /></div>
      <div className="adoption-arrival__person-info">
        <strong>{originalName}</strong>
        <span>{candidateAgeLabel(t, candidate.ageYears)} · {t(`adoption.journey.genders.${candidate.gender}`)}</span>
        <div className="adoption-tag-list adoption-arrival__tags">
          {candidate.personalityTags.slice(0, 3).map((value, index) => <span className="adoption-tag" key={`${index}-${value}`}>{value}</span>)}
        </div>
        <blockquote className="adoption-arrival__introduction">
          <p>{introduction}</p>
        </blockquote>
      </div>
    </div>
    <div className="adoption-arrival__copy">
      <h2>{t("adoption.journey.arrival.welcomeTitle", { name: displayName })}</h2>
      <p>{t("adoption.journey.arrival.confirmationHint")}</p>
      <label className="adoption-arrival__name">
        <span>{t("adoption.journey.arrival.nameLabel")}</span>
        <input
          aria-label={t("adoption.journey.arrival.nameInput")}
          maxLength={20}
          onChange={(event) => dispatch({ type: "custom-name", value: event.target.value })}
          placeholder={originalName}
          value={nameMode === "custom" ? customName : originalName}
        />
      </label>
      <div className="adoption-arrival__actions">
        <Button disabled={pending} onClick={onFinish} type="button">{t("adoption.journey.arrival.enter")}</Button>
      </div>
    </div>
  </section>
}
