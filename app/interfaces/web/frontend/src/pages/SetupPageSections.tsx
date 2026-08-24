import type { TFunction } from "i18next"

import type { SetupModelOption, SetupStatus } from "../api/setup"

type SetupTranslation = TFunction<"setup">
type SetupStepNumber = 1 | 2 | 3 | 4

type SetupReviewProps = {
  readonly accountId: string
  readonly bedCount: number
  readonly csrfToken: string
  readonly isInstalling: boolean
  readonly model: SetupModelOption | undefined
  readonly modelId: string
  readonly ollamaStatus: string
  readonly saving: boolean
  readonly t: SetupTranslation
  readonly useLocalOllama: boolean
  readonly onConfirmInstall: () => void
  readonly onStepChange: (step: SetupStepNumber) => void
}

export function SetupReview({
  accountId,
  bedCount,
  csrfToken,
  isInstalling,
  model,
  modelId,
  ollamaStatus,
  saving,
  t,
  useLocalOllama,
  onConfirmInstall,
  onStepChange,
}: SetupReviewProps) {
  return <section className="setup-form setup-review">
    <div className="setup-review-row" data-testid="setup-review-row">
      <div><strong>{t("review.owner")}</strong><span>{accountId || t("review.notConfigured")}</span></div>
      {!isInstalling && <button className="button button--quiet" onClick={() => onStepChange(1)} type="button">{t("review.modify")}</button>}
    </div>
    <div className="setup-review-row" data-testid="setup-review-row">
      <div><strong>{t("review.ollama")}</strong><span>{useLocalOllama ? t("review.enabled") : t("review.disabled")} · {ollamaStatus}</span></div>
      {!isInstalling && <button className="button button--quiet" onClick={() => onStepChange(2)} type="button">{t("review.modify")}</button>}
    </div>
    <div className="setup-review-row" data-testid="setup-review-row">
      <div><strong>{t("review.model")}</strong><span>{useLocalOllama ? (model?.model_id ?? modelId) : t("review.modelDisabled")}</span></div>
      {!isInstalling && <button className="button button--quiet" onClick={() => onStepChange(2)} type="button">{t("review.modify")}</button>}
    </div>
    <div className="setup-review-row" data-testid="setup-review-row">
      <div><strong>{t("review.beds")}</strong><span>{bedCount}</span></div>
      {!isInstalling && <button className="button button--quiet" onClick={() => onStepChange(3)} type="button">{t("review.modify")}</button>}
    </div>
    {!isInstalling && <div className="setup-actions"><button className="button" disabled={saving || !csrfToken} onClick={onConfirmInstall} type="button">{t("review.confirm")}</button></div>}
  </section>
}

type SetupInstallProps = {
  readonly draft: SetupStatus["draft"] | undefined
  readonly install: SetupStatus["install"] | undefined
  readonly model: SetupModelOption | undefined
  readonly modelId: string
  readonly saving: boolean
  readonly t: SetupTranslation
  readonly onConfirmInstall: () => void
  readonly onEnterManage: () => void
}

export function SetupInstall({
  draft,
  install,
  model,
  modelId,
  saving,
  t,
  onConfirmInstall,
  onEnterManage,
}: SetupInstallProps) {
  const phase = install?.phase ?? "owner"
  const action = install?.action_key ?? "idle"
  const actionKeys = {
    "ollama.check": "install.actions.ollama.check",
    "ollama.install": "install.actions.ollama.install",
    "ollama.manual": "install.actions.ollama.manual",
    "ollama.repair": "install.actions.ollama.repair",
    "ollama.reuse": "install.actions.ollama.reuse",
    "ollama.start": "install.actions.ollama.start",
    "ollama.skipped": "install.actions.ollama.skipped",
    "model.check": "install.actions.model.check",
    "model.download": "install.actions.model.download",
    "model.reuse": "install.actions.model.reuse",
    "model.skipped": "install.actions.model.skipped",
    "food.check": "install.actions.food.check",
    "food.emergency": "install.actions.food.emergency",
    "food.skipped": "install.actions.food.skipped",
    "nest.configure": "install.actions.nest.configure",
    "nest.apply": "install.actions.nest.configure",
    "owner.create": "install.actions.owner.create",
  } as const
  const phaseActionKeys = {
    owner: "install.actions.owner.create",
    ollama: "install.actions.ollama.check",
    model: "install.actions.model.check",
    emergency_food: "install.actions.food.check",
    nest: "install.actions.nest.configure",
  } as const
  const actionKey = Object.prototype.hasOwnProperty.call(actionKeys, action)
    ? actionKeys[action as keyof typeof actionKeys]
    : phaseActionKeys[phase] ?? "install.actions.preparing"
  const selectedModel = model?.model_id ?? draft?.model_id ?? modelId
  const actionText = action.startsWith("model.")
    ? t(actionKey, { model: selectedModel })
    : t(actionKey)
  const statusText = install?.state === "failed"
    ? t("install.failed")
    : install?.state === "completed"
      ? t("install.completed")
      : actionText
  const progressValue = install?.progress ?? 0
  return <section className="setup-form setup-install">
    <div aria-valuemax={100} aria-valuemin={0} aria-valuenow={progressValue} className="setup-progress" role="progressbar">
      <span className="setup-progress__bar" style={{ width: `${progressValue}%` }} />
    </div>
    <p aria-live="polite" className="setup-task">[{progressValue}%] {statusText}</p>
    {install?.state === "failed" && <div className="setup-actions"><button className="button" disabled={saving} onClick={onConfirmInstall} type="button">{t("install.retry")}</button></div>}
    {install?.state === "completed" && <div className="setup-actions"><button className="button" onClick={onEnterManage} type="button">{t("install.enter")}</button></div>}
  </section>
}
