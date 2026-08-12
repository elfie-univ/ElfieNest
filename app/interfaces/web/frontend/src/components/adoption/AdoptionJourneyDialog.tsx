import { useEffect, useMemo, useReducer, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  adoptionCandidates,
  adoptionInfo,
  adoptionReplies,
  commitAdoption,
  type AdoptionCandidate,
  type AdoptionCandidateSetInput,
  type AdoptionInfo,
  type AdoptionReply,
} from "../../api/me/adoption"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../../i18n/errors"
import { currentLocale } from "../../i18n/format"
import { ConfirmDialog } from "../ConfirmDialog"
import { Button } from "../ui/button"
import { Checkbox } from "../ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog"
import { Icon } from "../Icon"
import dogAvatar from "../../assets/adoption/dog.svg"
import elfariaArrivalImage from "../../assets/adoption/elfaria-arrival-square.png"
import foxAvatar from "../../assets/adoption/fox.svg"
import {
  DEFAULT_DRAFT,
  INITIAL_ADOPTION_STATE,
  MAX_CANDIDATE_BATCHES,
  adoptionReducer,
  intentComplete,
  selectedName,
  type AdoptionAction,
  type AdoptionDraftState,
  type AdoptionScreen,
  type Candidate,
  type CandidateReply,
  type CompanionAnswer,
  type GenderPreference,
  type LifeStage,
  type SpeciesId,
} from "./adoption-model"
import { NamingScreen, RepliesScreen } from "./AdoptionReplyScreens"

type AdoptionJourneyDialogProps = {
  readonly accountId: string
  readonly csrfToken: string
  readonly open: boolean
  readonly onAdopted: (elfieId: string) => Promise<void>
  readonly onOpenChange: (open: boolean) => void
}

type JourneyT = (key: string, options?: Record<string, unknown>) => string

const LIFE_STAGES: readonly LifeStage[] = ["youth", "young_adult", "mature", "elder", "any"]
const SPECIES: readonly SpeciesId[] = ["fox", "dog"]
const SPECIES_IMAGES: Readonly<Record<SpeciesId, string>> = { fox: foxAvatar, dog: dogAvatar }
const GENDERS: readonly GenderPreference[] = ["male", "female", "any"]
const APPEARANCE_GROUPS = ["stature", "build", "face", "signature"] as const
const COMPANIONSHIP_OPTIONS: readonly (readonly CompanionAnswer[])[] = [
  ["approach", "quiet", "independent", "any"],
  ["explore", "research", "observe", "any"],
  ["adapt", "plan", "comfort", "any"],
  ["direct", "discuss", "pause", "any"],
  ["lively", "steady", "space", "any"],
]

const STAGE_FOR_SCREEN: Partial<Record<AdoptionScreen, number>> = {
  basic: 0,
  appearance: 1,
  companionship: 2,
  review: 3,
  generating: 3,
  shortlist: 3,
  inviting: 3,
  replies: 3,
  naming: 3,
  committing: 3,
  arrival: 3,
}

function welcomeStorageKey(accountId: string): string {
  return `elfienest.adoption-welcome.${accountId}.v1`
}

function draftStorageKey(accountId: string): string {
  return `elfienest.adoption-draft.${accountId}.v1`
}

function hasSkippedWelcome(accountId: string): boolean {
  try {
    return window.localStorage.getItem(welcomeStorageKey(accountId)) === "skipped"
  } catch {
    return false
  }
}

function markWelcomeSkipped(accountId: string): void {
  try {
    window.localStorage.setItem(welcomeStorageKey(accountId), "skipped")
  } catch {
    // Storage can be disabled; the flow remains usable and will show the welcome again.
  }
}

function readDraft(accountId: string): AdoptionDraftState | null {
  try {
    const raw = window.localStorage.getItem(draftStorageKey(accountId))
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object" || !("draft" in parsed)) return null
    return parsed as AdoptionDraftState
  } catch {
    return null
  }
}

function saveDraft(accountId: string, state: AdoptionDraftState): void {
  if (!state.dirty || state.screen === "arrival") return
  try {
    const resumableScreen = ["basic", "appearance", "companionship", "review"].includes(state.screen) ? state.screen : "review"
    window.localStorage.setItem(draftStorageKey(accountId), JSON.stringify({ ...state, screen: resumableScreen, candidates: [], replies: [], selectedCandidateIds: [], finalCandidateId: null, candidateSetId: null }))
  } catch {
    // A failed draft write must not block adoption.
  }
}

function clearDraft(accountId: string): void {
  try {
    window.localStorage.removeItem(draftStorageKey(accountId))
  } catch {
    // Best effort only.
  }
}

