/**
 * Opt-in timing diagnostics for the adoption candidate generation wait.
 *
 * Enabled per session with `?adoptionTiming=1` in the URL or
 * `localStorage["elfienest.adoption-timing"] = "1"`. While disabled every
 * call is a no-op, so production sessions keep their console and the
 * `window.__adoptionTiming` state stays inert.
 */

const TIMING_FLAG_STORAGE_KEY = "elfienest.adoption-timing"
const TIMING_URL_PARAM = "adoptionTiming"
const CONSOLE_PREFIX = "[adoption-timing]"

export type AdoptionTimingSpan = {
  readonly end: () => void
}

export type AdoptionTimingSnapshot = {
  readonly enabled: boolean
  readonly marks: Readonly<Record<string, number>>
  readonly phases: Readonly<Record<string, number>>
}

type AdoptionTimingState = {
  enabled: boolean
  marks: Record<string, number>
  phases: Record<string, number>
}

function timingEnabled(): boolean {
  try {
    if (window.localStorage.getItem(TIMING_FLAG_STORAGE_KEY) === "1") return true
    return new URLSearchParams(window.location.search).has(TIMING_URL_PARAM)
  } catch {
    return false
  }
}

function currentState(): AdoptionTimingState {
  const existing = window.__adoptionTiming
  if (existing !== undefined) return existing
  const state: AdoptionTimingState = {
    enabled: timingEnabled(),
    marks: {},
    phases: {},
  }
  window.__adoptionTiming = state
  return state
}

export function adoptionTimingEnabled(): boolean {
  return currentState().enabled
}

/** Record a moment in time (performance.now) under `name`. */
export function markAdoptionTiming(name: string): void {
  const state = currentState()
  if (!state.enabled) return
  const at = performance.now()
  state.marks[name] = at
  console.info(`${CONSOLE_PREFIX} mark ${name} at ${at.toFixed(1)}ms`)
}

/** Measure one phase; the duration is recorded when `end()` is called. */
export function beginAdoptionTimingPhase(name: string): AdoptionTimingSpan {
  const state = currentState()
  if (!state.enabled) {
    return { end: () => undefined }
  }
  const startedAt = performance.now()
  return {
    end: () => {
      const duration = performance.now() - startedAt
      state.phases[name] = duration
      console.info(`${CONSOLE_PREFIX} ${name} ${duration.toFixed(1)}ms`)
    },
  }
}

/** Copy of the collected diagnostics, safe to read from devtools. */
export function readAdoptionTiming(): AdoptionTimingSnapshot {
  const state = currentState()
  return {
    enabled: state.enabled,
    marks: { ...state.marks },
    phases: { ...state.phases },
  }
}

/** Log one consolidated JSON line covering everything collected so far. */
export function logAdoptionTimingSummary(label: string): void {
  const state = currentState()
  if (!state.enabled) return
  console.info(`${CONSOLE_PREFIX} summary ${label} ${JSON.stringify({
    marks: state.marks,
    phases: state.phases,
  })}`)
}

declare global {
  interface Window {
    __adoptionTiming?: AdoptionTimingState
  }
}
