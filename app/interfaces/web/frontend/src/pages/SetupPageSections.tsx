import type { TFunction } from "i18next"

import type { SetupStatus } from "../api/setup"

type SetupTranslation = TFunction<"setup">
type SetupPhase = "model_validation" | "common_food" | "nest" | "runtime"

type SetupCompletionProps = {
  readonly completed: boolean
  readonly foodConfigured: boolean
  readonly install: SetupStatus["install"] | undefined
  readonly lastError: string | null
  readonly requestFailed: boolean
  readonly saving: boolean
  readonly t: SetupTranslation
  readonly onEnter: () => void
  readonly onRetry: () => void
}

function validationProgress(actionKey: string): { readonly passed: number; readonly total: number } | null {
  const match = /^model\.validation\.complete:(\d+):(\d+)$/.exec(actionKey)
  if (match === null) return null
  return { passed: Number(match[1]), total: Number(match[2]) }
}

function currentAction(
  phase: SetupPhase,
  actionKey: string,
  t: SetupTranslation,
): string {
  const progress = validationProgress(actionKey)
  if (progress !== null) return t("completion.validationProgress", progress)
  if (actionKey === "model.validation.start") return t("completion.validationRunning")
  if (actionKey === "model.validation.skipped") return t("completion.phaseSkipped")
  if (actionKey === "food.common.start") return t("completion.foodRunning")
  if (actionKey === "food.common.complete") return t("completion.foodDone")
  if (actionKey === "food.common.skipped") return t("completion.phaseSkipped")
  if (actionKey === "nest.initialize") return t("completion.nestRunning")
  if (actionKey === "account.default_landing.start") return t("completion.defaultLandingRunning")
  if (actionKey === "account.default_landing.complete") return t("completion.defaultLandingDone")
  if (actionKey === "runtime.ready.start") return t("completion.runtimeRunning")
  if (actionKey === "runtime.ready.complete") return t("completion.runtimeDone")
  return t(`completion.phase.${phase}`)
}

export function SetupCompletion({
  completed,
  foodConfigured,
  install,
  lastError,
  requestFailed,
  saving,
  t,
  onEnter,
  onRetry,
}: SetupCompletionProps) {
  const state = install?.state ?? "idle"
  const failed = !completed && (requestFailed || state === "failed" || state === "cancelled")
  const progress = Math.max(0, Math.min(100, install?.progress ?? 0))
  const activePhase = (install?.phase ?? "model_validation") as SetupPhase
  const action = currentAction(activePhase, install?.action_key ?? "", t)
  const statusText = completed ? t("completion.title") : failed ? t("completion.failed") : action

  return <section className="setup-form setup-install">
    <div aria-label={t("completion.progressLabel")} aria-valuemax={100} aria-valuemin={0} aria-valuenow={progress} className="setup-progress" role="progressbar">
      <span className="setup-progress__bar" style={{ width: `${progress}%` }} />
    </div>
    <p aria-live="polite" className="setup-task">[{progress}%] {statusText}</p>
    {failed && lastError ? <p className="setup-install-error" role="alert">{lastError}</p> : null}
    {failed ? <div className="setup-actions">
      <button className="button" disabled={saving} onClick={onRetry} type="button">{t("completion.retry")}</button>
      <button className="button button--quiet" disabled={saving} onClick={onEnter} type="button">{t("completion.manage")}</button>
    </div> : null}
    {completed ? <div className="setup-actions setup-install__complete-actions">
      <button className="button" onClick={onEnter} type="button">{t(foodConfigured ? "completion.adopt" : "completion.manage")}</button>
    </div> : null}
  </section>
}