function asCandidate(candidate: AdoptionCandidate): Candidate {
  return {
    candidateId: candidate.candidate_id,
    originalName: candidate.original_name,
    suggestedName: candidate.suggested_name,
    speciesId: candidate.species_id,
    lifeStage: candidate.life_stage as LifeStage,
    gender: candidate.gender,
    imageUrl: candidate.image_url,
    appearanceTags: candidate.appearance_tags,
    personalityTags: candidate.personality_tags,
    introduction: candidate.introduction,
    compatibility: candidate.compatibility,
  }
}

function asReply(reply: AdoptionReply): CandidateReply {
  return { ...asCandidate(reply), status: reply.status, message: reply.message }
}

function speciesImageUrl(speciesId: SpeciesId): string {
  return SPECIES_IMAGES[speciesId]
}

function candidateImageUrl(candidate: Pick<Candidate, "imageUrl" | "speciesId">): string {
  return candidate.imageUrl.startsWith("/adoption/") ? speciesImageUrl(candidate.speciesId) : candidate.imageUrl
}

function speciesName(t: (key: string) => string, speciesId: SpeciesId): string {
  return t(`adoption.journey.species.${speciesId}`)
}

function stageName(t: (key: string) => string, stage: LifeStage): string {
  return t(`adoption.journey.lifeStages.${stage}`)
}

function ChoiceButton({
  children,
  className = "",
  onClick,
  selected,
  ...props
}: React.ComponentProps<"button"> & { readonly selected: boolean }) {
  return (
    <button
      aria-pressed={selected}
      className={`adoption-choice ${selected ? "adoption-choice--selected" : ""} ${className}`}
      onClick={onClick}
      type="button"
      {...props}
    >
      {children}
      {selected ? <span className="adoption-choice__check"><Icon name="check" size={16} /></span> : null}
    </button>
  )
}

function ScreenIntro({
  eyebrow,
  title,
  description,
  badge,
}: {
  readonly eyebrow?: string
  readonly title: string
  readonly description?: string
  readonly badge?: string
}) {
  return (
    <div className="adoption-screen-intro">
      <div>
        {eyebrow ? <p className="adoption-eyebrow">{eyebrow}</p> : null}
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {badge ? <span className="adoption-badge">{badge}</span> : null}
    </div>
  )
}

function TagList({ values }: { readonly values: readonly string[] }) {
  return <div className="adoption-tag-list">{values.map((value, index) => <span className="adoption-tag" key={`${index}-${value}`}>{value}</span>)}</div>
}

