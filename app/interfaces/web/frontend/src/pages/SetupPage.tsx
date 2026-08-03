import { useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import {
  setupInstall,
  setupModelCatalog,
  setupSaveNestDraft,
  setupSaveOfflineDraft,
  setupSaveOwnerDraft,
  setupStatus,
  type SetupModelOption,
  type SetupStatus,
} from "../api/client"
import { LanguageSwitcher } from "../components/LanguageSwitcher"
import { Notice } from "../components/Notice"
import { localizeApiError, type ErrorOperation } from "../i18n/errors"
import { currentLocale } from "../i18n/format"

type SetupStepNumber = 1 | 2 | 3 | 4
type SetupError =
  | { readonly kind: "api"; readonly operation: ErrorOperation; readonly reason: unknown }
  | { readonly kind: "local"; readonly key: "errors.bedCount" | "errors.passwordMismatch" }

const setupStepNumbers: readonly SetupStepNumber[] = [1, 2, 3, 4]
const fallbackModels: readonly SetupModelOption[] = [
  { model_id: "qwen2.5:0.5b", label: "qwen2.5:0.5b（推荐）", approx_download_mb: 398, recommended: true },
  { model_id: "qwen3.5:0.8b", label: "qwen3.5:0.8b", approx_download_mb: 1024, recommended: false },
  { model_id: "gemma3:270m", label: "gemma3:270m", approx_download_mb: 292, recommended: false },
]

function normalizeStep(value: number): SetupStepNumber {
  return value === 1 || value === 2 || value === 3 ? value : 4
}

function setupError(
  reason: unknown,
  operation: ErrorOperation,
): SetupError {
  return { kind: "api", operation, reason }
}

export function SetupPage() {
  const { i18n, t } = useTranslation("setup")
  const { t: commonT } = useTranslation("common")
  const [progress, setProgress] = useState<SetupStatus | null>(null)
  const [catalog, setCatalog] = useState<readonly SetupModelOption[]>(fallbackModels)
  const [step, setStep] = useState<SetupStepNumber>(1)
  const [accountId, setAccountId] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [password, setPassword] = useState("")
  const [passwordConfirmation, setPasswordConfirmation] = useState("")
  const [useLocalOllama, setUseLocalOllama] = useState(true)
  const [modelId, setModelId] = useState("qwen2.5:0.5b")
  const [bedCount, setBedCount] = useState(4)
  const [csrfToken, setCsrfToken] = useState("")
  const [error, setError] = useState<SetupError | null>(null)
  const [saving, setSaving] = useState(false)

  const applyStatus = (status: SetupStatus): void => {
    setProgress(status)
    if (status.csrf_token) setCsrfToken(status.csrf_token)
    if (status.locked) {
      setStep(4)
      return
    }
    setStep(normalizeStep(status.current_step))
    const draft = status.draft
    if (draft.owner_account_id !== null) setAccountId(draft.owner_account_id)
    if (draft.display_name !== null) setDisplayName(draft.display_name)
    if (draft.use_local_ollama !== null) setUseLocalOllama(draft.use_local_ollama)
    if (draft.model_id !== null) setModelId(draft.model_id)
    if (draft.bed_count !== null) setBedCount(draft.bed_count)
  }

  useEffect(() => {
    let cancelled = false
    const load = async (): Promise<void> => {
      try {
        const [status, models] = await Promise.all([setupStatus(), setupModelCatalog()])
        if (cancelled) return
        setCatalog(models)
        applyStatus(status)
      } catch (reason: unknown) {
        if (!cancelled) setError(setupError(reason, "setup.load"))
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!progress?.locked || progress.install.state === "completed") return
    let cancelled = false
    const timer = window.setInterval(() => {
      void setupStatus().then((status) => {
        if (!cancelled) applyStatus(status)
      }).catch((reason: unknown) => {
        if (!cancelled) setError(setupError(reason, "setup.load"))
      })
    }, 1200)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [progress?.locked, progress?.install.state])

  const saveStatus = async (
    action: () => Promise<SetupStatus>,
    operation: ErrorOperation = "setup.save",
  ): Promise<void> => {
    setSaving(true)
    setError(null)
    try {
      applyStatus(await action())
    } catch (reason: unknown) {
      setError(setupError(reason, operation))
    } finally {
      setSaving(false)
    }
  }

  const submitOwner = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault()
    if (password !== passwordConfirmation) {
      setError({ kind: "local", key: "errors.passwordMismatch" })
      return
    }
    void saveStatus(() => setupSaveOwnerDraft(
      accountId.trim(),
      displayName.trim(),
      password.trim() || null,
      passwordConfirmation.trim() || null,
      csrfToken,
    ))
  }

  const saveOffline = (): void => {
    void saveStatus(() => setupSaveOfflineDraft(
      useLocalOllama,
      useLocalOllama ? modelId : null,
      csrfToken,
    ))
  }

  const saveNest = (): void => {
    if (!Number.isInteger(bedCount) || bedCount < 4 || bedCount > 32) {
      setError({ kind: "local", key: "errors.bedCount" })
      return
    }
    void saveStatus(() => setupSaveNestDraft(bedCount, csrfToken))
  }

  const confirmInstall = (): void => {
    void saveStatus(() => setupInstall(csrfToken), "setup.install")
  }

  const currentStep = progress?.locked ? 4 : step
  const draft = progress?.draft
  const install = progress?.install
  const isInstalling = progress?.locked === true
  const model = catalog.find((option) => option.model_id === (draft?.model_id ?? modelId))
  const ollamaInstalled = draft?.ollama_installed === true
  const ollamaStatus = ollamaInstalled ? t("offline.installed") : t("offline.notInstalled")
  const stepCopy = {
    1: { label: "steps.owner.label", title: "steps.owner.title", description: "steps.owner.description" },
    2: { label: "steps.offline.label", title: "steps.offline.title", description: "steps.offline.description" },
    3: { label: "steps.nest.label", title: "steps.nest.title", description: "steps.nest.description" },
    4: { label: "steps.review.label", title: "steps.review.title", description: "steps.review.description" },
  } as const

  const renderReview = () => <section className="setup-form setup-review">
    <div className="setup-review-row" data-testid="setup-review-row">
      <div><strong>{t("review.owner")}</strong><span>{accountId || t("review.notConfigured")}</span></div>
      {!isInstalling && <button className="button button--quiet" onClick={() => setStep(1)} type="button">{t("review.modify")}</button>}
    </div>
    <div className="setup-review-row" data-testid="setup-review-row">
      <div><strong>{t("review.ollama")}</strong><span>{useLocalOllama ? t("review.enabled") : t("review.disabled")} · {ollamaStatus}</span></div>
      {!isInstalling && <button className="button button--quiet" onClick={() => setStep(2)} type="button">{t("review.modify")}</button>}
    </div>
    <div className="setup-review-row" data-testid="setup-review-row">
      <div><strong>{t("review.model")}</strong><span>{useLocalOllama ? (model?.model_id ?? modelId) : t("review.modelDisabled")}</span></div>
      {!isInstalling && <button className="button button--quiet" onClick={() => setStep(2)} type="button">{t("review.modify")}</button>}
    </div>
    <div className="setup-review-row" data-testid="setup-review-row">
      <div><strong>{t("review.beds")}</strong><span>{bedCount}</span></div>
      {!isInstalling && <button className="button button--quiet" onClick={() => setStep(3)} type="button">{t("review.modify")}</button>}
    </div>
    {!isInstalling && <div className="setup-actions"><button className="button" disabled={saving || !csrfToken} onClick={confirmInstall} type="button">{t("review.confirm")}</button></div>}
  </section>

  const renderInstall = () => {
    const phase = install?.phase ?? "owner"
    const action = install?.action_key ?? "idle"
    const actionKeys = {
      "ollama.check": "install.actions.ollama.check",
      "ollama.install": "install.actions.ollama.install",
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
      {install?.state === "failed" && <div className="setup-actions"><button className="button" disabled={saving} onClick={confirmInstall} type="button">{t("install.retry")}</button></div>}
      {install?.state === "completed" && <div className="setup-actions"><button className="button" onClick={() => window.location.assign("/manage")} type="button">{t("install.enter")}</button></div>}
    </section>
  }

  return <main className="setup-page">
    <aside className="setup-rail">
      <div className="setup-brand">
        <span aria-hidden="true" className="setup-brand__mark">EN</span>
        <span><strong>ELFIE NEST</strong><small>{t("rail.productLabel")}</small></span>
      </div>
      <div className="setup-rail__intro">
        <p className="brand">{t("rail.brand")}</p>
        <p>{t("rail.description")}</p>
      </div>
      <ol aria-label={t("rail.stepsLabel")} className="setup-steps">
        {setupStepNumbers.map((stepNumber) => {
          const storedStep = progress?.steps.find((item) => item.number === stepNumber)
          const completed = storedStep?.status === "completed"
          const current = stepNumber === currentStep
          return <li className={completed ? "setup-step setup-step--completed" : current ? "setup-step setup-step--current" : "setup-step"} key={stepNumber}>
            <span aria-hidden="true" className="setup-step__number">{completed ? "✓" : stepNumber}</span>
            <span><strong>{t(stepCopy[stepNumber].label)}</strong><small>{completed ? t("rail.saved") : current ? t("rail.current") : t("rail.pending")}</small></span>
          </li>
        })}
      </ol>
      <p className="setup-rail__footnote">{t("rail.footnote")}</p>
    </aside>
    <section className="setup-main">
      <section aria-label={commonT("language.label")} className="setup-locale-control"><LanguageSwitcher variant="compact" /></section>
      <section aria-labelledby="setup-title" className="panel setup-card">
        <header className="setup-card__header">
          <p className="brand">{t("progress.stepCount", { current: currentStep, total: 4 })}</p>
          <h1 className="setup-card__title" id="setup-title">{isInstalling ? t("install.title") : t(stepCopy[currentStep].title)}</h1>
          <p>{isInstalling ? t("install.description") : t(stepCopy[currentStep].description)}</p>
        </header>
        <div className="setup-card__content">
          {isInstalling ? renderInstall() : currentStep === 1 && <form className="setup-form" onSubmit={submitOwner}>
            <label>{t("owner.fields.accountId")}<input autoComplete="username" minLength={3} onChange={(event) => setAccountId(event.target.value)} required value={accountId} /></label>
            <label>{t("owner.fields.displayName")}<input autoComplete="name" onChange={(event) => setDisplayName(event.target.value)} required value={displayName} /></label>
            <label>{t("owner.fields.password")}<input autoComplete="new-password" minLength={6} onChange={(event) => setPassword(event.target.value)} required={!draft?.password_configured} type="password" value={password} /></label>
            <label>{t("owner.fields.confirmPassword")}<input autoComplete="new-password" minLength={6} onChange={(event) => setPasswordConfirmation(event.target.value)} required={!draft?.password_configured} type="password" value={passwordConfirmation} /></label>
            <div className="setup-actions"><button className="button" disabled={saving || !csrfToken} type="submit">{saving ? t("owner.submitting") : t("owner.action")}</button></div>
          </form>}
          {!isInstalling && currentStep === 2 && <section className="setup-form">
            <p className="setup-callout">{t("offline.callout")}</p>
            <label className="setup-check"><input checked={useLocalOllama} onChange={(event) => setUseLocalOllama(event.target.checked)} type="checkbox" />{t("offline.useLocal")}</label>
            <p className="setup-hint">{ollamaStatus}</p>
            <label className="setup-field">{t("offline.model")}
              <select aria-label={t("offline.model")} disabled={!useLocalOllama} onChange={(event) => setModelId(event.target.value)} value={modelId}>
                {catalog.map((option) => <option key={option.model_id} value={option.model_id}>{option.label}</option>)}
              </select>
            </label>
            <p className="setup-model-status">{useLocalOllama ? t("offline.modelStatus", { size: model?.approx_download_mb ?? 0 }) : t("offline.modelDisabled")}</p>
            <div className="setup-actions"><button className="button" disabled={saving || !csrfToken || (useLocalOllama && !modelId)} onClick={saveOffline} type="button">{t("offline.action")}</button></div>
          </section>}
          {!isInstalling && currentStep === 3 && <section className="setup-form">
            <p className="setup-callout">{t("nest.callout")}</p>
            <label>{t("nest.fields.bedCount")}<input max={32} min={4} onChange={(event) => setBedCount(Number.isFinite(event.currentTarget.valueAsNumber) ? event.currentTarget.valueAsNumber : 0)} type="number" value={bedCount} /></label>
            <div className="setup-actions"><button className="button" disabled={saving || !csrfToken} onClick={saveNest} type="button">{t("nest.action")}</button></div>
          </section>}
          {!isInstalling && currentStep === 4 && renderReview()}
          {error ? <Notice kind="error" message={error.kind === "local" ? t(error.key) : localizeApiError(error.reason, error.operation, currentLocale(i18n))} /> : null}
        </div>
      </section>
    </section>
  </main>
}
