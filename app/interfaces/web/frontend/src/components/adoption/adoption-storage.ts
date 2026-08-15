import {
  DEFAULT_DRAFT,
  INITIAL_ADOPTION_STATE,
  type AdoptionDraftState,
} from "./adoption-model"

const DATABASE_NAME = "elfienest-adoption"
const DATABASE_VERSION = 1
const STORE_NAME = "drafts"
const STORAGE_VERSION = "v2"
const pendingWrites = new Map<string, Promise<void>>()

export const ADOPTION_SESSION_TTL_MILLISECONDS = 5 * 60 * 60 * 1000

type StoredDraft = {
  readonly accountId: string
  readonly savedAt: number
  readonly sessionExpiresAt: number | null
  readonly state: AdoptionDraftState
}

export type AdoptionDraftLoadResult = {
  readonly state: AdoptionDraftState | null
  readonly expired: boolean
  readonly sessionExpiresAt: number | null
}

function storageKey(accountId: string): string {
  return `elfienest.adoption-draft.${accountId}.${STORAGE_VERSION}`
}

function resumableState(state: AdoptionDraftState): AdoptionDraftState {
  if (state.screen === "generating") {
    return { ...state, screen: "review" }
  }
  if (state.screen === "committing") {
    return { ...state, screen: "naming" }
  }
  return state
}

function normalizeState(value: unknown): AdoptionDraftState | null {
  if (value === null || typeof value !== "object") return null
  const candidate = value as Partial<AdoptionDraftState>
  if (candidate.draft === null || typeof candidate.draft !== "object") return null
  return {
    ...INITIAL_ADOPTION_STATE,
    ...candidate,
    draft: { ...DEFAULT_DRAFT, ...candidate.draft },
    candidates: Array.isArray(candidate.candidates) ? candidate.candidates : [],
    selectedCandidateIds: Array.isArray(candidate.selectedCandidateIds) ? candidate.selectedCandidateIds : [],
    replies: Array.isArray(candidate.replies) ? candidate.replies : [],
    error: null,
  }
}

function indexedDbAvailable(): boolean {
  return typeof window !== "undefined" && "indexedDB" in window && window.indexedDB !== undefined
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!indexedDbAvailable()) {
      reject(new Error("IndexedDB is unavailable"))
      return
    }
    const request = window.indexedDB.open(DATABASE_NAME, DATABASE_VERSION)
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME, { keyPath: "accountId" })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error("IndexedDB could not be opened"))
  })
}

function readIndexedDraft(accountId: string): Promise<StoredDraft | null> {
  return openDatabase().then((database) => new Promise<StoredDraft | null>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readonly")
    const request = transaction.objectStore(STORE_NAME).get(accountId)
    request.onsuccess = () => resolve((request.result as StoredDraft | undefined) ?? null)
    request.onerror = () => reject(request.error ?? new Error("IndexedDB draft could not be read"))
    transaction.oncomplete = () => database.close()
    transaction.onerror = () => database.close()
  }))
}

function writeIndexedDraft(value: StoredDraft): Promise<void> {
  return openDatabase().then((database) => new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite")
    transaction.objectStore(STORE_NAME).put(value)
    transaction.oncomplete = () => {
      database.close()
      resolve()
    }
    transaction.onerror = () => {
      database.close()
      reject(transaction.error ?? new Error("IndexedDB draft could not be written"))
    }
    transaction.onabort = () => {
      database.close()
      reject(transaction.error ?? new Error("IndexedDB draft write was aborted"))
    }
  }))
}

function deleteIndexedDraft(accountId: string): Promise<void> {
  return openDatabase().then((database) => new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite")
    transaction.objectStore(STORE_NAME).delete(accountId)
    transaction.oncomplete = () => {
      database.close()
      resolve()
    }
    transaction.onerror = () => {
      database.close()
      reject(transaction.error ?? new Error("IndexedDB draft could not be deleted"))
    }
    transaction.onabort = () => {
      database.close()
      reject(transaction.error ?? new Error("IndexedDB draft delete was aborted"))
    }
  }))
}

function readLocalDraft(accountId: string): StoredDraft | null {
  try {
    const raw = window.localStorage.getItem(storageKey(accountId))
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (parsed === null || typeof parsed !== "object") return null
    const value = parsed as Partial<StoredDraft>
    const state = normalizeState(value.state)
    if (state === null) return null
    return {
      accountId,
      savedAt: typeof value.savedAt === "number" ? value.savedAt : Date.now(),
      sessionExpiresAt: typeof value.sessionExpiresAt === "number" ? value.sessionExpiresAt : null,
      state,
    }
  } catch {
    return null
  }
}

function writeLocalDraft(value: StoredDraft): void {
  try {
    window.localStorage.setItem(storageKey(value.accountId), JSON.stringify(value))
  } catch {
    // Device storage is best effort; the active in-memory journey remains usable.
  }
}

function removeLocalDraft(accountId: string): void {
  try {
    window.localStorage.removeItem(storageKey(accountId))
  } catch {
    // Device storage is best effort.
  }
}

function loadResult(value: StoredDraft | null): AdoptionDraftLoadResult {
  if (value === null) return { state: null, expired: false, sessionExpiresAt: null }
  const expired = value.sessionExpiresAt !== null && value.sessionExpiresAt <= Date.now()
  return {
    state: expired ? null : resumableState(value.state),
    expired,
    sessionExpiresAt: expired ? null : value.sessionExpiresAt,
  }
}

export async function loadAdoptionDraft(accountId: string): Promise<AdoptionDraftLoadResult> {
  await (pendingWrites.get(accountId) ?? Promise.resolve()).catch(() => undefined)
  try {
    const value = indexedDbAvailable()
      ? await readIndexedDraft(accountId)
      : readLocalDraft(accountId)
    const result = loadResult(value)
    if (result.expired) await clearAdoptionDraft(accountId)
    return result
  } catch {
    return loadResult(readLocalDraft(accountId))
  }
}

export function saveAdoptionDraft(
  accountId: string,
  state: AdoptionDraftState,
  sessionExpiresAt: number | null,
): Promise<void> {
  if (!state.dirty || state.screen === "arrival") return Promise.resolve()
  const value: StoredDraft = {
    accountId,
    savedAt: Date.now(),
    sessionExpiresAt,
    state: resumableState(state),
  }
  const previous = pendingWrites.get(accountId) ?? Promise.resolve()
  const write = previous
    .catch(() => undefined)
    .then(async () => {
      try {
        if (indexedDbAvailable()) await writeIndexedDraft(value)
        else writeLocalDraft(value)
      } catch {
        writeLocalDraft(value)
      }
    })
  pendingWrites.set(accountId, write)
  void write.finally(() => {
    if (pendingWrites.get(accountId) === write) pendingWrites.delete(accountId)
  })
  return write
}

export async function clearAdoptionDraft(accountId: string): Promise<void> {
  const previous = pendingWrites.get(accountId) ?? Promise.resolve()
  const clear = previous
    .catch(() => undefined)
    .then(async () => {
      removeLocalDraft(accountId)
      try {
        if (indexedDbAvailable()) await deleteIndexedDraft(accountId)
      } catch {
        // Device storage is best effort.
      }
    })
  pendingWrites.set(accountId, clear)
  try {
    await clear
  } finally {
    if (pendingWrites.get(accountId) === clear) pendingWrites.delete(accountId)
  }
}

export function adoptionSessionExpiryFromNow(): number {
  return Date.now() + ADOPTION_SESSION_TTL_MILLISECONDS
}
