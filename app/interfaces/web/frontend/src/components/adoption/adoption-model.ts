export const ADOPTION_STAGES = [
  "basic",
  "appearance",
  "companionship",
  "meeting",
] as const

export type AdoptionStage = (typeof ADOPTION_STAGES)[number]
export type AdoptionScreen =
  | "welcome"
  | AdoptionStage
  | "review"
  | "generating"
  | "shortlist"
  | "inviting"
  | "replies"
  | "naming"
  | "committing"
  | "arrival"

export type SpeciesId = string
export type LifeStage = "youth" | "young_adult" | "mature" | "elder" | "any"
export type GenderPreference = "male" | "female" | "any"
export type AppearanceChoice = "small" | "standard" | "tall" | "any"
export type BuildChoice = "slim" | "standard" | "round" | "any"
export type FaceChoice = "soft" | "balanced" | "defined" | "any"
export type SignatureChoice = "warm" | "marked" | "ears" | "any"
export type AppearancePriority = "stature" | "build" | "face" | "signature"
export type NameMode = "original" | "suggested" | "custom"

export type CompanionAnswer =
  | "approach"
  | "quiet"
  | "independent"
  | "explore"
  | "research"
  | "observe"
  | "adapt"
  | "plan"
  | "comfort"
  | "direct"
  | "discuss"
  | "pause"
  | "lively"
  | "steady"
  | "space"
  | "any"

export type AdoptionDraft = {
  readonly speciesId: SpeciesId | null
  readonly lifeStage: LifeStage
  readonly gender: GenderPreference
  readonly stature: AppearanceChoice
  readonly build: BuildChoice
  readonly face: FaceChoice
  readonly signature: SignatureChoice
  readonly priority: AppearancePriority
  readonly answers: readonly (CompanionAnswer | null)[]
}

export type Candidate = {
  readonly candidateId: string
  readonly originalName: string
  readonly suggestedName: string
  readonly speciesId: SpeciesId
  readonly lifeStage: LifeStage
  readonly gender: "male" | "female"
  readonly imageUrl: string
  readonly appearanceTags: readonly string[]
  readonly personalityTags: readonly string[]
  readonly introduction: string
  readonly compatibility: string
}

export type CandidateReply = Candidate & {
  readonly status: "accepted" | "unsure"
  readonly message: string
}

export type AdoptionDraftState = {
  readonly screen: AdoptionScreen
  readonly draft: AdoptionDraft
  readonly questionIndex: number
  readonly candidates: readonly Candidate[]
  readonly candidateBatch: number
  readonly selectedCandidateIds: readonly string[]
  readonly replies: readonly CandidateReply[]
  readonly finalCandidateId: string | null
  readonly nameMode: NameMode
  readonly customName: string
  readonly candidateSetId: string | null
  readonly error: string | null
  readonly dirty: boolean
}

export const MAX_CANDIDATE_BATCHES = 3 as const

export const DEFAULT_DRAFT: AdoptionDraft = {
  speciesId: null,
  lifeStage: "any",
  gender: "any",
  stature: "any",
  build: "any",
  face: "any",
  signature: "any",
  priority: "face",
  answers: [null, null, null, null, null],
}

export const INITIAL_ADOPTION_STATE: AdoptionDraftState = {
  screen: "basic",
  draft: DEFAULT_DRAFT,
  questionIndex: 0,
  candidates: [],
  candidateBatch: 0,
  selectedCandidateIds: [],
  replies: [],
  finalCandidateId: null,
  nameMode: "original",
  customName: "",
  candidateSetId: null,
  error: null,
  dirty: false,
}

