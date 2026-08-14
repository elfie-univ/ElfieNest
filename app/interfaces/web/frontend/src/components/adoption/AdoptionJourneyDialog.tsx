import { useEffect, useMemo, useReducer, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  adoptionCandidates,
  adoptionInfo,
  adoptionReplies,
  commitAdoption,
  type AdoptionCandidate,
  type AdoptionCandidateSet,
  type AdoptionCandidateSetInput,
  type AdoptionInfo,
  type AdoptionReply,
} from "../../api/me/adoption"
import { ApiError } from "../../api/http"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../../i18n/errors"
import { currentLocale } from "../../i18n/format"
import { ConfirmDialog } from "../ConfirmDialog"
import { Button } from "../ui/button"
import { Checkbox } from "../ui/checkbox"
import { Textarea } from "../ui/textarea"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../ui/alert-dialog"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog"
import { Icon } from "../Icon"
import dogAvatar from "../../assets/adoption/dog-model.png"
import elfariaArrivalImage from "../../assets/adoption/elfaria-arrival-square.png"
import foxAvatar from "../../assets/adoption/fox-model.png"
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
import {
  createProfileGodotPreview,
  ProfileGodotPreviewError,
  type ProfileGodotPreview,
} from "../elfie-profile/profile-godot-preview"

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
    const saved = parsed as Partial<AdoptionDraftState> & { readonly draft: Partial<AdoptionDraftState["draft"]> }
    return {
      ...INITIAL_ADOPTION_STATE,
      ...saved,
      draft: { ...DEFAULT_DRAFT, ...saved.draft },
      candidates: [],
      replies: [],
      finalCandidateId: null,
      candidateSetId: null,
      error: null,
    }
  } catch {
    return null
  }
}

function saveDraft(accountId: string, state: AdoptionDraftState): void {
  if (!state.dirty || state.screen === "arrival") return
  try {
    const hasRecoverableCandidates = state.candidateBatch > 0 && state.adoptionSessionId !== null
    const resumableScreen = hasRecoverableCandidates
      ? "shortlist"
      : ["basic", "appearance", "companionship", "review"].includes(state.screen)
        ? state.screen
        : "review"
    window.localStorage.setItem(draftStorageKey(accountId), JSON.stringify({
      ...state,
      screen: resumableScreen,
      candidates: [],
      replies: [],
      finalCandidateId: null,
      candidateSetId: null,
    }))
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
    speciesId: candidate.species_id,
    lifeStage: candidate.life_stage as LifeStage,
    ageMonths: candidate.age_months,
    gender: candidate.gender,
    fullBodyImageUrl: candidate.full_body_image_url,
    headshotImageUrl: candidate.headshot_image_url,
    appearanceTags: candidate.appearance_tags,
    personalityTags: candidate.personality_tags,
    runtimeAppearance: candidate.runtime_appearance ?? {},
  }
}

function asReply(reply: AdoptionReply, previous?: Candidate): CandidateReply {
  const mapped = asCandidate(reply)
  const candidate = previous === undefined
    ? mapped
    : {
        ...mapped,
        fullBodyImageUrl: mapped.fullBodyImageUrl || previous.fullBodyImageUrl,
        headshotImageUrl: mapped.headshotImageUrl || previous.headshotImageUrl,
        runtimeAppearance: Object.keys(mapped.runtimeAppearance).length > 0
          ? mapped.runtimeAppearance
          : previous.runtimeAppearance,
      }
  return { ...candidate, status: reply.status, message: reply.message, reveal: reply.reveal === null ? null : {
    originalName: reply.reveal.original_name,
    suggestedName: reply.reveal.suggested_name,
    personalStory: reply.reveal.personal_story,
  } }
}

function speciesImageUrl(speciesId: SpeciesId): string {
  return SPECIES_IMAGES[speciesId]
}

function candidateImageUrl(candidate: Pick<Candidate, "headshotImageUrl" | "fullBodyImageUrl" | "speciesId">, kind: "headshot" | "fullBody" = "headshot"): string {
  const imageUrl = kind === "fullBody" ? candidate.fullBodyImageUrl : candidate.headshotImageUrl
  return imageUrl || speciesImageUrl(candidate.speciesId)
}

