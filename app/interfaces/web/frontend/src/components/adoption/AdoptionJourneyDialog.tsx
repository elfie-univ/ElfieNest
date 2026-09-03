import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type RefObject } from "react"
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
import {
  AlertDialog,
  AlertDialogAction,
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
import elfariaArrivalImage from "../../assets/adoption/elfaria-arrival-square.png"
import {
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
import {
  adoptionSessionExpiryFromNow,
  clearAdoptionDraft,
  loadAdoptionDraft,
  saveAdoptionDraft,
} from "./adoption-storage"
import { ArrivalWelcomeScreen } from "./AdoptionReplyScreens"
import {
  calculateVisibleFrameBounds,
  createProfileGodotPreview,
  measureVisibleFrame,
  ProfileGodotPreviewError,
  toGodotVisibleFrameMetrics,
  type ProfileGodotPreview,
  type VisibleFrameBounds,
} from "../elfie-profile/profile-godot-preview"

type AdoptionJourneyDialogProps = {
  readonly accountId: string
  readonly csrfToken: string
  readonly open: boolean
  readonly onAdopted: (elfieId: string) => Promise<void>
  readonly onOpenChange: (open: boolean) => void
  readonly onRefreshCsrfToken: () => Promise<string>
}

type JourneyT = (key: string, options?: Record<string, unknown>) => string

const LIFE_STAGES: readonly LifeStage[] = ["youth", "young_adult", "mature", "elder", "any"]
const GENDERS: readonly GenderPreference[] = ["male", "female", "any"]
const APPEARANCE_GROUPS = ["stature", "build", "face", "signature"] as const
const COMPANIONSHIP_OPTIONS: readonly (readonly CompanionAnswer[])[] = [
  ["approach", "quiet", "independent", "any"],
  ["explore", "research", "observe", "any"],
  ["adapt", "plan", "comfort", "any"],
  ["direct", "discuss", "pause", "any"],
  ["lively", "steady", "space", "any"],
]
const PORTRAIT_RUNTIME_IDLE_MILLISECONDS = 5 * 60 * 1000
const PORTRAIT_RUNTIME_SCREENS: readonly AdoptionScreen[] = ["basic", "appearance", "companionship", "generating"]
const INVITATION_RETRY_DELAYS_MILLISECONDS = [400, 1000] as const
const INVITATION_TIMEOUT_MILLISECONDS = 30_000
const WAIT_STATUS_SECOND_PHASE_MILLISECONDS = 4_000
const WAIT_STATUS_FINAL_PHASE_MILLISECONDS = 10_000
const WAIT_STATUS_KEYS = ["initial", "continuing", "delayed"] as const

function isExpiredSessionError(reason: unknown): boolean {
  return reason instanceof ApiError && reason.code === "adoption_candidate_set_expired"
}

const STAGE_FOR_SCREEN: Partial<Record<AdoptionScreen, number>> = {
  basic: 0,
  appearance: 0,
  companionship: 0,
  review: 0,
  generating: 1,
  shortlist: 1,
  inviting: 2,
  replies: 2,
  naming: 2,
  committing: 2,
  arrival: 2,
}

function welcomeStorageKey(accountId: string): string {
  return `elfienest.adoption-welcome.${accountId}.v1`
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

function asCandidate(candidate: AdoptionCandidate): Candidate {
  return {
    candidateId: candidate.candidate_id,
    speciesId: candidate.species_id,
    lifeStage: candidate.life_stage as LifeStage,
    ageYears: candidate.age_years,
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
  return { ...candidate, status: reply.status, message: reply.message }
}

function candidateImageUrl(candidate: Pick<Candidate, "headshotImageUrl" | "fullBodyImageUrl">, kind: "headshot" | "fullBody" = "headshot"): string {
  if (kind === "fullBody") return candidate.fullBodyImageUrl
  return candidate.headshotImageUrl || candidate.fullBodyImageUrl
}

class InvitationReplyTimeoutError extends Error {
  public readonly name = "InvitationReplyTimeoutError"
}

function isInvitationChannelFailure(reason: unknown): boolean {
  if (reason instanceof InvitationReplyTimeoutError) return true
  if (reason instanceof ApiError) return reason.status >= 500
  if (reason instanceof Error && reason.name === "TimeoutError") return true
  if (reason instanceof DOMException && reason.name === "NetworkError") return true
  return reason instanceof TypeError
    && /failed to fetch|network|load failed/i.test(reason.message)
}

function isRetryableInvitationFailure(reason: unknown): boolean {
  return reason instanceof ApiError && reason.status >= 500
}

function waitMilliseconds(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

async function waitForInvitationReply<T>(promise: Promise<T>, milliseconds: number): Promise<T> {
  let timer: number | undefined
  try {
    return await Promise.race([
      promise,
      new Promise<T>((_, reject) => {
        timer = window.setTimeout(() => reject(new InvitationReplyTimeoutError("Invitation reply timed out")), milliseconds)
      }),
    ])
  } finally {
    if (timer !== undefined) window.clearTimeout(timer)
  }
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

function candidateAgeLabel(t: JourneyT, ageYears: number): string {
  return t("adoption.journey.shortlist.ageYears", { count: ageYears })
}

function speciesName(
  speciesId: SpeciesId,
  species: AdoptionInfo["species"][number] | undefined,
  locale: string,
): string {
  if (species !== undefined) {
    return locale === "zh-CN" ? species.display_name_zh : species.display_name
  }
  return speciesId
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
  open,
  t,
}: {
  readonly block: AdoptionEntryBlock
  readonly onExit: () => void
  readonly open: boolean
  readonly t: JourneyT
}) {
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
        <AlertDialogAction onClick={onExit}>{t("adoption.journey.entryBlock.dismiss")}</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
}

export function AdoptionJourneyDialog({ accountId, csrfToken, open, onAdopted, onOpenChange, onRefreshCsrfToken }: AdoptionJourneyDialogProps) {
  const { i18n, t } = useTranslation("chat")
  const locale = currentLocale(i18n)
  const [state, dispatch] = useReducer(adoptionReducer, INITIAL_ADOPTION_STATE)
  const [info, setInfo] = useState<AdoptionInfo | null>(null)
  const [loadingInfo, setLoadingInfo] = useState(false)
  const [entryBlock, setEntryBlock] = useState<AdoptionEntryBlock | null>(null)
  const [closePrompt, setClosePrompt] = useState(false)
  const [invitationFailureOpen, setInvitationFailureOpen] = useState(false)
  const [candidateRecoveryNotice, setCandidateRecoveryNotice] = useState(false)
  const [generationRequest, setGenerationRequest] = useState<AdoptionCandidateSetInput | null>(null)
  const [sendingInvitations, setSendingInvitations] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [apiError, setApiError] = useState<LocalizedErrorState>(null)
  const csrfTokenRef = useRef(csrfToken)
  const retryingInvitationRef = useRef(false)
  const portraitFrameRef = useRef<HTMLIFrameElement>(null)
  const portraitRuntimeTimerRef = useRef<number | null>(null)
  const portraitLastActivityAtRef = useRef(0)
  const [portraitRuntimeEnabled, setPortraitRuntimeEnabled] = useState(false)
  const [portraitRuntimeBlocked, setPortraitRuntimeBlocked] = useState(false)
  const [portraitRuntimeGeneration, setPortraitRuntimeGeneration] = useState(0)
  const sessionExpiresAtRef = useRef<number | null>(null)
  const isBusy = state.screen === "generating" || state.screen === "inviting" || state.screen === "committing" || sendingInvitations || committing
  const isIntentLocked = !["welcome", "basic", "appearance", "companionship"].includes(state.screen)

  useEffect(() => {
    csrfTokenRef.current = csrfToken
  }, [csrfToken])

  const withCsrfRetry = useCallback(async <Result,>(request: (token: string) => Promise<Result>): Promise<Result> => {
    try {
      return await request(csrfTokenRef.current)
    } catch (reason: unknown) {
      if (!(reason instanceof ApiError) || reason.code !== "csrf_rejected") throw reason
      let refreshedToken = ""
      try {
        refreshedToken = await onRefreshCsrfToken()
      } catch {
        throw reason
      }
      if (refreshedToken === "") throw reason
      csrfTokenRef.current = refreshedToken
      return request(refreshedToken)
    }
  }, [onRefreshCsrfToken])

  const loadCandidates = useCallback((request: AdoptionCandidateSetInput): Promise<AdoptionCandidateSet> => (
    withCsrfRetry((token) => adoptionCandidates(request, token))
  ), [withCsrfRetry])

  const handleExpiredSession = useCallback((draft: AdoptionDraftState["draft"]): void => {
    const canRegenerate = intentComplete(draft)
    sessionExpiresAtRef.current = canRegenerate ? adoptionSessionExpiryFromNow() : null
    void clearAdoptionDraft(accountId)
    setGenerationRequest(canRegenerate ? candidateSetInput(draft, 1) : null)
    setSendingInvitations(false)
    setCommitting(false)
    setInvitationFailureOpen(false)
    setApiError(null)
    setPortraitRuntimeEnabled(false)
    setPortraitRuntimeBlocked(!canRegenerate)
    setPortraitRuntimeGeneration((generation) => generation + 1)
    setCandidateRecoveryNotice(canRegenerate)
    if (canRegenerate) {
      dispatch({ type: "restart-candidates" })
      return
    }
    dispatch({ type: "reset", screen: "basic" })
    dispatch({ type: "error", message: t("adoption.journey.errors.expired") })
  }, [accountId, t])

  useEffect(() => {
    if (!open) {
      setInfo(null)
      setEntryBlock(null)
      setLoadingInfo(false)
      setCommitting(false)
      setCandidateRecoveryNotice(false)
      setPortraitRuntimeBlocked(false)
      portraitLastActivityAtRef.current = Date.now()
      sessionExpiresAtRef.current = null
      return
    }
    let active = true
    setInfo(null)
    setLoadingInfo(true)
    setApiError(null)
    setEntryBlock(null)
    setPortraitRuntimeBlocked(false)
    portraitLastActivityAtRef.current = Date.now()
    setInvitationFailureOpen(false)
    retryingInvitationRef.current = false
    void (async () => {
      try {
        const loaded = await loadAdoptionDraft(accountId)
        if (!active) return
        sessionExpiresAtRef.current = loaded.sessionExpiresAt
        if (loaded.expired) {
          handleExpiredSession(loaded.state?.draft ?? INITIAL_ADOPTION_STATE.draft)
        } else if (loaded.state?.dirty && loaded.state.screen !== "arrival") {
          dispatch({ type: "restore", state: loaded.state })
        } else {
          dispatch({ type: "reset", screen: hasSkippedWelcome(accountId) ? "basic" : "welcome" })
        }

        const nextInfo = await adoptionInfo()
        if (!active) return
        setInfo(nextInfo)
        if (nextInfo.availability === "nest_full") setEntryBlock("nest-full")
        else if (nextInfo.availability === "member_quota_full") setEntryBlock("member-full")
        else if (nextInfo.availability === "species_unavailable") setEntryBlock("unavailable")

        const saved = loaded.state
        if (
          !loaded.expired
          && saved?.dirty
          && saved.adoptionSessionId !== null
          && saved.candidateBatch > 0
          && intentComplete(saved.draft)
        ) {
          try {
            const recovered = await loadCandidates(
              candidateSetInput(saved.draft, saved.candidateBatch, saved.adoptionSessionId),
            )
            if (!active) return
            const recoveredCandidates = recovered.candidates.map(asCandidate)
            const savedIds = saved.candidates.map((candidate) => candidate.candidateId)
            const recoveredIds = recoveredCandidates.map((candidate) => candidate.candidateId)
            const sameCandidates = savedIds.length === 0
              || (savedIds.length === recoveredIds.length && savedIds.every((candidateId, index) => candidateId === recoveredIds[index]))
            if (!sameCandidates) {
              handleExpiredSession(saved.draft)
              return
            }
            dispatch({ type: "candidate-set-recovered", setId: recovered.candidate_set_id })
            if (saved.candidates.length === 0) {
              dispatch({
                type: "candidates-ready",
                batch: recovered.batch_number,
                setId: recovered.candidate_set_id,
                sessionId: recovered.adoption_session_id,
                candidates: recoveredCandidates,
              })
            }
          } catch (reason: unknown) {
            if (!active) return
            if (isExpiredSessionError(reason)) {
              handleExpiredSession(saved.draft)
              return
            }
            setApiError(describeApiError(reason, "manage.load"))
          }
        }
      } catch (reason: unknown) {
        if (!active) return
        setApiError(describeApiError(reason, "manage.load"))
        setEntryBlock("unavailable")
      } finally {
        if (active) setLoadingInfo(false)
      }
    })()
    return () => { active = false }
  }, [accountId, handleExpiredSession, loadCandidates, open])

  useEffect(() => {
    if (!open) return
    if (state.adoptionSessionId === null) sessionExpiresAtRef.current = null
    if (state.adoptionSessionId !== null && sessionExpiresAtRef.current === null) {
      handleExpiredSession(state.draft)
      return
    }
    void saveAdoptionDraft(accountId, state, sessionExpiresAtRef.current)
  }, [accountId, handleExpiredSession, open, state])

  useEffect(() => {
    if (!open) return undefined
    const expiresAt = sessionExpiresAtRef.current
    if (expiresAt === null) return undefined
    const timer = window.setTimeout(() => {
      if (sessionExpiresAtRef.current === expiresAt) handleExpiredSession(state.draft)
    }, Math.max(0, expiresAt - Date.now()))
    return () => window.clearTimeout(timer)
  }, [handleExpiredSession, open, state.adoptionSessionId, state.screen])

  const allowedSpecies = useMemo(() => {
    return [...(info?.species ?? [])].sort((left, right) => left.sort_order - right.sort_order)
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
    void clearAdoptionDraft(accountId)
    sessionExpiresAtRef.current = null
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
      if (state.candidates.length > 0) dispatch({ type: "screen", screen: "shortlist" })
      return
    }
    if (index === 2) {
      if (state.finalCandidateId !== null) dispatch({ type: "screen", screen: "naming" })
    }
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
    if (state.adoptionSessionId === null) sessionExpiresAtRef.current = adoptionSessionExpiryFromNow()
    setApiError(null)
    setCandidateRecoveryNotice(false)
    setPortraitRuntimeBlocked(false)
    setGenerationRequest(request)
    dispatch({ type: "screen", screen: "generating" })
  }

  const sendInvitations = async (): Promise<void> => {
    const selectedCandidateId = state.selectedCandidateIds[0]
    if (state.candidateSetId === null || selectedCandidateId === undefined) {
      dispatch({ type: "error", message: t("adoption.journey.validation.chooseCandidate") })
      return
    }
    if (sendingInvitations) return
    setApiError(null)
    setInvitationFailureOpen(false)
    setSendingInvitations(true)
    dispatch({ type: "screen", screen: "inviting" })
    try {
      let candidateSetId = state.candidateSetId
      let result: Awaited<ReturnType<typeof adoptionReplies>> | null = null
      let transientFailureCount = 0
      while (result === null) {
        try {
          result = await waitForInvitationReply(
            withCsrfRetry((token) => adoptionReplies(candidateSetId, [selectedCandidateId], "", token)),
            INVITATION_TIMEOUT_MILLISECONDS,
          )
        } catch (reason: unknown) {
          if (isExpiredSessionError(reason)) {
            handleExpiredSession(state.draft)
            return
          }
          if (!isRetryableInvitationFailure(reason) || transientFailureCount >= INVITATION_RETRY_DELAYS_MILLISECONDS.length) throw reason
          const retryDelay = INVITATION_RETRY_DELAYS_MILLISECONDS[transientFailureCount]
          if (retryDelay === undefined) throw reason
          await waitMilliseconds(retryDelay)
          transientFailureCount += 1
        }
      }
      if (result === null) throw new Error("Invitation reply result is missing")
      const previous = new Map(state.candidates.map((candidate) => [candidate.candidateId, candidate]))
      const replies = result.replies.map((reply) => asReply(reply, previous.get(reply.candidate_id)))
      if (!replies.some((reply) => reply.candidateId === selectedCandidateId)) throw new Error("Selected candidate reply is missing")
      dispatch({ type: "replies-ready", finalCandidateId: selectedCandidateId, replies })
    } catch (reason: unknown) {
      if (isExpiredSessionError(reason)) {
        handleExpiredSession(state.draft)
        return
      }
      if (isInvitationChannelFailure(reason)) {
        setInvitationFailureOpen(true)
        return
      }
      dispatch({ type: "screen", screen: "shortlist" })
      setApiError(describeApiError(reason, "manage.save"))
    } finally {
      setSendingInvitations(false)
    }
  }

  const finishAdoption = async (): Promise<void> => {
    const candidateSetId = state.candidateSetId
    const finalCandidateId = state.finalCandidateId
    if (candidateSetId === null || finalCandidateId === null) {
      dispatch({ type: "error", message: t("adoption.journey.validation.chooseCandidate") })
      return
    }
    const name = selectedName(state)
    if (!name || name.length > 20) {
      dispatch({ type: "error", message: t("adoption.journey.validation.name") })
      return
    }
    if (committing) return
    setApiError(null)
    setCommitting(true)
    dispatch({ type: "screen", screen: "committing" })
    try {
      const finalCandidate = state.replies.find((candidate) => candidate.candidateId === finalCandidateId)
      const headshotImageUrl = finalCandidate?.fullBodyImageUrl
        ? await createFinalHeadshotDataUrl(finalCandidate.fullBodyImageUrl)
        : finalCandidate?.headshotImageUrl ?? ""
      const result = await withCsrfRetry((token) => commitAdoption(candidateSetId, finalCandidateId, name, token, {
        ...(finalCandidate?.fullBodyImageUrl ? { fullBodyImageUrl: finalCandidate.fullBodyImageUrl } : {}),
        ...(headshotImageUrl ? { headshotImageUrl } : {}),
      }))
      await clearAdoptionDraft(accountId)
      await onAdopted(result.elfie_id)
      onOpenChange(false)
    } catch (reason: unknown) {
      if (isExpiredSessionError(reason)) {
        handleExpiredSession(state.draft)
        return
      }
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
      dispatch({ type: "screen", screen: "naming" })
      setApiError(describeApiError(reason, "manage.save"))
    } finally {
      setCommitting(false)
    }
  }

  const next = (): void => {
    switch (state.screen) {
      case "welcome": goToBasic(); return
      case "basic":
        if (state.draft.speciesId === null) dispatch({ type: "error", message: t("adoption.journey.validation.species") })
        else void generateCandidates()
        return
      case "appearance": dispatch({ type: "screen", screen: "companionship" }); return
      case "companionship":
        void generateCandidates()
        return
      case "review":
        void generateCandidates()
        return
      case "shortlist": void sendInvitations(); return
      case "replies":
        if (state.finalCandidateId === null) dispatch({ type: "error", message: t("adoption.journey.validation.chooseCandidate") })
        else dispatch({ type: "screen", screen: "naming" })
        return
      case "naming": void finishAdoption(); return
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
      case "review": dispatch({ type: "screen", screen: "basic" }); return
      default: return
    }
  }

  const errorMessage = resolveLocalizedError(apiError, locale)
  const selectedCandidate = state.replies.find((candidate) => candidate.candidateId === state.finalCandidateId)
  const journeyReady = info !== null && !loadingInfo && entryBlock === null
  const portraitRuntimeEligible = open && journeyReady && PORTRAIT_RUNTIME_SCREENS.includes(state.screen)
  const portraitRuntimeRequested = portraitRuntimeEligible && !portraitRuntimeBlocked
  const markPortraitRuntimeActivity = useCallback((): void => {
    if (!portraitRuntimeEligible) return
    const now = Date.now()
    const expired = now - portraitLastActivityAtRef.current >= PORTRAIT_RUNTIME_IDLE_MILLISECONDS
    portraitLastActivityAtRef.current = now
    if (expired) setPortraitRuntimeGeneration((generation) => generation + 1)
    setPortraitRuntimeBlocked(false)
    setPortraitRuntimeEnabled(true)
    if (portraitRuntimeTimerRef.current !== null) window.clearTimeout(portraitRuntimeTimerRef.current)
    portraitRuntimeTimerRef.current = window.setTimeout(() => {
      portraitRuntimeTimerRef.current = null
      setPortraitRuntimeEnabled(false)
    }, PORTRAIT_RUNTIME_IDLE_MILLISECONDS)
  }, [portraitRuntimeEligible])

  useEffect(() => {
    if (!portraitRuntimeRequested) {
      setPortraitRuntimeEnabled(false)
      if (portraitRuntimeTimerRef.current !== null) {
        window.clearTimeout(portraitRuntimeTimerRef.current)
        portraitRuntimeTimerRef.current = null
      }
      return undefined
    }
    markPortraitRuntimeActivity()
    return () => {
      if (portraitRuntimeTimerRef.current !== null) {
        window.clearTimeout(portraitRuntimeTimerRef.current)
        portraitRuntimeTimerRef.current = null
      }
    }
  }, [markPortraitRuntimeActivity, portraitRuntimeRequested, state.screen])

  useEffect(() => {
    if (!portraitRuntimeEligible) return undefined
    const resume = (): void => {
      if (document.visibilityState === "visible") markPortraitRuntimeActivity()
    }
    document.addEventListener("visibilitychange", resume)
    window.addEventListener("focus", resume)
    window.addEventListener("pageshow", resume)
    return () => {
      document.removeEventListener("visibilitychange", resume)
      window.removeEventListener("focus", resume)
      window.removeEventListener("pageshow", resume)
    }
  }, [markPortraitRuntimeActivity, portraitRuntimeEligible])

  const entryChecking = open && (loadingInfo || (info === null && entryBlock === null))
  const title = !journeyReady
    ? t("adoption.journey.entryCheck.title")
    : state.screen === "welcome"
      ? t("adoption.journey.window.welcomeTitle")
      : t("adoption.journey.window.title")
  const stage = STAGE_FOR_SCREEN[state.screen]
  const showFooter = journeyReady && !["welcome", "generating", "inviting", "committing", "arrival", "naming"].includes(state.screen)
  const showBack = !isIntentLocked && state.screen !== "basic"
  const onGenerationReady = useCallback((result: AdoptionCandidateSet, candidates: readonly Candidate[]): void => {
    if (sessionExpiresAtRef.current === null) sessionExpiresAtRef.current = adoptionSessionExpiryFromNow()
    setGenerationRequest(null)
    dispatch({
      type: "candidates-ready",
      batch: result.batch_number,
      setId: result.candidate_set_id,
      sessionId: result.adoption_session_id,
      candidates,
      selectedIds: state.selectedCandidateIds,
    })
  }, [state.selectedCandidateIds])
  const onGenerationError = useCallback((reason: unknown): void => {
    setGenerationRequest(null)
    setPortraitRuntimeBlocked(true)
    setPortraitRuntimeEnabled(false)
    if (isExpiredSessionError(reason)) {
      handleExpiredSession(state.draft)
      return
    }
    dispatch({ type: "error", message: t("adoption.journey.errors.generate") })
  }, [handleExpiredSession, state.draft, t])

  const candidateLabel = (candidateId: string): string => {
    const index = state.candidates.findIndex((candidate) => candidate.candidateId === candidateId)
    return t("adoption.journey.shortlist.candidate", { number: index >= 0 ? index + 1 : "" })
  }

  const exitEntryBlock = (): void => {
    setEntryBlock(null)
    onOpenChange(false)
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
        onKeyDown={markPortraitRuntimeActivity}
        onPointerDown={markPortraitRuntimeActivity}
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

        {journeyReady && state.screen !== "welcome" ? (
          <ol aria-label={t("adoption.journey.progress.label")} className="adoption-progress">
            {(["basic", "selection", "welcome"] as const).map((key, index) => (
              <li aria-current={stage === index ? "step" : undefined} key={key}>
                <button aria-label={t(`adoption.journey.progress.${key}`)} disabled={isIntentLocked || (index > 0 && state.candidates.length === 0)} onClick={() => navigateToStage(index)} type="button">
                  <span>{index + 1}</span>{t(`adoption.journey.progress.${key}`)}
                </button>
              </li>
            ))}
          </ol>
        ) : null}

        <div aria-live="polite" className="adoption-dialog__body">
          {journeyReady && state.error ? <p className="adoption-inline-error" role="alert">{state.error}</p> : null}
          {journeyReady && errorMessage ? <p className="adoption-inline-error" role="alert">{errorMessage}</p> : null}
          {journeyReady && state.screen === "shortlist" && candidateRecoveryNotice ? <p className="adoption-inline-notice" role="status">{t("adoption.journey.recovery.candidatesRegenerated")}</p> : null}
          {entryChecking ? <AdoptionEntryCheck t={t} /> : null}
          {journeyReady && state.screen === "welcome" ? <WelcomeScreen t={t} onStart={goToBasic} /> : null}
          {journeyReady && state.screen === "basic" ? <BasicScreen allowedSpecies={allowedSpecies} canAdopt={info?.quota.can_adopt ?? true} draft={state.draft} dispatch={dispatch} locale={locale} speciesName={(id) => speciesName(id, info?.species.find((species) => species.species_id === id), locale)} stageName={(value) => stageName(t, value)} t={t} /> : null}
          {journeyReady && state.screen === "appearance" ? <AppearanceScreen controls={info?.species.find((species) => species.species_id === state.draft.speciesId)?.appearance_controls ?? []} draft={state.draft} dispatch={dispatch} t={t} /> : null}
          {journeyReady && state.screen === "companionship" ? <CompanionshipScreen draft={state.draft} dispatch={dispatch} onAnswer={answerCompanionship} questionIndex={state.questionIndex} t={t} /> : null}
          {journeyReady && state.screen === "generating" && generationRequest !== null ? <GeneratingScreen frameRef={portraitFrameRef} loadCandidates={loadCandidates} onError={onGenerationError} onReady={onGenerationReady} request={generationRequest} runtimeActive={portraitRuntimeEnabled && portraitRuntimeRequested} runtimeGeneration={portraitRuntimeGeneration} t={t} /> : null}
          {journeyReady && state.screen === "shortlist" ? <ShortlistScreen candidates={state.candidates} candidateBatch={state.candidateBatch} dispatch={dispatch} onRegenerate={() => { void generateCandidates() }} selectedIds={state.selectedCandidateIds} t={t} /> : null}
          {journeyReady && state.screen === "inviting" ? <SendingScreen candidates={state.candidates.filter((candidate) => state.selectedCandidateIds.includes(candidate.candidateId))} t={t} /> : null}
          {journeyReady && state.screen === "naming" && selectedCandidate ? <ArrivalWelcomeScreen candidate={selectedCandidate} candidateImageUrl={candidateImageUrl} candidateLabel={candidateLabel(selectedCandidate.candidateId)} customName={state.customName} onFinish={() => { void finishAdoption() }} pending={committing} dispatch={dispatch} t={t} /> : null}
          {journeyReady && state.screen === "committing" ? <ProgressScreen title={t("adoption.journey.committing.title", { name: selectedName(state) })} /> : null}
        </div>

        {portraitRuntimeEnabled && portraitRuntimeRequested ? <iframe
          aria-hidden="true"
          className="adoption-portrait-renderer"
          key={portraitRuntimeGeneration}
          onError={() => { if (state.screen === "generating") onGenerationError(new ProfileGodotPreviewError("preview_load_failed")) }}
          ref={portraitFrameRef}
          src="/runtime/godot/elfienest.html?mode=elfie_lab"
          title=""
        /> : null}

        {showFooter ? (
          <footer className="adoption-dialog__footer">
            {showBack ? <Button onClick={back} type="button" variant="ghost">{t("adoption.journey.actions.back")}</Button> : null}
            <div>
              {state.screen === "basic" ? <Button disabled={state.draft.speciesId === null} onClick={() => dispatch({ type: "screen", screen: "appearance" })} type="button" variant="outline">{t("adoption.journey.actions.detailMatching")}</Button> : null}
              <Button disabled={isNextDisabled(state, info)} onClick={next} type="button">{nextLabel(state, t)}</Button>
            </div>
          </footer>
        ) : null}

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

        {entryBlock !== null ? <AdoptionEntryBlockDialog block={entryBlock} onExit={exitEntryBlock} open t={t} /> : null}

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
  const [skipWelcome, setSkipWelcome] = useState(true)
  return <section className="adoption-welcome">
    <div className="adoption-welcome__art"><img alt={t("adoption.journey.welcome.imageAlt")} src={elfariaArrivalImage} /></div>
    <div className="adoption-welcome__copy"><h2>{t("adoption.journey.welcome.title")}</h2><details className="adoption-auxiliary"><summary>{t("adoption.journey.welcome.details")}</summary><p>{t("adoption.journey.welcome.note")}</p></details><label className="adoption-welcome__skip"><Checkbox aria-label={t("adoption.journey.welcome.skip")} checked={skipWelcome} className="adoption-welcome__checkbox" onCheckedChange={(checked) => setSkipWelcome(checked === true)} /><span>{t("adoption.journey.welcome.skip")}</span></label><Button onClick={() => onStart(skipWelcome)} type="button">{t("adoption.journey.welcome.start")}</Button></div>
  </section>
}

function BasicScreen({
  allowedSpecies, canAdopt, dispatch, draft, locale, speciesName, stageName, t,
}: {
  readonly allowedSpecies: readonly AdoptionInfo["species"][number][]
  readonly canAdopt: boolean
  readonly dispatch: React.Dispatch<AdoptionAction>
  readonly draft: AdoptionDraftState["draft"]
  readonly locale: string
  readonly speciesName: (id: SpeciesId) => string
  readonly stageName: (stage: LifeStage) => string
  readonly t: JourneyT
}) {
  return <section>
    <ScreenIntro title={t("adoption.journey.basic.title")} />
    <fieldset className="adoption-fieldset"><legend>{t("adoption.journey.basic.speciesLabel")}</legend><div className="adoption-species-grid">
      {allowedSpecies.map((species) => <ChoiceButton
        className="adoption-species-choice"
        key={species.species_id}
        onClick={(event) => {
          if (event.detail === 0) dispatch({ type: "set-basic", field: "speciesId", value: species.species_id })
        }}
        onPointerDown={(event) => {
          if (event.button === 0) dispatch({ type: "set-basic", field: "speciesId", value: species.species_id })
        }}
        selected={draft.speciesId === species.species_id}
      >
        <img alt="" className="adoption-species-choice__image" src={species.presentation_images.full_body_url} />
        <span><strong>{locale === "zh-CN" ? species.display_name_zh : species.display_name}</strong></span>
      </ChoiceButton>)}
    </div></fieldset>
    <fieldset className="adoption-fieldset"><legend>{t("adoption.journey.basic.lifeStageLabel")}</legend><div className="adoption-option-row">{LIFE_STAGES.map((stage) => <ChoiceButton key={stage} onClick={() => dispatch({ type: "set-basic", field: "lifeStage", value: stage })} selected={draft.lifeStage === stage}>{stageName(stage)}</ChoiceButton>)}</div></fieldset>
    <fieldset className="adoption-fieldset"><legend>{t("adoption.journey.basic.genderLabel")}</legend><div className="adoption-option-row">{GENDERS.map((gender) => <ChoiceButton key={gender} onClick={() => dispatch({ type: "set-basic", field: "gender", value: gender })} selected={draft.gender === gender}>{t(`adoption.journey.genders.${gender}`)}</ChoiceButton>)}</div></fieldset>
    {!canAdopt ? <p className="adoption-quota-warning">{t("adoption.journey.quota.exhausted")}</p> : null}
  </section>
}

function AppearanceScreen({ controls, draft, dispatch, t }: { readonly controls: readonly AdoptionInfo["species"][number]["appearance_controls"][number][]; readonly draft: AdoptionDraftState["draft"]; readonly dispatch: React.Dispatch<AdoptionAction>; readonly t: JourneyT }) {
  const defaults: Record<(typeof APPEARANCE_GROUPS)[number], readonly string[]> = {
    stature: ["small", "standard", "tall", "any"],
    build: ["slim", "standard", "round", "any"],
    face: ["soft", "balanced", "defined", "any"],
    signature: ["warm", "marked", "ears", "any"],
  }
  const configured = new Map(controls.map((control) => [control.control_id, control.options]))
  const groups = APPEARANCE_GROUPS.map((group) => ({
    group,
    options: configured.get(group) ?? defaults[group],
  }))
  return <section>
    <ScreenIntro badge={t("adoption.journey.badges.detailedMatch", { current: 1, total: 2 })} title={t("adoption.journey.appearance.title")} />
    <div className="adoption-appearance-grid">{groups.map(({ group, options }) => <fieldset className="adoption-fieldset" key={group}><legend>{t(`adoption.journey.appearance.groups.${group}.label`)}</legend><div className="adoption-appearance-options">{options.map((value) => <ChoiceButton className="adoption-appearance-choice" key={value} onClick={() => dispatch({ type: "set-appearance", field: group, value } as AdoptionAction)} selected={draft[group] === value}><span className={`adoption-shape adoption-shape--${value}`} aria-hidden="true" />{t(`adoption.journey.appearance.groups.${group}.${value}`)}</ChoiceButton>)}</div></fieldset>)}</div>
    <fieldset className="adoption-fieldset"><legend>{t("adoption.journey.appearance.priorityLabel")}</legend><div className="adoption-option-row">{(["stature", "build", "face", "signature"] as const).map((priority) => <ChoiceButton key={priority} onClick={() => dispatch({ type: "set-appearance", field: "priority", value: priority })} selected={draft.priority === priority}>{t(`adoption.journey.appearance.groups.${priority}.label`)}</ChoiceButton>)}</div></fieldset>
  </section>
}

function CompanionshipScreen({ draft, dispatch, onAnswer, questionIndex, t }: { readonly draft: AdoptionDraftState["draft"]; readonly dispatch: React.Dispatch<AdoptionAction>; readonly onAnswer: (index: number, value: CompanionAnswer) => void; readonly questionIndex: number; readonly t: JourneyT }) {
  const options = COMPANIONSHIP_OPTIONS[questionIndex] ?? COMPANIONSHIP_OPTIONS[0] ?? []
  return <section>
    <ScreenIntro badge={t("adoption.journey.badges.detailedMatch", { current: 2, total: 2 })} title={t("adoption.journey.companionship.title")} />
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

function TimedWaitStatus({ translationPrefix, t }: { readonly translationPrefix: string; readonly t: JourneyT }) {
  const [phase, setPhase] = useState<0 | 1 | 2>(0)

  useEffect(() => {
    setPhase(0)
    const secondPhaseTimer = window.setTimeout(() => setPhase(1), WAIT_STATUS_SECOND_PHASE_MILLISECONDS)
    const finalPhaseTimer = window.setTimeout(() => setPhase(2), WAIT_STATUS_FINAL_PHASE_MILLISECONDS)
    return () => {
      window.clearTimeout(secondPhaseTimer)
      window.clearTimeout(finalPhaseTimer)
    }
  }, [translationPrefix])

  return <p className="adoption-sending-screen__candidate">{t(`${translationPrefix}.status.${WAIT_STATUS_KEYS[phase]}`)}</p>
}

type GeneratingScreenProps = {
  readonly frameRef: RefObject<HTMLIFrameElement | null>
  readonly loadCandidates: (request: AdoptionCandidateSetInput) => Promise<AdoptionCandidateSet>
  readonly onError: (reason: unknown) => void
  readonly onReady: (result: AdoptionCandidateSet, candidates: readonly Candidate[]) => void
  readonly request: AdoptionCandidateSetInput
  readonly runtimeActive: boolean
  readonly runtimeGeneration: number
  readonly t: JourneyT
}

type CandidateRequestLease = {
  readonly loadCandidates: (request: AdoptionCandidateSetInput) => Promise<AdoptionCandidateSet>
  readonly promise: Promise<AdoptionCandidateSet>
  readonly request: AdoptionCandidateSetInput
}

type CandidateLoad = {
  readonly candidates: readonly Candidate[]
  readonly request: AdoptionCandidateSetInput
  readonly result: AdoptionCandidateSet
}

function GeneratingScreen({ frameRef, loadCandidates, onError, onReady, request, runtimeActive, runtimeGeneration, t }: GeneratingScreenProps) {
  const candidateRequestRef = useRef<CandidateRequestLease | null>(null)
  const renderedCandidatesRef = useRef(new Map<string, Candidate>())
  const [candidateLoad, setCandidateLoad] = useState<CandidateLoad | null>(null)

  useEffect(() => {
    let active = true
    let lease = candidateRequestRef.current
    if (lease === null || lease.request !== request || lease.loadCandidates !== loadCandidates) {
      lease = { loadCandidates, promise: loadCandidates(request), request }
      candidateRequestRef.current = lease
      renderedCandidatesRef.current.clear()
      setCandidateLoad(null)
    }
    const currentLease = lease
    void currentLease.promise
      .then((result) => {
        if (!active) return
        const candidates = result.candidates.map(asCandidate)
        if (candidates.some((candidate) => Object.keys(candidate.runtimeAppearance).length === 0)) {
          onError(new ProfileGodotPreviewError("candidate_portrait_unavailable"))
          return
        }
        setCandidateLoad({ candidates, request: currentLease.request, result })
      })
      .catch((reason: unknown) => {
        if (active) onError(reason)
      })
    return () => { active = false }
  }, [loadCandidates, onError, request])

  const activeLoad = candidateLoad?.request === request ? candidateLoad : null

  useEffect(() => {
    if (!runtimeActive || activeLoad === null) return undefined
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
        await waitWithTimeout(ready, 20_000, "preview_timeout")
        if (!active) return
        for (const candidate of activeLoad.candidates) {
          if (!active || bridge === null) return
          if (renderedCandidatesRef.current.has(candidate.candidateId)) continue
          await sendAndWait(bridge, waitForAction, "configure", {
            appearance: candidate.runtimeAppearance,
            elfie_id: `candidate-${candidate.candidateId}`,
            spec_revision: portraitRevision(candidate.candidateId),
            species_id: candidate.speciesId,
          })
          const provisional = await captureAndWait(bridge, waitForAction)
          try {
            const metrics = await measureVisibleFrame(provisional.blob)
            if (metrics !== null) {
              await sendAndWait(bridge, waitForAction, "frame", toGodotVisibleFrameMetrics(metrics))
            }
          } finally {
            if (typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(provisional.previewUrl)
          }
          const fullBody = await captureAndWait(bridge, waitForAction)
          let fullBodyImageUrl = ""
          try {
            fullBodyImageUrl = await captureDataUrl(fullBody)
          } finally {
            URL.revokeObjectURL(fullBody.previewUrl)
          }
          if (!active) return
          renderedCandidatesRef.current.set(candidate.candidateId, { ...candidate, fullBodyImageUrl, headshotImageUrl: "" })
        }
        const rendered = activeLoad.candidates.map((candidate) => renderedCandidatesRef.current.get(candidate.candidateId))
        if (rendered.some((candidate) => candidate === undefined)) {
          throw new ProfileGodotPreviewError("candidate_portrait_unavailable")
        }
        if (active) onReady(activeLoad.result, rendered as readonly Candidate[])
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
  }, [activeLoad, frameRef, onError, onReady, runtimeActive, runtimeGeneration])

  const title = t("adoption.journey.generating.title")
  return <section className="adoption-progress-screen">
    <h2>{title}</h2>
    <div aria-label={title} className="adoption-signal adoption-progress-signal" role="progressbar"><span /></div>
    <TimedWaitStatus t={t} translationPrefix="adoption.journey.generating" />
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

const HEADSHOT_FRAME_HEIGHT_RATIO = 0.57
const HEADSHOT_VISIBLE_HEIGHT_RATIO = 0.60
const HEADSHOT_HORIZONTAL_PADDING_RATIO = 0.14
const HEADSHOT_TOP_PADDING_RATIO = 0.03

export function calculateHeadshotCrop(
  naturalWidth: number,
  naturalHeight: number,
  visibleBounds: VisibleFrameBounds | null = null,
): {
  readonly cropSize: number
  readonly cropX: number
  readonly cropY: number
} {
  const safeWidth = Math.max(1, Math.floor(naturalWidth))
  const safeHeight = Math.max(1, Math.floor(naturalHeight))
  const visibleWidth = visibleBounds === null
    ? 0
    : Math.max(0, visibleBounds.right - visibleBounds.left + 1)
  const visibleHeight = visibleBounds === null
    ? 0
    : Math.max(0, visibleBounds.bottom - visibleBounds.top + 1)
  const cropSize = Math.max(
    1,
    Math.min(
      safeWidth,
      safeHeight,
      Math.round(Math.max(
        visibleWidth * (1 + HEADSHOT_HORIZONTAL_PADDING_RATIO),
        Math.min(
          visibleHeight * HEADSHOT_VISIBLE_HEIGHT_RATIO,
          safeHeight * HEADSHOT_FRAME_HEIGHT_RATIO,
        ),
      )),
    ),
  )
  const contentCenterX = visibleBounds === null
    ? safeWidth * 0.5
    : (visibleBounds.left + visibleBounds.right + 1) * 0.5
  const cropX = Math.min(
    Math.max(0, safeWidth - cropSize),
    Math.max(0, Math.round(contentCenterX - cropSize * 0.5)),
  )
  const contentTop = visibleBounds === null ? safeHeight * 0.06 : visibleBounds.top
  const maxCropY = Math.max(0, safeHeight - cropSize)
  const cropY = Math.min(
    maxCropY,
    Math.max(0, Math.round(contentTop - cropSize * HEADSHOT_TOP_PADDING_RATIO)),
  )
  return { cropSize, cropX, cropY }
}

async function createHeadshotDataUrl(capture: { readonly blob: Blob }): Promise<string> {
  let sourceUrl: string | undefined
  try {
    sourceUrl = URL.createObjectURL(capture.blob)
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const element = new Image()
      element.onload = () => resolve(element)
      element.onerror = () => reject(new ProfileGodotPreviewError("invalid_portrait"))
      element.src = sourceUrl as string
    })
    const sourcePixels = document.createElement("canvas")
    sourcePixels.width = image.naturalWidth
    sourcePixels.height = image.naturalHeight
    const sourceContext = sourcePixels.getContext("2d")
    if (sourceContext === null) throw new ProfileGodotPreviewError("invalid_portrait")
    sourceContext.drawImage(image, 0, 0, image.naturalWidth, image.naturalHeight)
    const visibleBounds = calculateVisibleFrameBounds(
      image.naturalWidth,
      image.naturalHeight,
      sourceContext.getImageData(0, 0, image.naturalWidth, image.naturalHeight).data,
    )
    const { cropSize, cropX, cropY } = calculateHeadshotCrop(
      image.naturalWidth,
      image.naturalHeight,
      visibleBounds,
    )
    const canvas = document.createElement("canvas")
    canvas.width = cropSize
    canvas.height = cropSize
    const context = canvas.getContext("2d")
    if (context === null) throw new ProfileGodotPreviewError("invalid_portrait")
    context.drawImage(image, cropX, cropY, cropSize, cropSize, 0, 0, cropSize, cropSize)
    return canvas.toDataURL("image/png")
  } catch {
    return captureDataUrl(capture)
  } finally {
    if (sourceUrl !== undefined) URL.revokeObjectURL(sourceUrl)
  }
}

function captureFromDataUrl(dataUrl: string): { readonly blob: Blob; readonly previewUrl: string } | null {
  const match = /^data:([^;,]+);base64,(.+)$/.exec(dataUrl)
  if (match === null) return null
  const mediaType = match[1]
  const encoded = match[2]
  if (mediaType === undefined || encoded === undefined) return null
  try {
    const binary = atob(encoded)
    const bytes = new Uint8Array(binary.length)
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
    const blob = new Blob([bytes], { type: mediaType })
    return { blob, previewUrl: URL.createObjectURL(blob) }
  } catch {
    return null
  }
}

async function createFinalHeadshotDataUrl(fullBodyImageUrl: string): Promise<string> {
  const capture = captureFromDataUrl(fullBodyImageUrl)
  if (capture === null) return fullBodyImageUrl
  try {
    return await createHeadshotDataUrl(capture)
  } finally {
    URL.revokeObjectURL(capture.previewUrl)
  }
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
    <div className="adoption-shortlist-header">
      <ScreenIntro eyebrow={t("adoption.journey.shortlist.eyebrow")} title={t("adoption.journey.shortlist.title")} />
      <div className="adoption-shortlist-header__actions">
        <span>{t("adoption.journey.shortlist.batch", { current: candidateBatch, max: MAX_CANDIDATE_BATCHES })}</span>
        <Button disabled={!canRegenerate} onClick={onRegenerate} type="button" variant="outline">{canRegenerate ? t("adoption.journey.shortlist.regenerate") : t("adoption.journey.shortlist.batchComplete", { max: MAX_CANDIDATE_BATCHES })}</Button>
      </div>
    </div>
    <div className="adoption-candidate-grid">
      {candidates.map((candidate, index) => {
        const selected = selectedIds.includes(candidate.candidateId)
        return <ChoiceButton aria-label={t("adoption.journey.shortlist.candidate", { number: index + 1 })} className="adoption-candidate-card" key={candidate.candidateId} onClick={() => dispatch({ type: "toggle-candidate", candidateId: candidate.candidateId })} selected={selected}><img alt="" src={candidateImageUrl(candidate, "fullBody")} /><span className="adoption-candidate-card__copy"><strong>{t("adoption.journey.shortlist.candidate", { number: index + 1 })}</strong><small>{candidateAgeLabel(t, candidate.ageYears)} · {t(`adoption.journey.genders.${candidate.gender}`)}</small><TagList values={candidate.personalityTags.slice(0, 3)} /></span></ChoiceButton>
      })}
    </div>
  </section>
}

function SendingScreen({ candidates, t }: { readonly candidates: readonly Candidate[]; readonly t: JourneyT }) {
  const candidate = candidates[0]
  const title = t("adoption.journey.inviting.title")
  return <section className="adoption-sending-screen"><div className="adoption-arrival__portal"><img alt="" src={candidate ? candidateImageUrl(candidate, "headshot") : ""} /></div><ScreenIntro title={title} /><div aria-label={title} className="adoption-signal adoption-progress-signal" role="progressbar"><span /></div><TimedWaitStatus t={t} translationPrefix="adoption.journey.inviting" /></section>
}

function isNextDisabled(state: AdoptionDraftState, info: AdoptionInfo | null): boolean {
  if (state.screen === "basic") return state.draft.speciesId === null || info?.availability !== "available"
  if (state.screen === "companionship") return state.draft.answers.some((answer) => answer === null)
  if (state.screen === "shortlist") return state.selectedCandidateIds.length === 0
  if (state.screen === "replies") return state.finalCandidateId === null
  if (state.screen === "naming") {
    const candidate = state.replies.find((item) => item.candidateId === state.finalCandidateId)
    return candidate === undefined || !state.customName.trim()
  }
  return false
}

function nextLabel(state: AdoptionDraftState, t: JourneyT): string {
  if (state.screen === "basic") return t("adoption.journey.actions.startMatching")
  if (state.screen === "appearance") return t("adoption.journey.actions.toCompanionship")
  if (state.screen === "companionship") return t("adoption.journey.actions.startMatching")
  if (state.screen === "review") return t("adoption.journey.actions.generate")
  if (state.screen === "shortlist") return t("adoption.journey.actions.welcomeSelected")
  if (state.screen === "replies") return t("adoption.journey.actions.toNaming")
  if (state.screen === "naming") return t("adoption.journey.arrival.enter")
  return t("adoption.journey.actions.continue")
}