export function AdoptionJourneyDialog({ accountId, csrfToken, open, onAdopted, onOpenChange }: AdoptionJourneyDialogProps) {
  const { i18n, t } = useTranslation("chat")
  const locale = currentLocale(i18n)
  const [state, dispatch] = useReducer(adoptionReducer, INITIAL_ADOPTION_STATE)
  const [info, setInfo] = useState<AdoptionInfo | null>(null)
  const [loadingInfo, setLoadingInfo] = useState(false)
  const [closePrompt, setClosePrompt] = useState(false)
  const [intentConfirmOpen, setIntentConfirmOpen] = useState(false)
  const [finalConfirmOpen, setFinalConfirmOpen] = useState(false)
  const [apiError, setApiError] = useState<LocalizedErrorState>(null)
  const isBusy = state.screen === "generating" || state.screen === "inviting" || state.screen === "committing"
  const isIntentLocked = !["welcome", "basic", "appearance", "companionship", "review"].includes(state.screen)

  useEffect(() => {
    if (!open) return
    const saved = readDraft(accountId)
    if (saved?.dirty && saved.screen !== "arrival") {
      dispatch({ type: "reset", screen: saved.screen })
      for (const field of ["speciesId", "lifeStage", "gender"] as const) {
        const value = saved.draft[field]
        if (value !== DEFAULT_DRAFT[field] && !(field === "speciesId" && value === null)) dispatch({ type: "set-basic", field, value: value as SpeciesId | LifeStage | GenderPreference })
      }
      for (const field of ["stature", "build", "face", "signature", "priority"] as const) {
        const value = saved.draft[field]
        if (value !== DEFAULT_DRAFT[field]) dispatch({ type: "set-appearance", field, value })
      }
      saved.draft.answers.forEach((answer, index) => { if (answer !== null) dispatch({ type: "set-answer", index, value: answer }) })
    } else {
      dispatch({ type: "reset", screen: hasSkippedWelcome(accountId) ? "basic" : "welcome" })
    }
    setLoadingInfo(true)
    setApiError(null)
    void adoptionInfo().then(setInfo).catch((reason: unknown) => setApiError(describeApiError(reason, "manage.load"))).finally(() => setLoadingInfo(false))
  }, [accountId, open])

  useEffect(() => {
    if (open) saveDraft(accountId, state)
  }, [accountId, open, state])

  const allowedSpecies = useMemo(() => {
    const configured = info?.species_ids.filter((value): value is SpeciesId => value === "dog" || value === "fox")
    return [...(configured?.length ? configured : SPECIES)].sort((left, right) => Number(left !== "fox") - Number(right !== "fox"))
  }, [info])

  const requestClose = (): void => {
    if (isBusy) return
    if (state.dirty && state.screen !== "welcome" && state.screen !== "arrival") {
      setClosePrompt(true)
      return
    }
    onOpenChange(false)
  }

  const confirmDiscard = (): void => {
    clearDraft(accountId)
    dispatch({ type: "reset", screen: "basic" })
    setClosePrompt(false)
    onOpenChange(false)
  }

  const goToBasic = (skipWelcome = false): void => {
    if (skipWelcome) markWelcomeSkipped(accountId)
    dispatch({ type: "screen", screen: "basic" })
  }

  const navigateToStage = (index: number): void => {
    if (isIntentLocked) return
    if (index === 0) {
      dispatch({ type: "screen", screen: "basic" })
      return
    }
    if (index === 1) {
      dispatch({ type: "screen", screen: "appearance" })
      return
    }
    if (index === 2) {
      const firstUnanswered = state.draft.answers.findIndex((answer) => answer === null)
      dispatch({ type: "screen", screen: "companionship" })
      dispatch({ type: "question", index: firstUnanswered === -1 ? 0 : firstUnanswered })
      return
    }
    if (!intentComplete(state.draft)) {
      dispatch({ type: "error", message: t("adoption.journey.validation.completeIntent") })
      return
    }
    dispatch({ type: "screen", screen: "review" })
  }

  const answerCompanionship = (index: number, value: CompanionAnswer): void => {
    dispatch({ type: "set-answer", index, value })
    if (index < COMPANIONSHIP_OPTIONS.length - 1) {
      dispatch({ type: "question", index: index + 1 })
    }
  }

  const intentPayload = (): AdoptionCandidateSetInput => {
    const speciesId = state.draft.speciesId
    if (speciesId === null) throw new Error("Adoption species is required")
    const answers = state.draft.answers.map((answer) => {
      if (answer === null) throw new Error("Every Adoption answer is required")
      return answer
    })
    return {
      species_id: speciesId,
      life_stage: state.draft.lifeStage,
      gender: state.draft.gender,
      appearance: {
        stature: state.draft.stature,
        build: state.draft.build,
        face: state.draft.face,
        signature: state.draft.signature,
        priority: state.draft.priority,
      },
      answers,
    }
  }

  const generateCandidates = async (): Promise<void> => {
    if (!intentComplete(state.draft)) {
      dispatch({ type: "error", message: t("adoption.journey.validation.completeIntent") })
      return
    }
    const batch = state.candidateBatch + 1
    if (batch > MAX_CANDIDATE_BATCHES) return
    setApiError(null)
    dispatch({ type: "screen", screen: "generating" })
    try {
      const result = await adoptionCandidates(intentPayload(), csrfToken)
      dispatch({ type: "candidates-ready", batch, setId: result.candidate_set_id, candidates: result.candidates.map(asCandidate) })
    } catch (reason: unknown) {
      setApiError(describeApiError(reason, "manage.save"))
      dispatch({ type: "error", message: t("adoption.journey.errors.generate") })
    }
  }

  const sendInvitations = async (): Promise<void> => {
    if (state.candidateSetId === null || state.selectedCandidateIds.length === 0) {
      dispatch({ type: "error", message: t("adoption.journey.validation.chooseCandidate") })
      return
    }
    setApiError(null)
    dispatch({ type: "screen", screen: "inviting" })
    try {
      const result = await adoptionReplies(state.candidateSetId, state.selectedCandidateIds, csrfToken)
      dispatch({ type: "replies-ready", replies: result.replies.map(asReply) })
    } catch (reason: unknown) {
      setApiError(describeApiError(reason, "manage.save"))
      dispatch({ type: "error", message: t("adoption.journey.errors.replies") })
    }
  }

  const finishAdoption = async (): Promise<void> => {
    if (state.candidateSetId === null || state.finalCandidateId === null) {
      dispatch({ type: "error", message: t("adoption.journey.validation.chooseReply") })
      return
    }
    const name = selectedName(state)
    if (!name || name.length > 20) {
      dispatch({ type: "error", message: t("adoption.journey.validation.name") })
      return
    }
    setApiError(null)
    dispatch({ type: "screen", screen: "committing" })
    try {
      const result = await commitAdoption(state.candidateSetId, state.finalCandidateId, name, csrfToken)
      clearDraft(accountId)
      await onAdopted(result.elfie_id)
      dispatch({ type: "screen", screen: "arrival" })
    } catch (reason: unknown) {
      setApiError(describeApiError(reason, "manage.save"))
      dispatch({ type: "error", message: t("adoption.journey.errors.commit") })
    }
  }

  const requestFinishAdoption = (): void => {
    if (state.candidateSetId === null || state.finalCandidateId === null) {
      dispatch({ type: "error", message: t("adoption.journey.validation.chooseReply") })
      return
    }
    const name = selectedName(state)
    if (!name || name.length > 20) {
      dispatch({ type: "error", message: t("adoption.journey.validation.name") })
      return
    }
    setFinalConfirmOpen(true)
  }

  const next = (): void => {
    switch (state.screen) {
      case "welcome": goToBasic(); return
      case "basic":
        if (state.draft.speciesId === null) dispatch({ type: "error", message: t("adoption.journey.validation.species") })
        else dispatch({ type: "screen", screen: "appearance" })
        return
      case "appearance": dispatch({ type: "screen", screen: "companionship" }); return
      case "companionship":
        if (intentComplete(state.draft)) dispatch({ type: "screen", screen: "review" })
        else dispatch({ type: "error", message: t("adoption.journey.validation.completeIntent") })
        return
      case "review":
        if (intentComplete(state.draft)) setIntentConfirmOpen(true)
        else dispatch({ type: "error", message: t("adoption.journey.validation.completeIntent") })
        return
      case "shortlist": void sendInvitations(); return
      case "replies":
        if (state.finalCandidateId === null) dispatch({ type: "error", message: t("adoption.journey.validation.chooseReply") })
        else dispatch({ type: "screen", screen: "naming" })
        return
      case "naming": requestFinishAdoption(); return
      default: return
    }
  }

  const back = (): void => {
    if (isBusy) return
    switch (state.screen) {
      case "appearance": dispatch({ type: "screen", screen: "basic" }); return
      case "companionship":
        if (state.questionIndex > 0) dispatch({ type: "question", index: state.questionIndex - 1 })
        else dispatch({ type: "screen", screen: "appearance" })
        return
      case "review": dispatch({ type: "screen", screen: "companionship" }); dispatch({ type: "question", index: 4 }); return
      case "shortlist": dispatch({ type: "screen", screen: "review" }); return
      case "replies": dispatch({ type: "screen", screen: "shortlist" }); return
      case "naming": dispatch({ type: "screen", screen: "replies" }); return
      default: return
    }
  }

  const errorMessage = resolveLocalizedError(apiError, locale)
  const selectedCandidate = state.replies.find((candidate) => candidate.candidateId === state.finalCandidateId)
  const title = state.screen === "welcome" ? t("adoption.journey.window.welcomeTitle") : t("adoption.journey.window.title")
  const stage = STAGE_FOR_SCREEN[state.screen]
  const showFooter = !["welcome", "generating", "inviting", "committing", "arrival"].includes(state.screen)
  const showBack = state.screen === "naming" || (!isIntentLocked && state.screen !== "basic")

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (nextOpen) onOpenChange(true); else requestClose() }}>
      <DialogContent
        className="adoption-dialog"
        onEscapeKeyDown={(event) => { event.preventDefault(); requestClose() }}
        onPointerDownOutside={(event) => { event.preventDefault(); requestClose() }}
        showCloseButton={false}
      >
        <DialogHeader className="adoption-dialog__header">
          <div>
            <p className="adoption-dialog__kicker">{t("adoption.journey.window.kicker")}</p>
            <DialogTitle>{title}</DialogTitle>
          </div>
          <Button aria-label={t("adoption.close")} className="adoption-dialog__close" disabled={isBusy} onClick={requestClose} size="icon" type="button" variant="ghost"><Icon name="x" /></Button>
        </DialogHeader>

        {state.screen !== "welcome" && state.screen !== "arrival" ? (
          <ol aria-label={t("adoption.journey.progress.label")} className="adoption-progress">
            {(["basic", "appearance", "companionship", "meeting"] as const).map((key, index) => (
              <li aria-current={stage === index ? "step" : undefined} key={key}>
                <button aria-label={t(`adoption.journey.progress.${key}`)} disabled={isIntentLocked || (index === 3 && !intentComplete(state.draft))} onClick={() => navigateToStage(index)} type="button">
                  <span>{index + 1}</span>{t(`adoption.journey.progress.${key}`)}
                </button>
              </li>
            ))}
          </ol>
        ) : null}

        <div aria-live="polite" className="adoption-dialog__body">
          {loadingInfo && state.screen === "basic" ? <div className="adoption-loading"><span className="adoption-spinner" aria-hidden="true" />{t("adoption.journey.loading")}</div> : null}
          {!loadingInfo && state.screen === "welcome" ? <WelcomeScreen t={t} onStart={goToBasic} /> : null}
          {!loadingInfo && state.screen === "basic" ? <BasicScreen allowedSpecies={allowedSpecies} canAdopt={info?.quota.can_adopt ?? true} draft={state.draft} dispatch={dispatch} speciesName={(id) => speciesName(t, id)} stageName={(value) => stageName(t, value)} t={t} /> : null}
          {state.screen === "appearance" ? <AppearanceScreen draft={state.draft} dispatch={dispatch} t={t} /> : null}
          {state.screen === "companionship" ? <CompanionshipScreen draft={state.draft} dispatch={dispatch} onAnswer={answerCompanionship} questionIndex={state.questionIndex} t={t} /> : null}
          {state.screen === "review" ? <ReviewScreen draft={state.draft} dispatch={dispatch} stageName={(value) => stageName(t, value)} speciesName={(id) => speciesName(t, id)} t={t} /> : null}
          {state.screen === "generating" ? <ProgressScreen icon="sparkles" title={t("adoption.journey.generating.title")} /> : null}
          {state.screen === "shortlist" ? <ShortlistScreen candidates={state.candidates} candidateBatch={state.candidateBatch} dispatch={dispatch} onRegenerate={() => { void generateCandidates() }} selectedIds={state.selectedCandidateIds} stageName={(value) => stageName(t, value)} t={t} /> : null}
          {state.screen === "inviting" ? <InvitingScreen candidates={state.candidates.filter((candidate) => state.selectedCandidateIds.includes(candidate.candidateId))} t={t} /> : null}
          {state.screen === "replies" ? <RepliesScreen candidateImageUrl={candidateImageUrl} dispatch={dispatch} finalCandidateId={state.finalCandidateId} intro={<ScreenIntro title={t("adoption.journey.replies.title", { count: state.replies.filter((reply) => reply.status === "accepted").length })} />} replies={state.replies} /> : null}
          {state.screen === "naming" && selectedCandidate ? <NamingScreen candidate={selectedCandidate} candidateImageUrl={candidateImageUrl} customName={state.customName} dispatch={dispatch} intro={<ScreenIntro title={t("adoption.journey.naming.title")} />} nameMode={state.nameMode} t={t} /> : null}
          {state.screen === "committing" ? <ProgressScreen icon="house" title={t("adoption.journey.committing.title", { name: selectedName(state) })} /> : null}
          {state.screen === "arrival" && selectedCandidate ? <ArrivalScreen candidate={selectedCandidate} name={selectedName(state)} onFinish={() => { onOpenChange(false) }} t={t} /> : null}
          {state.error ? <p className="adoption-inline-error" role="alert">{state.error}</p> : null}
          {errorMessage ? <p className="adoption-inline-error" role="alert">{errorMessage}</p> : null}
        </div>

        {showFooter ? (
          <footer className="adoption-dialog__footer">
            {showBack ? <Button onClick={back} type="button" variant="ghost">{t("adoption.journey.actions.back")}</Button> : null}
            <div>
              <span className="adoption-footer-hint">{footerHint(state, t)}</span>
              <Button disabled={isNextDisabled(state, info)} onClick={next} type="button">{nextLabel(state, t)}</Button>
            </div>
          </footer>
        ) : null}

        <ConfirmDialog
          cancelLabel={t("adoption.journey.intentConfirm.cancel")}
          confirmLabel={t("adoption.journey.intentConfirm.confirm")}
          description={t("adoption.journey.intentConfirm.description")}
          onConfirm={() => { setIntentConfirmOpen(false); void generateCandidates() }}
          onOpenChange={setIntentConfirmOpen}
          open={intentConfirmOpen}
          title={t("adoption.journey.intentConfirm.title")}
        />
        <ConfirmDialog
          cancelLabel={t("adoption.journey.finalConfirm.cancel")}
          confirmLabel={t("adoption.journey.finalConfirm.confirm")}
          description={t("adoption.journey.finalConfirm.description")}
          onConfirm={() => { setFinalConfirmOpen(false); void finishAdoption() }}
          onOpenChange={setFinalConfirmOpen}
          open={finalConfirmOpen}
          pending={state.screen === "committing"}
          title={t("adoption.journey.finalConfirm.title")}
        />

        {closePrompt ? (
          <div aria-labelledby="adoption-close-title" aria-modal="true" className="adoption-close-prompt" role="alertdialog">
            <div className="adoption-close-prompt__card">
              <h2 id="adoption-close-title">{t("adoption.journey.closePrompt.title")}</h2>
              <p>{t("adoption.journey.closePrompt.description")}</p>
              <div><Button onClick={() => setClosePrompt(false)} type="button" variant="ghost">{t("adoption.journey.closePrompt.continue")}</Button><Button onClick={confirmDiscard} type="button" variant="destructive">{t("adoption.journey.closePrompt.discard")}</Button></div>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

function WelcomeScreen({ t, onStart }: { readonly t: JourneyT; readonly onStart: (skipWelcome: boolean) => void }) {
  const [skipWelcome, setSkipWelcome] = useState(false)
  return <section className="adoption-welcome">
    <div className="adoption-welcome__art"><img alt={t("adoption.journey.welcome.imageAlt")} src={elfariaArrivalImage} /></div>
    <div className="adoption-welcome__copy"><h2>{t("adoption.journey.welcome.title")}</h2><p>{t("adoption.journey.welcome.description")}</p><div className="adoption-welcome__note"><Icon name="scroll" size={18} /><span>{t("adoption.journey.welcome.note")}</span></div><label className="adoption-welcome__skip"><Checkbox aria-label={t("adoption.journey.welcome.skip")} checked={skipWelcome} className="adoption-welcome__checkbox" onCheckedChange={(checked) => setSkipWelcome(checked === true)} /><span>{t("adoption.journey.welcome.skip")}</span></label><Button onClick={() => onStart(skipWelcome)} type="button">{t("adoption.journey.welcome.start")}</Button></div>
  </section>
}

function BasicScreen({
  allowedSpecies, canAdopt, dispatch, draft, speciesName, stageName, t,
}: {
  readonly allowedSpecies: readonly SpeciesId[]
  readonly canAdopt: boolean
  readonly dispatch: React.Dispatch<AdoptionAction>
  readonly draft: AdoptionDraftState["draft"]
  readonly speciesName: (id: SpeciesId) => string
  readonly stageName: (stage: LifeStage) => string
  readonly t: JourneyT
}) {
  return <section>
    <ScreenIntro badge={t("adoption.journey.badges.oneMinute")} title={t("adoption.journey.basic.title")} />
    <fieldset className="adoption-fieldset"><legend>{t("adoption.journey.basic.speciesLabel")}</legend><div className="adoption-species-grid">
      {allowedSpecies.map((speciesId) => <ChoiceButton className="adoption-species-choice" key={speciesId} onClick={() => dispatch({ type: "set-basic", field: "speciesId", value: speciesId })} selected={draft.speciesId === speciesId}><img alt="" src={speciesImageUrl(speciesId)} /><span><strong>{speciesName(speciesId)}</strong></span></ChoiceButton>)}
    </div></fieldset>
    <fieldset className="adoption-fieldset"><legend>{t("adoption.journey.basic.lifeStageLabel")}</legend><div className="adoption-option-row">{LIFE_STAGES.map((stage) => <ChoiceButton key={stage} onClick={() => dispatch({ type: "set-basic", field: "lifeStage", value: stage })} selected={draft.lifeStage === stage}>{stageName(stage)}</ChoiceButton>)}</div></fieldset>
    <fieldset className="adoption-fieldset"><legend>{t("adoption.journey.basic.genderLabel")}</legend><div className="adoption-option-row">{GENDERS.map((gender) => <ChoiceButton key={gender} onClick={() => dispatch({ type: "set-basic", field: "gender", value: gender })} selected={draft.gender === gender}>{t(`adoption.journey.genders.${gender}`)}</ChoiceButton>)}</div></fieldset>
    {!canAdopt ? <p className="adoption-quota-warning">{t("adoption.journey.quota.exhausted")}</p> : null}
  </section>
}

function AppearanceScreen({ draft, dispatch, t }: { readonly draft: AdoptionDraftState["draft"]; readonly dispatch: React.Dispatch<AdoptionAction>; readonly t: JourneyT }) {
  const groups: Record<(typeof APPEARANCE_GROUPS)[number], readonly string[]> = {
    stature: ["small", "standard", "tall", "any"],
    build: ["slim", "standard", "round", "any"],
    face: ["soft", "balanced", "defined", "any"],
    signature: ["warm", "marked", "ears", "any"],
  }
  return <section>
    <ScreenIntro badge={t("adoption.journey.badges.broadChoices")} title={t("adoption.journey.appearance.title")} />
    <div className="adoption-appearance-grid">{APPEARANCE_GROUPS.map((group) => <fieldset className="adoption-fieldset" key={group}><legend>{t(`adoption.journey.appearance.groups.${group}.label`)}</legend><div className="adoption-appearance-options">{groups[group].map((value) => <ChoiceButton className="adoption-appearance-choice" key={value} onClick={() => dispatch({ type: "set-appearance", field: group, value } as AdoptionAction)} selected={draft[group] === value}><span className={`adoption-shape adoption-shape--${value}`} aria-hidden="true" />{t(`adoption.journey.appearance.groups.${group}.${value}`)}</ChoiceButton>)}</div></fieldset>)}</div>
    <fieldset className="adoption-fieldset"><legend>{t("adoption.journey.appearance.priorityLabel")}</legend><div className="adoption-option-row">{(["stature", "build", "face", "signature"] as const).map((priority) => <ChoiceButton key={priority} onClick={() => dispatch({ type: "set-appearance", field: "priority", value: priority })} selected={draft.priority === priority}>{t(`adoption.journey.appearance.groups.${priority}.label`)}</ChoiceButton>)}</div></fieldset>
  </section>
}

function CompanionshipScreen({ draft, dispatch, onAnswer, questionIndex, t }: { readonly draft: AdoptionDraftState["draft"]; readonly dispatch: React.Dispatch<AdoptionAction>; readonly onAnswer: (index: number, value: CompanionAnswer) => void; readonly questionIndex: number; readonly t: JourneyT }) {
  const options = COMPANIONSHIP_OPTIONS[questionIndex] ?? COMPANIONSHIP_OPTIONS[0] ?? []
  return <section>
    <ScreenIntro badge={t("adoption.journey.badges.questionCount", { current: questionIndex + 1, total: 5 })} title={t("adoption.journey.companionship.title")} />
    <div className="adoption-question-layout"><nav aria-label={t("adoption.journey.companionship.questionLabel")} className="adoption-question-index">{[0, 1, 2, 3, 4].map((index) => <button aria-current={index === questionIndex ? "step" : undefined} className={index === questionIndex ? "adoption-question-index__item adoption-question-index__item--active" : "adoption-question-index__item"} key={index} onClick={() => dispatch({ type: "question", index })} type="button"><span>{index + 1}</span><small>{t(`adoption.journey.companionship.shortLabels.${index}`)}</small></button>)}</nav><div className="adoption-question-card"><p className="adoption-eyebrow">{t(`adoption.journey.companionship.scenarios.${questionIndex}.label`)}</p><h3>{t(`adoption.journey.companionship.scenarios.${questionIndex}.title`)}</h3><div className="adoption-answer-grid">{options.map((option) => <ChoiceButton key={option} onClick={() => onAnswer(questionIndex, option)} selected={draft.answers[questionIndex] === option}>{t(`adoption.journey.companionship.answers.${option}`)}</ChoiceButton>)}</div></div></div>
  </section>
}

function ReviewScreen({ draft, dispatch, speciesName, stageName, t }: { readonly draft: AdoptionDraftState["draft"]; readonly dispatch: React.Dispatch<AdoptionAction>; readonly speciesName: (id: SpeciesId) => string; readonly stageName: (stage: LifeStage) => string; readonly t: JourneyT }) {
  const answers = draft.answers.filter((answer): answer is CompanionAnswer => answer !== null).map((answer) => t(`adoption.journey.companionship.answers.${answer}`))
  return <section><ScreenIntro badge={t("adoption.journey.badges.editable")} eyebrow={t("adoption.journey.review.eyebrow")} title={t("adoption.journey.review.title")} /><div className="adoption-review-grid"><ReviewCard title={t("adoption.journey.review.basic")} onEdit={() => dispatch({ type: "screen", screen: "basic" })} t={t} values={draft.speciesId ? [speciesName(draft.speciesId), stageName(draft.lifeStage), t(`adoption.journey.genders.${draft.gender}`)] : []} /><ReviewCard title={t("adoption.journey.review.appearance")} onEdit={() => dispatch({ type: "screen", screen: "appearance" })} t={t} values={[t(`adoption.journey.appearance.groups.stature.${draft.stature}`), t(`adoption.journey.appearance.groups.build.${draft.build}`), t(`adoption.journey.appearance.groups.face.${draft.face}`), t(`adoption.journey.appearance.groups.signature.${draft.signature}`), `${t("adoption.journey.review.priority")}: ${t(`adoption.journey.appearance.groups.${draft.priority}.label`)}`]} /><ReviewCard title={t("adoption.journey.review.companionship")} onEdit={() => { dispatch({ type: "screen", screen: "companionship" }); dispatch({ type: "question", index: 0 }) }} t={t} values={answers} /></div></section>
}

function ReviewCard({ title, values, onEdit, t }: { readonly title: string; readonly values: readonly string[]; readonly onEdit: () => void; readonly t: JourneyT }) {
  return <section className="adoption-review-card"><div><h3>{title}</h3><Button aria-label={`${t("adoption.journey.actions.edit")} ${title}`} onClick={onEdit} size="icon-sm" type="button" variant="ghost"><Icon name="pencil" size={16} /></Button></div><TagList values={values} /></section>
}

function ProgressScreen({ icon, title }: { readonly icon: "sparkles" | "house"; readonly title: string }) {
  return <section className="adoption-progress-screen"><div className="adoption-progress-screen__icon"><Icon name={icon === "house" ? "house" : "palette"} size={34} /></div><h2>{title}</h2><span className="adoption-spinner" aria-label={title} /></section>
}

function ShortlistScreen({ candidates, candidateBatch, dispatch, onRegenerate, selectedIds, stageName, t }: { readonly candidates: readonly Candidate[]; readonly candidateBatch: number; readonly dispatch: React.Dispatch<AdoptionAction>; readonly onRegenerate: () => void; readonly selectedIds: readonly string[]; readonly stageName: (stage: LifeStage) => string; readonly t: JourneyT }) {
  const canRegenerate = candidateBatch < MAX_CANDIDATE_BATCHES
  return <section>
    <ScreenIntro badge={t("adoption.journey.badges.maxThree")} eyebrow={t("adoption.journey.shortlist.eyebrow")} title={t("adoption.journey.shortlist.title")} />
    <div className="adoption-candidate-grid">
      {candidates.map((candidate) => <ChoiceButton className="adoption-candidate-card" key={candidate.candidateId} onClick={() => dispatch({ type: "toggle-candidate", candidateId: candidate.candidateId })} selected={selectedIds.includes(candidate.candidateId)}><img alt="" src={candidateImageUrl(candidate)} /><span className="adoption-candidate-card__copy"><strong>{candidate.originalName}</strong><small>{stageName(candidate.lifeStage)} · {t(`adoption.journey.genders.${candidate.gender}`)}</small><TagList values={candidate.appearanceTags.slice(0, 2)} /></span></ChoiceButton>)}
    </div>
    <div className="adoption-shortlist-toolbar">
      <span>{t("adoption.journey.shortlist.selected", { count: selectedIds.length })}</span>
      <div className="adoption-shortlist-toolbar__actions">
        <span>{t("adoption.journey.shortlist.batch", { current: candidateBatch, max: MAX_CANDIDATE_BATCHES })}</span>
        <Button disabled={!canRegenerate} onClick={onRegenerate} type="button" variant="outline">{canRegenerate ? t("adoption.journey.shortlist.regenerate") : t("adoption.journey.shortlist.batchComplete", { max: MAX_CANDIDATE_BATCHES })}</Button>
      </div>
    </div>
  </section>
}

function InvitingScreen({ candidates, t }: { readonly candidates: readonly Candidate[]; readonly t: JourneyT }) {
  return <section><ScreenIntro title={t("adoption.journey.inviting.title")} /><div className="adoption-signal" aria-hidden="true"><span /></div><div className="adoption-invite-grid">{candidates.map((candidate) => <div className="adoption-invite-card" key={candidate.candidateId}><img alt="" src={candidateImageUrl(candidate)} /><strong>{candidate.originalName}</strong></div>)}</div></section>
}

function ArrivalScreen({ candidate, name, onFinish, t }: { readonly candidate: CandidateReply; readonly name: string; readonly onFinish: () => void; readonly t: JourneyT }) {
  return <section className="adoption-arrival"><div className="adoption-arrival__portal"><img alt="" src={candidateImageUrl(candidate)} /></div><h2>{t("adoption.journey.arrival.title", { name })}</h2><Button onClick={onFinish} type="button">{t("adoption.journey.arrival.enter")}</Button></section>
}

function isNextDisabled(state: AdoptionDraftState, info: AdoptionInfo | null): boolean {
  if (state.screen === "basic") return state.draft.speciesId === null || info?.quota.can_adopt === false
  if (state.screen === "companionship") return state.draft.answers.some((answer) => answer === null)
  if (state.screen === "shortlist") return state.selectedCandidateIds.length === 0
  if (state.screen === "replies") return state.finalCandidateId === null
  if (state.screen === "naming") return state.nameMode === "custom" && !state.customName.trim()
  return false
}

function nextLabel(state: AdoptionDraftState, t: JourneyT): string {
  if (state.screen === "basic") return t("adoption.journey.actions.toAppearance")
  if (state.screen === "appearance") return t("adoption.journey.actions.toCompanionship")
  if (state.screen === "companionship") return t("adoption.journey.actions.nextPage")
  if (state.screen === "review") return t("adoption.journey.actions.generate")
  if (state.screen === "shortlist") return t("adoption.journey.actions.invite")
  if (state.screen === "replies") return t("adoption.journey.actions.toNaming")
  if (state.screen === "naming") return t("adoption.journey.actions.confirm")
  return t("adoption.journey.actions.continue")
}

function footerHint(state: AdoptionDraftState, t: JourneyT): string {
  if (state.screen === "shortlist") return t("adoption.journey.shortlist.selectionHint")
  if (state.screen === "replies") return t("adoption.journey.replies.selectionHint")
  if (state.screen === "naming") return t("adoption.journey.naming.selectionHint")
  return ""
}
