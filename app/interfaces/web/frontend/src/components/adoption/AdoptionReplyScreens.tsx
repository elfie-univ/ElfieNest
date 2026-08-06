import type { ReactNode } from "react"
import { RadioGroup as RadioGroupPrimitive } from "radix-ui"

import { Icon } from "../Icon"
import type {
  AdoptionAction,
  CandidateReply,
  NameMode,
} from "./adoption-model"

type JourneyT = (key: string, options?: Record<string, unknown>) => string
type CandidateImageUrl = (candidate: Pick<CandidateReply, "imageUrl" | "speciesId">) => string

type RepliesScreenProps = {
  readonly dispatch: React.Dispatch<AdoptionAction>
  readonly finalCandidateId: string | null
  readonly intro: ReactNode
  readonly replies: readonly CandidateReply[]
  readonly candidateImageUrl: CandidateImageUrl
}

export function RepliesScreen({ candidateImageUrl, dispatch, finalCandidateId, intro, replies }: RepliesScreenProps) {
  return <section>
    {intro}
    <div className="adoption-reply-grid">
      {replies.map((reply) => reply.status === "accepted" ? (
        <button
          aria-pressed={finalCandidateId === reply.candidateId}
          className={`adoption-choice adoption-reply-card ${finalCandidateId === reply.candidateId ? "adoption-choice--selected" : ""}`}
          key={reply.candidateId}
          onClick={() => dispatch({ type: "select-final", candidateId: reply.candidateId })}
          type="button"
        >
          <img alt="" src={candidateImageUrl(reply)} />
          <strong>{reply.originalName}</strong>
          <span>{reply.message}</span>
          {finalCandidateId === reply.candidateId ? <span className="adoption-choice__check"><Icon name="check" size={16} /></span> : null}
        </button>
      ) : (
        <div className="adoption-reply-card adoption-reply-card--unsure" key={reply.candidateId}>
          <img alt="" src={candidateImageUrl(reply)} />
          <strong>{reply.originalName}</strong>
          <span>{reply.message}</span>
        </div>
      ))}
    </div>
  </section>
}

type NamingScreenProps = {
  readonly candidate: CandidateReply
  readonly candidateImageUrl: CandidateImageUrl
  readonly customName: string
  readonly dispatch: React.Dispatch<AdoptionAction>
  readonly intro: ReactNode
  readonly nameMode: NameMode
  readonly t: JourneyT
}

export function NamingScreen({ candidate, candidateImageUrl, customName, dispatch, intro, nameMode, t }: NamingScreenProps) {
  const setNameMode = (value: string): void => {
    if (value === "original" || value === "suggested" || value === "custom") {
      dispatch({ type: "name-mode", mode: value })
    }
  }

  return <section>
    {intro}
    <div className="adoption-naming-layout">
      <div className="adoption-naming-person">
        <img alt={t("adoption.journey.naming.portraitAlt", { name: candidate.originalName })} src={candidateImageUrl(candidate)} />
        <strong>{candidate.originalName}</strong>
      </div>
      <fieldset className="adoption-name-options">
        <legend>{t("adoption.journey.naming.label")}</legend>
        <RadioGroupPrimitive.Root
          aria-label={t("adoption.journey.naming.label")}
          className="adoption-name-options__group"
          onValueChange={setNameMode}
          value={nameMode}
        >
          <RadioGroupPrimitive.Item className="adoption-name-option" value="original">
            <span aria-hidden="true" className="adoption-name-option__radio">
              <RadioGroupPrimitive.Indicator className="adoption-name-option__indicator" forceMount><Icon name="check" size={14} /></RadioGroupPrimitive.Indicator>
            </span>
            <span>{t("adoption.journey.naming.original", { name: candidate.originalName })}</span>
          </RadioGroupPrimitive.Item>
          <RadioGroupPrimitive.Item className="adoption-name-option" value="suggested">
            <span aria-hidden="true" className="adoption-name-option__radio">
              <RadioGroupPrimitive.Indicator className="adoption-name-option__indicator" forceMount><Icon name="check" size={14} /></RadioGroupPrimitive.Indicator>
            </span>
            <span>{t("adoption.journey.naming.suggested", { name: candidate.suggestedName })}</span>
          </RadioGroupPrimitive.Item>
          <div className="adoption-name-option-row" data-selected={nameMode === "custom" ? "true" : "false"}>
            <RadioGroupPrimitive.Item className="adoption-name-option" value="custom">
              <span aria-hidden="true" className="adoption-name-option__radio">
                <RadioGroupPrimitive.Indicator className="adoption-name-option__indicator" forceMount><Icon name="check" size={14} /></RadioGroupPrimitive.Indicator>
              </span>
              <span>{t("adoption.journey.naming.custom")}</span>
            </RadioGroupPrimitive.Item>
            <input
              aria-label={t("adoption.journey.naming.customInput")}
              maxLength={20}
              onChange={(event) => dispatch({ type: "custom-name", value: event.target.value })}
              onFocus={() => dispatch({ type: "name-mode", mode: "custom" })}
              placeholder={t("adoption.journey.naming.customPlaceholder")}
              value={customName}
            />
          </div>
        </RadioGroupPrimitive.Root>
      </fieldset>
    </div>
  </section>
}
