import { useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import { Checkbox } from "@/components/ui/checkbox"

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
import { NumberField } from "../components/NumberField"
import { SelectField } from "../components/SelectField"
import { TextField } from "../components/TextField"
import { localizeApiError, type ErrorOperation } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { SetupInstall, SetupReview } from "./SetupPageSections"
import { SetupWelcome } from "./SetupWelcome"

type SetupStepNumber = 1 | 2 | 3 | 4
type SetupError =
  | { readonly kind: "api"; readonly operation: ErrorOperation; readonly reason: unknown }
  | { readonly kind: "local"; readonly key: "errors.bedCount" | "errors.passwordMismatch" }

const setupStepNumbers: readonly SetupStepNumber[] = [1, 2, 3, 4]
const setupFullLogoUrl = new URL("../../../../../../docs/public/assets/elfienest-full-logo-transparent.png", import.meta.url).href

function normalizeStep(value: number): SetupStepNumber {
  return value === 1 || value === 2 || value === 3 ? value : 4
}

function isFreshSetup(status: SetupStatus): boolean {
  return status.need_setup && !status.locked && status.current_step === 1 && !status.draft.owner_configured && status.draft.owner_account_id === null
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
  const [catalog, setCatalog] = useState<readonly SetupModelOption[]>([])
  const [step, setStep] = useState<SetupStepNumber>(1)
  const [accountId, setAccountId] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [password, setPassword] = useState("")
  const [passwordConfirmation, setPasswordConfirmation] = useState("")
  const [useLocalOllama, setUseLocalOllama] = useState(true)
  const [modelId, setModelId] = useState("")
  const [bedCount, setBedCount] = useState(4)
  const [csrfToken, setCsrfToken] = useState("")
  const [error, setError] = useState<SetupError | null>(null)
  const [saving, setSaving] = useState(false)
  const [welcomeDismissed, setWelcomeDismissed] = useState(false)
  const bedCountIsInvalid = !Number.isInteger(bedCount) || bedCount < 4 || bedCount > 32

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
        if (status.draft.model_id !== null) setModelId(status.draft.model_id)
        else if (models[0] !== undefined) setModelId(models[0].model_id)
        applyStatus(status)
      } catch (reason: unknown) {
        if (reason instanceof Error) {
          if (!cancelled) setError(setupError(reason, "setup.load"))
        } else if (!cancelled) {
          setError(setupError(reason, "setup.load"))
        }
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
        if (reason instanceof Error) {
          if (!cancelled) setError(setupError(reason, "setup.load"))
        } else if (!cancelled) {
          setError(setupError(reason, "setup.load"))
        }
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
      if (reason instanceof Error) {
        setError(setupError(reason, operation))
      } else {
        setError(setupError(reason, operation))
      }
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
    if (bedCountIsInvalid) {
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
  const showWelcome = progress !== null && isFreshSetup(progress) && !welcomeDismissed
  const model = catalog.find((option) => option.model_id === (draft?.model_id ?? modelId))
  const ollamaInstalled = draft?.ollama_installed === true
  const ollamaStatus = ollamaInstalled ? t("offline.installed") : t("offline.notInstalled")
  const stepCopy = {
    1: { label: "steps.owner.label", title: "steps.owner.title" },
    2: { label: "steps.offline.label", title: "steps.offline.title" },
    3: { label: "steps.nest.label", title: "steps.nest.title" },
    4: { label: "steps.review.label", title: "steps.review.title" },
  } as const

  if (showWelcome) {
    return <main className="setup-welcome-page">
      <section aria-label={commonT("language.label")} className="setup-locale-control"><LanguageSwitcher variant="compact" /></section>
      <SetupWelcome action={t("welcome.action")} onContinue={() => setWelcomeDismissed(true)} title={t("welcome.title")} />
    </main>
  }

  return <main className="setup-page">
    <aside className="setup-rail">
      <div className="setup-brand">
        <img alt="ELFIE NEST" className="setup-brand__logo" src={setupFullLogoUrl} />
      </div>
      <div className="setup-rail__intro">
        <p className="brand">{t("rail.brand")}</p>
      </div>
      <ol aria-label={t("rail.stepsLabel")} className="setup-steps">
        {setupStepNumbers.map((stepNumber) => {
          const storedStep = progress?.steps.find((item) => item.number === stepNumber)
          const completed = storedStep?.status === "completed"
          const current = stepNumber === currentStep
          const stateClassName = current ? "setup-step--current" : completed ? "setup-step--completed" : ""
          return <li className={`setup-step ${stateClassName}`} key={stepNumber}>
            <button aria-current={current ? "step" : undefined} className="setup-step__button" disabled={!completed || isInstalling || current} onClick={() => setStep(stepNumber)} type="button">
              <span aria-hidden="true" className="setup-step__number">{completed ? "✓" : stepNumber}</span>
              <span><strong>{t(stepCopy[stepNumber].label)}</strong><small>{completed ? t("rail.saved") : current ? t("rail.current") : t("rail.pending")}</small></span>
            </button>
          </li>
        })}
      </ol>
    </aside>
    <section className="setup-main">
      <section aria-label={commonT("language.label")} className="setup-locale-control"><LanguageSwitcher variant="compact" /></section>
      <section aria-labelledby="setup-title" className="panel setup-card">
        <header className="setup-card__header">
          <p className="brand">{t("progress.stepCount", { current: currentStep, total: 4 })}</p>
          <h1 className="setup-card__title" id="setup-title">{isInstalling ? t("install.title") : t(stepCopy[currentStep].title)}</h1>
        </header>
        <div className="setup-card__content">
          {isInstalling ? <SetupInstall draft={draft} install={install} model={model} modelId={modelId} onConfirmInstall={confirmInstall} onEnterManage={() => window.location.assign("/manage")} saving={saving} t={t} /> : currentStep === 1 && <form className="setup-form setup-form--owner" onSubmit={submitOwner}>
            <TextField autoComplete="username" label={t("owner.fields.accountId")} minLength={3} onChange={setAccountId} required value={accountId} />
            <TextField autoComplete="name" label={t("owner.fields.displayName")} onChange={setDisplayName} required value={displayName} />
            <TextField {...(draft?.password_configured ? { placeholder: t("owner.passwordConfiguredPlaceholder") } : {})} autoComplete="new-password" label={t("owner.fields.password")} minLength={6} onChange={setPassword} required={!draft?.password_configured} type="password" value={password} />
            <TextField {...(draft?.password_configured ? { placeholder: t("owner.passwordConfiguredPlaceholder") } : {})} autoComplete="new-password" label={t("owner.fields.confirmPassword")} minLength={6} onChange={setPasswordConfirmation} required={!draft?.password_configured} type="password" value={passwordConfirmation} />
            <div className="setup-actions"><button className="button" disabled={saving || !csrfToken} type="submit">{saving ? t("owner.submitting") : t("owner.action")}</button></div>
          </form>}
          {!isInstalling && currentStep === 2 && <section className="setup-form setup-form--offline">
            <div className="setup-check setup-check--row"><span id="setup-use-local-label">{t("offline.useLocal")}</span><Checkbox aria-labelledby="setup-use-local-label" checked={useLocalOllama} onCheckedChange={(checked) => setUseLocalOllama(checked === true)} /></div>
            <p className={`setup-hint setup-hint--status ${ollamaInstalled ? "setup-hint--installed" : "setup-hint--missing"}`}>{ollamaStatus}</p>
            <div className="setup-field--row"><SelectField disabled={!useLocalOllama} label={t("offline.model")} onValueChange={setModelId} options={catalog.map((option) => ({ label: option.label, value: option.model_id }))} value={modelId} /></div>
            <p className="setup-model-status">{useLocalOllama ? t("offline.modelStatus", { size: model?.approx_download_mb ?? 0 }) : t("offline.modelDisabled")}</p>
            <div className="setup-actions"><button className="button" disabled={saving || !csrfToken || (useLocalOllama && !modelId)} onClick={saveOffline} type="button">{t("offline.action")}</button></div>
          </section>}
          {!isInstalling && currentStep === 3 && <section className="setup-form setup-form--bed-count">
            <NumberField
              clampOnBlur={false}
              error={bedCountIsInvalid ? t("errors.bedCount") : undefined}
              label={t("nest.fields.bedCount")}
              max={32}
              min={4}
              onChange={setBedCount}
              onDraftChange={(draftValue) => {
                const parsed = Number(draftValue)
                setBedCount(Number.isFinite(parsed) ? parsed : 0)
              }}
              value={bedCount}
            />
            <div className="setup-actions"><button className="button" disabled={saving || !csrfToken || bedCountIsInvalid} onClick={saveNest} type="button">{t("nest.action")}</button></div>
          </section>}
          {!isInstalling && currentStep === 4 && <SetupReview accountId={accountId} bedCount={bedCount} csrfToken={csrfToken} isInstalling={isInstalling} model={model} modelId={modelId} ollamaStatus={ollamaStatus} onConfirmInstall={confirmInstall} onStepChange={setStep} saving={saving} t={t} useLocalOllama={useLocalOllama} />}
          {error ? <Notice kind="error" message={error.kind === "local" ? t(error.key) : localizeApiError(error.reason, error.operation, currentLocale(i18n))} /> : null}
        </div>
      </section>
    </section>
  </main>
}