export type AdoptionAction =
  | { readonly type: "screen"; readonly screen: AdoptionScreen }
  | { readonly type: "set-basic"; readonly field: "speciesId" | "lifeStage" | "gender"; readonly value: SpeciesId | LifeStage | GenderPreference }
  | { readonly type: "set-appearance"; readonly field: "stature" | "build" | "face" | "signature" | "priority"; readonly value: AppearanceChoice | BuildChoice | FaceChoice | SignatureChoice | AppearancePriority }
  | { readonly type: "set-answer"; readonly index: number; readonly value: CompanionAnswer }
  | { readonly type: "question"; readonly index: number }
  | { readonly type: "candidates-ready"; readonly setId: string; readonly batch: number; readonly candidates: readonly Candidate[] }
  | { readonly type: "toggle-candidate"; readonly candidateId: string }
  | { readonly type: "replies-ready"; readonly replies: readonly CandidateReply[] }
  | { readonly type: "select-final"; readonly candidateId: string }
  | { readonly type: "name-mode"; readonly mode: NameMode }
  | { readonly type: "custom-name"; readonly value: string }
  | { readonly type: "error"; readonly message: string }
  | { readonly type: "clear-error" }
  | { readonly type: "reset"; readonly screen?: AdoptionScreen }

function isAppearanceField(field: AdoptionAction & { type: "set-appearance" }): field is Extract<AdoptionAction, { type: "set-appearance" }> {
  return field.type === "set-appearance"
}

export function adoptionReducer(state: AdoptionDraftState, action: AdoptionAction): AdoptionDraftState {
  switch (action.type) {
    case "screen":
      return { ...state, screen: action.screen, error: null }
    case "set-basic": {
      const draft = { ...state.draft, [action.field]: action.value } as AdoptionDraft
      const intentChanged = action.value !== state.draft[action.field]
      return {
        ...state,
        draft,
        dirty: true,
        error: null,
        ...(intentChanged ? { candidates: [], candidateBatch: 0, selectedCandidateIds: [], replies: [], finalCandidateId: null, candidateSetId: null } : {}),
      }
    }
    case "set-appearance": {
      const field = action.field
      if (!isAppearanceField(action)) return state
      const draft = { ...state.draft, [field]: action.value } as AdoptionDraft
      return { ...state, draft, dirty: true, candidates: [], candidateBatch: 0, selectedCandidateIds: [], replies: [], finalCandidateId: null, candidateSetId: null, error: null }
    }
    case "set-answer": {
      const answers = [...state.draft.answers]
      answers[action.index] = action.value
      return { ...state, draft: { ...state.draft, answers }, dirty: true, candidates: [], candidateBatch: 0, selectedCandidateIds: [], replies: [], finalCandidateId: null, candidateSetId: null, error: null }
    }
    case "question":
      return { ...state, questionIndex: Math.max(0, Math.min(4, action.index)), error: null }
    case "candidates-ready":
      return { ...state, screen: "shortlist", candidateSetId: action.setId, candidates: action.candidates, candidateBatch: action.batch, selectedCandidateIds: [], replies: [], finalCandidateId: null, error: null, dirty: true }
    case "toggle-candidate": {
      const selected = state.selectedCandidateIds.includes(action.candidateId)
        ? state.selectedCandidateIds.filter((id) => id !== action.candidateId)
        : state.selectedCandidateIds.length < 3 ? [...state.selectedCandidateIds, action.candidateId] : state.selectedCandidateIds
      return { ...state, selectedCandidateIds: selected, error: null }
    }
    case "replies-ready":
      return { ...state, screen: "replies", replies: action.replies, finalCandidateId: null, error: null }
    case "select-final":
      return { ...state, finalCandidateId: action.candidateId, error: null }
    case "name-mode":
      return { ...state, nameMode: action.mode, error: null }
    case "custom-name":
      return { ...state, customName: action.value, nameMode: "custom", error: null }
    case "error":
      return { ...state, screen: state.screen === "generating" || state.screen === "inviting" || state.screen === "committing" ? "review" : state.screen, error: action.message }
    case "clear-error":
      return { ...state, error: null }
    case "reset":
      return { ...INITIAL_ADOPTION_STATE, screen: action.screen ?? "basic" }
    default:
      return state
  }
}

export function intentComplete(draft: AdoptionDraft): boolean {
  return draft.speciesId !== null && draft.answers.every((answer) => answer !== null)
}

export function selectedName(state: AdoptionDraftState): string {
  const candidate = state.replies.find((item) => item.candidateId === state.finalCandidateId)
  if (candidate === undefined) return ""
  if (state.nameMode === "suggested") return candidate.suggestedName
  if (state.nameMode === "custom") return state.customName.trim()
  return candidate.originalName
}