function invitationMessageWithinLimit(value: string): boolean {
  const cjkCount = (value.match(/[\u3400-\u9fff]/g) ?? []).length
  const wordCount = value.trim() ? value.trim().split(/\s+/).length : 0
  return cjkCount > 0 ? cjkCount <= 50 && wordCount <= 50 : wordCount <= 50
}

function candidateSetInput(
  draft: AdoptionDraftState["draft"],
  batchNumber: number,
  adoptionSessionId: string | null = null,
): AdoptionCandidateSetInput {
  if (draft.speciesId === null) throw new Error("Adoption species is required")
  const answers = draft.answers.map((answer) => {
    if (answer === null) throw new Error("Every Adoption answer is required")
    return answer
  })
  return {
    species_id: draft.speciesId,
    life_stage: draft.lifeStage,
    gender: draft.gender,
    appearance: {
      stature: draft.stature,
      build: draft.build,
      face: draft.face,
      signature: draft.signature,
      priority: draft.priority,
    },
    answers,
    batch_number: batchNumber,
    ...(adoptionSessionId === null ? {} : { adoption_session_id: adoptionSessionId }),
  }
}

function candidateAgeLabel(t: JourneyT, ageMonths: number): string {
  const years = Math.floor(ageMonths / 12)
  const months = ageMonths % 12
  if (years === 0) return t("adoption.journey.shortlist.ageMonths", { count: months })
  if (months === 0) return t("adoption.journey.shortlist.ageYears", { count: years })
  return t("adoption.journey.shortlist.ageYearsMonths", { years, months })
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

type AdoptionEntryBlock = "nest-full" | "member-full" | "unavailable"

function AdoptionEntryCheck({ t }: { readonly t: JourneyT }) {
  return <section aria-live="polite" className="adoption-entry-check">
    <span aria-hidden="true" className="adoption-spinner" />
    <h2>{t("adoption.journey.entryCheck.title")}</h2>
    <p>{t("adoption.journey.entryCheck.description")}</p>
  </section>
}

function AdoptionEntryBlockDialog({
  block,
  onExit,
  onRetry,
  open,
  t,
}: {
  readonly block: AdoptionEntryBlock
  readonly onExit: () => void
  readonly onRetry: () => void
  readonly open: boolean
  readonly t: JourneyT
}) {
  const capacity = block !== "unavailable"
  const titleKey = block === "unavailable"
    ? "adoption.journey.entryBlock.unavailableTitle"
    : "adoption.journey.entryBlock.quotaTitle"
  const descriptionKey = block === "nest-full"
    ? "adoption.journey.entryBlock.nestQuotaDescription"
    : block === "member-full"
      ? "adoption.journey.entryBlock.memberQuotaDescription"
      : "adoption.journey.entryBlock.unavailableDescription"
  return <AlertDialog onOpenChange={(nextOpen) => { if (!nextOpen) onExit() }} open={open}>
    <AlertDialogContent className="adoption-entry-block-dialog">
      <AlertDialogHeader>
        <AlertDialogTitle>{t(titleKey)}</AlertDialogTitle>
        <AlertDialogDescription>{t(descriptionKey)}</AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        {capacity ? <AlertDialogAction onClick={onExit}>{t("adoption.journey.entryBlock.dismiss")}</AlertDialogAction> : <>
          <AlertDialogCancel>{t("adoption.journey.entryBlock.exit")}</AlertDialogCancel>
          <AlertDialogAction onClick={(event) => { event.preventDefault(); onRetry() }}>{t("adoption.journey.entryBlock.retry")}</AlertDialogAction>
        </>}
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
}

export function AdoptionJourneyDialog({ accountId, csrfToken, open, onAdopted, onOpenChange }: AdoptionJourneyDialogProps) {
  const { i18n, t } = useTranslation("chat")
  const locale = currentLocale(i18n)
  const [state, dispatch] = useReducer(adoptionReducer, INITIAL_ADOPTION_STATE)
  const [info, setInfo] = useState<AdoptionInfo | null>(null)
  const [loadingInfo, setLoadingInfo] = useState(false)
  const [entryRequest, setEntryRequest] = useState(0)
  const [entryBlock, setEntryBlock] = useState<AdoptionEntryBlock | null>(null)
  const [closePrompt, setClosePrompt] = useState(false)
  const [intentConfirmOpen, setIntentConfirmOpen] = useState(false)
  const [finalConfirmOpen, setFinalConfirmOpen] = useState(false)
  const [invitationFailureOpen, setInvitationFailureOpen] = useState(false)
  const [messageDialogOpen, setMessageDialogOpen] = useState(false)
  const [messageDraft, setMessageDraft] = useState("")
  const [generationRequest, setGenerationRequest] = useState<AdoptionCandidateSetInput | null>(null)
  const [sendingInvitations, setSendingInvitations] = useState(false)
  const [apiError, setApiError] = useState<LocalizedErrorState>(null)
  const retryingInvitationRef = useRef(false)
  const isBusy = state.screen === "generating" || state.screen === "committing" || sendingInvitations
  const isIntentLocked = !["welcome", "basic", "appearance", "companionship", "review"].includes(state.screen)

  useEffect(() => {
    if (!open) {
      setInfo(null)
      setEntryBlock(null)
      setLoadingInfo(false)
      return
    }
    let active = true
    const saved = readDraft(accountId)
    if (saved?.dirty && saved.screen !== "arrival") {
      dispatch({ type: "restore", state: saved })
    } else {
      dispatch({ type: "reset", screen: hasSkippedWelcome(accountId) ? "basic" : "welcome" })
    }
    setInfo(null)
    setLoadingInfo(true)
    setApiError(null)
    setEntryBlock(null)
    setInvitationFailureOpen(false)
    retryingInvitationRef.current = false
    void adoptionInfo()
      .then((nextInfo) => {
        if (!active) return
        setInfo(nextInfo)
        if (nextInfo.availability === "nest_full") setEntryBlock("nest-full")
        else if (nextInfo.availability === "member_quota_full") setEntryBlock("member-full")
        else if (nextInfo.availability === "model_unavailable") setEntryBlock("unavailable")
        else if (
          saved?.dirty
          && saved.screen === "shortlist"
          && saved.adoptionSessionId !== null
          && saved.candidateBatch > 0
          && intentComplete(saved.draft)
        ) {
          setGenerationRequest(candidateSetInput(
            saved.draft,
            saved.candidateBatch,
            saved.adoptionSessionId,
          ))
          dispatch({ type: "screen", screen: "generating" })
        }
      })
      .catch((reason: unknown) => {
        if (!active) return
        setApiError(describeApiError(reason, "manage.load"))
        setEntryBlock("unavailable")
      })
      .finally(() => { if (active) setLoadingInfo(false) })
    return () => { active = false }
  }, [accountId, entryRequest, open])

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

  const generateCandidates = (): void => {
    if (!intentComplete(state.draft)) {
      dispatch({ type: "error", message: t("adoption.journey.validation.completeIntent") })
      return
    }
    const batch = state.candidateBatch + 1
    if (batch > MAX_CANDIDATE_BATCHES) return
    const request = candidateSetInput(state.draft, batch, state.adoptionSessionId)
    setApiError(null)
    setGenerationRequest(request)
    dispatch({ type: "screen", screen: "generating" })
  }

  const sendInvitations = async (): Promise<void> => {
    if (state.candidateSetId === null || state.selectedCandidateIds.length === 0) {
      dispatch({ type: "error", message: t("adoption.journey.validation.chooseCandidate") })
      return
    }
    if (sendingInvitations) return
    setApiError(null)
    setMessageDialogOpen(false)
    setInvitationFailureOpen(false)
    setSendingInvitations(true)
    dispatch({ type: "screen", screen: "inviting" })
    try {
      let candidateSetId = state.candidateSetId
      let result: Awaited<ReturnType<typeof adoptionReplies>> | null = null
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          result = await adoptionReplies(candidateSetId, state.selectedCandidateIds, state.invitationMessageEnabled ? state.invitationMessage : "", csrfToken)
          break
        } catch (reason: unknown) {
          const canRecover = attempt === 0
            && reason instanceof ApiError
            && reason.code === "adoption_candidate_set_expired"
            && state.adoptionSessionId !== null
            && state.candidateBatch > 0
          if (!canRecover) throw reason
          const recovered = await adoptionCandidates(
            candidateSetInput(state.draft, state.candidateBatch, state.adoptionSessionId),
            csrfToken,
          )
          const currentIds = state.candidates.map((candidate) => candidate.candidateId)
          const recoveredIds = recovered.candidates.map((candidate) => candidate.candidate_id)
          const sameCandidates = currentIds.length === recoveredIds.length
            && currentIds.every((candidateId, index) => candidateId === recoveredIds[index])
          if (
            recovered.adoption_session_id !== state.adoptionSessionId
            || recovered.batch_number !== state.candidateBatch
            || !sameCandidates
          ) {
            throw reason
          }
          candidateSetId = recovered.candidate_set_id
          dispatch({ type: "candidate-set-recovered", setId: candidateSetId })
        }
      }
      if (result === null) throw new Error("Invitation reply result is missing")
      const previous = new Map(state.candidates.map((candidate) => [candidate.candidateId, candidate]))
      dispatch({ type: "replies-ready", replies: result.replies.map((reply) => asReply(reply, previous.get(reply.candidate_id))) })
    } catch {
      setInvitationFailureOpen(true)
    } finally {
      setSendingInvitations(false)
    }
  }

  const openMessageEditor = (): void => {
    if (state.candidateSetId === null || state.selectedCandidateIds.length === 0) {
      dispatch({ type: "error", message: t("adoption.journey.validation.chooseCandidate") })
      return
    }
    setMessageDraft(state.invitationMessage)
    setMessageDialogOpen(true)
  }

  const saveInvitationMessage = (): void => {
    const message = messageDraft.trim()
    if (message.length === 0) {
      dispatch({ type: "invitation-message-enabled", value: false })
    } else {
      dispatch({ type: "invitation-message", value: message })
    }
    setMessageDialogOpen(false)
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
    dispatch({ type: "screen", screen: "committing" })
    try {
      const finalCandidate = state.replies.find((candidate) => candidate.candidateId === state.finalCandidateId)
      const result = await commitAdoption(state.candidateSetId, state.finalCandidateId, name, csrfToken, {
        ...(finalCandidate?.fullBodyImageUrl ? { fullBodyImageUrl: finalCandidate.fullBodyImageUrl } : {}),
        ...(finalCandidate?.headshotImageUrl ? { headshotImageUrl: finalCandidate.headshotImageUrl } : {}),
      })
      clearDraft(accountId)
      await onAdopted(result.elfie_id)
      dispatch({ type: "screen", screen: "arrival" })
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.code === "nest_capacity_reached") {
        dispatch({ type: "screen", screen: "shortlist" })
        setEntryBlock("nest-full")
        return
      }
      if (reason instanceof ApiError && reason.code === "elfie_capacity_reached") {
        dispatch({ type: "screen", screen: "shortlist" })
        setEntryBlock("member-full")
        return
      }
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
  const journeyReady = info !== null && !loadingInfo && entryBlock === null
  const entryChecking = open && (loadingInfo || (info === null && entryBlock === null))
  const title = !journeyReady
    ? t("adoption.journey.entryCheck.title")
    : state.screen === "welcome"
      ? t("adoption.journey.window.welcomeTitle")
      : t("adoption.journey.window.title")
  const stage = STAGE_FOR_SCREEN[state.screen]
  const showFooter = journeyReady && !["welcome", "generating", "inviting", "committing", "arrival"].includes(state.screen)
  const showBack = state.screen === "naming" || (!isIntentLocked && state.screen !== "basic")
  const onGenerationReady = (result: AdoptionCandidateSet, candidates: readonly Candidate[]): void => {
    setGenerationRequest(null)
    dispatch({
      type: "candidates-ready",
      batch: result.batch_number,
      setId: result.candidate_set_id,
      sessionId: result.adoption_session_id,
      candidates,
      selectedIds: state.selectedCandidateIds,
    })
  }
  const onGenerationError = (reason: unknown): void => {
    setGenerationRequest(null)
    void reason
    dispatch({ type: "error", message: t("adoption.journey.errors.generate") })
  }

  const candidateLabel = (candidateId: string): string => {
    const index = state.candidates.findIndex((candidate) => candidate.candidateId === candidateId)
    return t("adoption.journey.shortlist.candidate", { number: index >= 0 ? index + 1 : "" })
  }

  const exitEntryBlock = (): void => {
    setEntryBlock(null)
    onOpenChange(false)
  }

  const retryEntryCheck = (): void => {
    setEntryBlock(null)
    setInfo(null)
    setLoadingInfo(true)
    setEntryRequest((value) => value + 1)
  }

  const retryInvitation = (): void => {
    retryingInvitationRef.current = true
    setInvitationFailureOpen(false)
    void sendInvitations()
  }

  const invitationFailureTitle = t("adoption.journey.invitationFailure.title")
  const invitationFailureDescription = t("adoption.journey.invitationFailure.description")

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

        {journeyReady && state.screen !== "welcome" && state.screen !== "arrival" ? (
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
          {journeyReady && state.error ? <p className="adoption-inline-error" role="alert">{state.error}</p> : null}
          {journeyReady && errorMessage ? <p className="adoption-inline-error" role="alert">{errorMessage}</p> : null}
          {entryChecking ? <AdoptionEntryCheck t={t} /> : null}
          {journeyReady && state.screen === "welcome" ? <WelcomeScreen t={t} onStart={goToBasic} /> : null}
          {journeyReady && state.screen === "basic" ? <BasicScreen allowedSpecies={allowedSpecies} canAdopt={info?.quota.can_adopt ?? true} draft={state.draft} dispatch={dispatch} speciesName={(id) => speciesName(t, id)} stageName={(value) => stageName(t, value)} t={t} /> : null}
          {journeyReady && state.screen === "appearance" ? <AppearanceScreen draft={state.draft} dispatch={dispatch} t={t} /> : null}
          {journeyReady && state.screen === "companionship" ? <CompanionshipScreen draft={state.draft} dispatch={dispatch} onAnswer={answerCompanionship} questionIndex={state.questionIndex} t={t} /> : null}
          {journeyReady && state.screen === "review" ? <ReviewScreen draft={state.draft} dispatch={dispatch} stageName={(value) => stageName(t, value)} speciesName={(id) => speciesName(t, id)} t={t} /> : null}
          {journeyReady && state.screen === "generating" && generationRequest !== null ? <GeneratingScreen csrfToken={csrfToken} onError={onGenerationError} onReady={onGenerationReady} request={generationRequest} title={t("adoption.journey.generating.title")} /> : null}
          {journeyReady && state.screen === "shortlist" ? <ShortlistScreen candidates={state.candidates} candidateBatch={state.candidateBatch} dispatch={dispatch} onRegenerate={() => { void generateCandidates() }} selectedIds={state.selectedCandidateIds} t={t} /> : null}
          {journeyReady && state.screen === "inviting" ? <SendingScreen candidates={state.candidates.filter((candidate) => state.selectedCandidateIds.includes(candidate.candidateId))} candidateLabel={candidateLabel} t={t} /> : null}
          {journeyReady && state.screen === "replies" ? <RepliesScreen candidateImageUrl={candidateImageUrl} candidateLabel={candidateLabel} dispatch={dispatch} finalCandidateId={state.finalCandidateId} intro={<ScreenIntro title={t("adoption.journey.replies.title", { count: state.replies.filter((reply) => reply.status === "accepted").length })} />} replies={state.replies} t={t} /> : null}
          {journeyReady && state.screen === "naming" && selectedCandidate ? <NamingScreen candidate={selectedCandidate} candidateImageUrl={candidateImageUrl} candidateLabel={candidateLabel(selectedCandidate.candidateId)} customName={state.customName} dispatch={dispatch} intro={<ScreenIntro title={t("adoption.journey.naming.title")} />} nameMode={state.nameMode} t={t} /> : null}
          {journeyReady && state.screen === "committing" ? <ProgressScreen title={t("adoption.journey.committing.title", { name: selectedName(state) })} /> : null}
          {journeyReady && state.screen === "arrival" && selectedCandidate ? <ArrivalScreen candidate={selectedCandidate} name={selectedName(state)} onFinish={() => { onOpenChange(false) }} t={t} /> : null}
        </div>

        {showFooter ? (
          <footer className="adoption-dialog__footer">
            {showBack ? <Button onClick={back} type="button" variant="ghost">{t("adoption.journey.actions.back")}</Button> : null}
            <div>
              <span className="adoption-footer-hint">{footerHint(state, t)}</span>
              {state.screen === "shortlist" ? <Button onClick={openMessageEditor} type="button" variant="outline">{state.invitationMessageEnabled ? t("adoption.journey.inviting.editMessage") : t("adoption.journey.inviting.writeMessage")}</Button> : null}
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
        <ConfirmDialog
          cancelLabel={t("adoption.journey.invitationFailure.exit")}
          confirmLabel={t("adoption.journey.invitationFailure.retry")}
          description={invitationFailureDescription}
          onConfirm={retryInvitation}
          onOpenChange={(nextOpen) => {
            setInvitationFailureOpen(nextOpen)
            if (nextOpen) return
            if (retryingInvitationRef.current) {
              retryingInvitationRef.current = false
              return
            }
            onOpenChange(false)
          }}
          open={invitationFailureOpen}
          title={invitationFailureTitle}
        />

        {entryBlock !== null ? <AdoptionEntryBlockDialog block={entryBlock} onExit={exitEntryBlock} onRetry={retryEntryCheck} open t={t} /> : null}

        {closePrompt ? (
          <div aria-labelledby="adoption-close-title" aria-modal="true" className="adoption-close-prompt" role="alertdialog">
            <div className="adoption-close-prompt__card">
              <h2 id="adoption-close-title">{t("adoption.journey.closePrompt.title")}</h2>
              <p>{t("adoption.journey.closePrompt.description")}</p>
              <div><Button onClick={() => setClosePrompt(false)} type="button" variant="ghost">{t("adoption.journey.closePrompt.continue")}</Button><Button onClick={confirmDiscard} type="button" variant="destructive">{t("adoption.journey.closePrompt.discard")}</Button></div>
            </div>
          </div>
        ) : null}

        {messageDialogOpen ? (
          <div aria-labelledby="adoption-message-title" aria-modal="true" className="adoption-message-prompt" role="dialog">
            <div className="adoption-message-prompt__card">
              <div className="adoption-message-prompt__header">
                <h2 id="adoption-message-title">{t("adoption.journey.inviting.messageTitle")}</h2>
                <Button aria-label={t("adoption.close")} onClick={() => setMessageDialogOpen(false)} size="icon-sm" type="button" variant="ghost"><Icon name="x" /></Button>
              </div>
              <Textarea aria-label={t("adoption.journey.inviting.messageLabel")} maxLength={400} onChange={(event) => { if (invitationMessageWithinLimit(event.target.value)) setMessageDraft(event.target.value) }} placeholder={t("adoption.journey.inviting.messagePlaceholder")} value={messageDraft} />
              <p className="adoption-message-prompt__hint">{t("adoption.journey.inviting.messageLimit")}</p>
              <div className="adoption-message-prompt__actions">
                <Button onClick={() => setMessageDialogOpen(false)} type="button" variant="ghost">{t("adoption.journey.inviting.cancelMessage")}</Button>
                <Button onClick={saveInvitationMessage} type="button">{t("adoption.journey.inviting.saveMessage")}</Button>
              </div>
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

function ProgressScreen({ title }: { readonly title: string }) {
  return <section className="adoption-progress-screen"><h2>{title}</h2><div aria-label={title} className="adoption-signal adoption-progress-signal" role="progressbar"><span /></div></section>
}

type GeneratingScreenProps = {
  readonly csrfToken: string
  readonly onError: (reason: unknown) => void
  readonly onReady: (result: AdoptionCandidateSet, candidates: readonly Candidate[]) => void
  readonly request: AdoptionCandidateSetInput
  readonly title: string
}

function GeneratingScreen({ csrfToken, onError, onReady, request, title }: GeneratingScreenProps) {
  const frameRef = useRef<HTMLIFrameElement>(null)

  useEffect(() => {
    let active = true
    let readyResolve: (() => void) | null = null
    const ready = new Promise<void>((resolve) => {
      readyResolve = resolve
    })
    const pendingActions = new Map<string, { readonly resolve: () => void; readonly reject: (reason: unknown) => void }>()
    const frame = frameRef.current
    if (frame === null) return undefined

    let bridge: ProfileGodotPreview | null = null
    const waitForAction = (action: string): Promise<void> => new Promise<void>((resolve, reject) => {
      pendingActions.set(action, { resolve, reject })
    })
    bridge = createProfileGodotPreview({
      frame,
      onEvent: (event) => {
        if (event.kind === "ready") {
          readyResolve?.()
          return
        }
        const pending = pendingActions.get(event.action)
        if (pending === undefined) return
        pendingActions.delete(event.action)
        if (event.kind === "completed") pending.resolve()
        else pending.reject(new ProfileGodotPreviewError(event.reason))
      },
    })

    const run = async (): Promise<void> => {
      try {
        const result = await adoptionCandidates(request, csrfToken)
        if (!active) return
        const candidates = result.candidates.map(asCandidate)
        if (candidates.some((candidate) => Object.keys(candidate.runtimeAppearance).length === 0)) {
          const hasStaticPortraits = candidates.every((candidate) => candidate.fullBodyImageUrl.length > 0 && candidate.headshotImageUrl.length > 0)
          if (hasStaticPortraits) onReady(result, candidates)
          else onError(new ProfileGodotPreviewError("candidate_portrait_unavailable"))
          return
        }
        await waitWithTimeout(ready, 20_000, "preview_timeout")
        const rendered: Candidate[] = []
        for (const candidate of candidates) {
          if (!active || bridge === null) return
          await sendAndWait(bridge, waitForAction, "configure", {
            appearance: candidate.runtimeAppearance,
            elfie_id: `candidate-${candidate.candidateId}`,
            spec_revision: portraitRevision(candidate.candidateId),
            species_id: candidate.speciesId,
          })
          const fullBody = await captureAndWait(bridge, waitForAction)
          await sendAndWait(bridge, waitForAction, "focus", { target: "head" })
          const headshot = await captureAndWait(bridge, waitForAction)
          const fullBodyImageUrl = await captureDataUrl(fullBody)
          const headshotImageUrl = await captureDataUrl(headshot)
          URL.revokeObjectURL(fullBody.previewUrl)
          URL.revokeObjectURL(headshot.previewUrl)
          rendered.push({ ...candidate, fullBodyImageUrl, headshotImageUrl })
        }
        if (active) onReady(result, rendered)
      } catch (reason: unknown) {
        if (active) onError(reason)
      }
    }
    void run()
    return () => {
      active = false
      for (const pending of pendingActions.values()) pending.reject(new ProfileGodotPreviewError("preview_closed"))
      pendingActions.clear()
      bridge?.dispose()
    }
  }, [csrfToken, onError, onReady, request])

  return <section className="adoption-progress-screen">
    <h2>{title}</h2>
    <div aria-label={title} className="adoption-signal adoption-progress-signal" role="progressbar"><span /></div>
    <iframe
      aria-hidden="true"
      className="adoption-portrait-renderer"
      onError={() => onError(new ProfileGodotPreviewError("preview_load_failed"))}
      ref={frameRef}
      src="/runtime/godot/elfienest.html?mode=elfie_lab"
      title=""
    />
  </section>
}

async function sendAndWait(
  bridge: ProfileGodotPreview,
  waitForAction: (action: string) => Promise<void>,
  action: string,
  payload: Readonly<Record<string, unknown>>,
): Promise<void> {
  const completion = waitForAction(action)
  bridge.send(action, payload)
  await completion
}

async function captureAndWait(
  bridge: ProfileGodotPreview,
  waitForAction: (action: string) => Promise<void>,
): Promise<{ readonly blob: Blob; readonly previewUrl: string }> {
  const completion = waitForAction("capture")
  const capture = bridge.capture()
  await completion
  return capture
}

async function captureDataUrl(capture: { readonly blob: Blob }): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === "string") resolve(reader.result)
      else reject(new ProfileGodotPreviewError("invalid_portrait"))
    }
    reader.onerror = () => reject(new ProfileGodotPreviewError("invalid_portrait"))
    reader.readAsDataURL(capture.blob)
  })
}

function portraitRevision(candidateId: string): number {
  let hash = 2166136261
  for (const character of candidateId) {
    hash ^= character.charCodeAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

async function waitWithTimeout<T>(promise: Promise<T>, milliseconds: number, reason: string): Promise<T> {
  let timer: number | undefined
  try {
    return await Promise.race([
      promise,
      new Promise<T>((_, reject) => {
        timer = window.setTimeout(() => reject(new ProfileGodotPreviewError(reason)), milliseconds)
      }),
    ])
  } finally {
    if (timer !== undefined) window.clearTimeout(timer)
  }
}

function ShortlistScreen({ candidates, candidateBatch, dispatch, onRegenerate, selectedIds, t }: { readonly candidates: readonly Candidate[]; readonly candidateBatch: number; readonly dispatch: React.Dispatch<AdoptionAction>; readonly onRegenerate: () => void; readonly selectedIds: readonly string[]; readonly t: JourneyT }) {
  const canRegenerate = candidateBatch < MAX_CANDIDATE_BATCHES
  return <section>
    <ScreenIntro badge={t("adoption.journey.badges.maxThree")} eyebrow={t("adoption.journey.shortlist.eyebrow")} title={t("adoption.journey.shortlist.title")} />
    <div className="adoption-candidate-grid">
      {candidates.map((candidate, index) => {
        const selected = selectedIds.includes(candidate.candidateId)
        const disabled = !selected && selectedIds.length >= 3
        return <ChoiceButton aria-label={t("adoption.journey.shortlist.candidate", { number: index + 1 })} className="adoption-candidate-card" disabled={disabled} key={candidate.candidateId} onClick={() => dispatch({ type: "toggle-candidate", candidateId: candidate.candidateId })} selected={selected}><img alt="" src={candidateImageUrl(candidate, "fullBody")} /><span className="adoption-candidate-card__copy"><strong>{t("adoption.journey.shortlist.candidate", { number: index + 1 })}</strong><small>{candidateAgeLabel(t, candidate.ageMonths)} · {t(`adoption.journey.genders.${candidate.gender}`)}</small><TagList values={candidate.personalityTags.slice(0, 3)} /></span></ChoiceButton>
      })}
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

function SendingScreen({ candidates, candidateLabel, t }: { readonly candidates: readonly Candidate[]; readonly candidateLabel: (candidateId: string) => string; readonly t: JourneyT }) {
  return <section className="adoption-sending-screen"><ScreenIntro title={t("adoption.journey.inviting.title")} /><div className="adoption-invite-grid">{candidates.map((candidate) => <div className="adoption-invite-card" key={candidate.candidateId}><img alt="" src={candidateImageUrl(candidate, "headshot")} /><strong>{candidateLabel(candidate.candidateId)}</strong><TagList values={candidate.personalityTags.slice(0, 3)} /></div>)}</div><div aria-label={t("adoption.journey.inviting.title")} className="adoption-signal adoption-progress-signal" role="progressbar"><span /></div></section>
}

function ArrivalScreen({ candidate, name, onFinish, t }: { readonly candidate: CandidateReply; readonly name: string; readonly onFinish: () => void; readonly t: JourneyT }) {
  return <section className="adoption-arrival"><div className="adoption-arrival__portal"><img alt="" src={candidateImageUrl(candidate)} /></div><h2>{t("adoption.journey.arrival.title", { name })}</h2><Button onClick={onFinish} type="button">{t("adoption.journey.arrival.enter")}</Button></section>
}

function isNextDisabled(state: AdoptionDraftState, info: AdoptionInfo | null): boolean {
  if (state.screen === "basic") return state.draft.speciesId === null || info?.availability !== "available"
  if (state.screen === "companionship") return state.draft.answers.some((answer) => answer === null)
  if (state.screen === "shortlist") return state.selectedCandidateIds.length === 0
  if (state.screen === "replies") return state.finalCandidateId === null
  if (state.screen === "naming") {
    const candidate = state.replies.find((item) => item.candidateId === state.finalCandidateId)
    if (candidate?.reveal === null) return !state.customName.trim()
    return state.nameMode === "custom" && !state.customName.trim()
  }
  return false
}

function nextLabel(state: AdoptionDraftState, t: JourneyT): string {
  if (state.screen === "basic") return t("adoption.journey.actions.toAppearance")
  if (state.screen === "appearance") return t("adoption.journey.actions.toCompanionship")
  if (state.screen === "companionship") return t("adoption.journey.actions.nextPage")
  if (state.screen === "review") return t("adoption.journey.actions.generate")
  if (state.screen === "shortlist") return t("adoption.journey.actions.sendIntent")
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
