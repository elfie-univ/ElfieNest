import { useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import {
  currentUser,
  setup,
  setupBindExistingOllama,
  setupComplete,
  setupConfiguredModel,
  setupInstallOfficialOllama,
  setupModelRecommendation,
  setupNest,
  setupPullModel,
  setupSkipModel,
  setupSkipOllama,
  setupStatus,
  type SetupModelRecommendation,
  type SetupStatus,
} from "../api/client"
import { LanguageSwitcher } from "../components/LanguageSwitcher"
import { Notice } from "../components/Notice"
import { TextField } from "../components/TextField"
import { localizeApiError, type ErrorOperation } from "../i18n/errors"
import { currentLocale } from "../i18n/format"

type SetupStepNumber = 1 | 2 | 3 | 4 | 5
type SetupError =
  | { readonly kind: "api"; readonly operation: ErrorOperation; readonly reason: unknown }
  | { readonly kind: "local"; readonly key: "errors.bedCount" | "errors.passwordMismatch" }
const setupStepNumbers: readonly SetupStepNumber[] = [1, 2, 3, 4, 5]
type SetupStepCopyKey = `steps.${"owner" | "ollama" | "nest" | "model" | "finish"}.${"label" | "title" | "description"}`

const setupStepCopy = {
  1: { description: "steps.owner.description", label: "steps.owner.label", title: "steps.owner.title" },
  2: { description: "steps.ollama.description", label: "steps.ollama.label", title: "steps.ollama.title" },
  3: { description: "steps.nest.description", label: "steps.nest.label", title: "steps.nest.title" },
  4: { description: "steps.model.description", label: "steps.model.label", title: "steps.model.title" },
  5: { description: "steps.finish.description", label: "steps.finish.label", title: "steps.finish.title" },
} satisfies Record<SetupStepNumber, {
  readonly description: SetupStepCopyKey
  readonly label: SetupStepCopyKey
  readonly title: SetupStepCopyKey
}>

function normalizeSetupStep(value: number | undefined): SetupStepNumber {
  switch (value) {
    case 2: return 2
    case 3: return 3
    case 4: return 4
    case 5: return 5
    default: return 1
  }
}

export function SetupPage() {
  const { i18n, t } = useTranslation("setup")
  const [username, setUsername] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [password, setPassword] = useState("")
  const [passwordConfirmation, setPasswordConfirmation] = useState("")
  const [bedCount, setBedCount] = useState(4)
  const [ollamaEndpoint, setOllamaEndpoint] = useState("http://127.0.0.1:11434")
  const [ollamaInstallConfirmed, setOllamaInstallConfirmed] = useState(false)
  const [progress, setProgress] = useState<SetupStatus | null>(null)
  const [modelRecommendation, setModelRecommendation] = useState<SetupModelRecommendation | null>(null)
  const [modelReference, setModelReference] = useState("")
  const [modelPullConfirmed, setModelPullConfirmed] = useState(false)
  const [csrfToken, setCsrfToken] = useState("")
  const [error, setError] = useState<SetupError | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const load = (): void => {
      void Promise.all([setupStatus(), currentUser().catch(() => null)])
        .then(([status, user]) => {
          setProgress(status)
          if (user?.csrf_token) setCsrfToken(user.csrf_token)
        })
        .catch((reason: unknown) => setError({ kind: "api", operation: "setup.load", reason }))
    }
    load()
    const timer = window.setInterval(load, 2000)
    return () => window.clearInterval(timer)
  }, [i18n])

  useEffect(() => {
    if (progress?.current_step !== 4) return
    void setupModelRecommendation().then(setModelRecommendation).catch(() => setModelRecommendation(null))
  }, [progress?.current_step])

  const submitOwner = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (password !== passwordConfirmation) {
      setError({ key: "errors.passwordMismatch", kind: "local" })
      return
    }
    setSaving(true)
    setError(null)
    try {
      const result = await setup(username.trim(), password, displayName.trim())
      setCsrfToken(result.csrf_token)
      setProgress(await setupStatus())
    } catch (reason: unknown) {
      setError({ kind: "api", operation: "setup.save", reason })
    } finally {
      setSaving(false)
    }
  }

  const completeStep = async (
    action: () => Promise<SetupStatus>,
    operation: ErrorOperation,
  ): Promise<void> => {
    setSaving(true)
    setError(null)
    try {
      const status = await action()
      setProgress(status)
      if (status.complete) window.location.assign("/manage")
    } catch (reason: unknown) {
      setError({ kind: "api", operation, reason })
    } finally {
      setSaving(false)
    }
  }

  const saveNest = (): void => {
    if (!Number.isInteger(bedCount) || bedCount < 4 || bedCount > 32) {
      setError({ key: "errors.bedCount", kind: "local" })
      return
    }
    void completeStep(() => setupNest(bedCount, csrfToken), "setup.save")
  }

  const currentStep = normalizeSetupStep(progress?.current_step)
  const currentStepCopy = setupStepCopy[currentStep]
  const runningTask = progress?.task?.state === "running" ? progress.task : null

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
          const storedStep = progress?.steps.find((step) => step.number === stepNumber)
          const completed = storedStep?.status === "completed"
          const current = stepNumber === currentStep
          const className = completed
            ? "setup-step setup-step--completed"
            : current ? "setup-step setup-step--current" : "setup-step"
          return <li className={className} key={stepNumber}>
            <span aria-hidden="true" className="setup-step__number">{completed ? "✓" : stepNumber}</span>
            <span><strong>{t(setupStepCopy[stepNumber].label)}</strong><small>{completed ? t("rail.saved") : current ? t("rail.current") : t("rail.pending")}</small></span>
          </li>
        })}
      </ol>
      <p className="setup-rail__footnote">{t("rail.footnote")}</p>
    </aside>
    <section className="setup-main">
      <section aria-labelledby="setup-title" className="panel setup-card">
        <header className="setup-card__header">
          <p className="brand">{t("progress.stepCount", { current: currentStep, total: 5 })}</p>
          <h1 id="setup-title">{t(currentStepCopy.title)}</h1>
          <p>{t(currentStepCopy.description)}</p>
          <LanguageSwitcher />
        </header>
        <div className="setup-card__content">
          {currentStep === 1 && <form className="setup-form" onSubmit={(event) => { void submitOwner(event) }}>
            <label>{t("owner.fields.username")}<input autoComplete="username" minLength={3} onChange={(event) => setUsername(event.target.value)} required value={username} /></label>
            <label>{t("owner.fields.displayName")}<input autoComplete="name" onChange={(event) => setDisplayName(event.target.value)} required value={displayName} /></label>
            <label>{t("owner.fields.password")}<input autoComplete="new-password" minLength={6} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /></label>
            <label>{t("owner.fields.confirmPassword")}<input autoComplete="new-password" minLength={6} onChange={(event) => setPasswordConfirmation(event.target.value)} required type="password" value={passwordConfirmation} /></label>
            <div className="setup-actions"><button className="button" disabled={saving} type="submit">{saving ? t("owner.submitting") : t("owner.action")}</button></div>
          </form>}
          {currentStep === 2 && <section className="setup-form">
            <p className="setup-callout">{t("ollama.callout")}</p>
            <TextField label={t("ollama.fields.endpoint")} onChange={setOllamaEndpoint} type="url" value={ollamaEndpoint} />
            {runningTask?.step === 2 ? <p className="setup-task">{t("ollama.running", { progress: runningTask.progress })}<span>{t("ollama.runningHint")}</span></p> : <>
              <label className="setup-check"><input checked={ollamaInstallConfirmed} onChange={(event) => setOllamaInstallConfirmed(event.target.checked)} type="checkbox" />{t("ollama.confirmInstall")}</label>
              <div className="setup-actions"><button className="button" disabled={saving || !csrfToken || !ollamaInstallConfirmed} onClick={() => { void completeStep(() => setupInstallOfficialOllama(csrfToken), "setup.install") }} type="button">{t("ollama.actions.install")}</button><button className="button button--quiet" disabled={saving || !csrfToken} onClick={() => { void completeStep(() => setupBindExistingOllama(ollamaEndpoint.trim(), csrfToken), "setup.save") }} type="button">{t("ollama.actions.bind")}</button><button className="button button--quiet" disabled={saving || !csrfToken} onClick={() => { void completeStep(() => setupSkipOllama(csrfToken), "setup.save") }} type="button">{t("ollama.actions.skip")}</button></div>
            </>}
          </section>}
          {currentStep === 3 && <section className="setup-form">
            <p className="setup-callout">{t("nest.callout")}</p>
            <label>{t("nest.fields.bedCount")}<input max={32} min={4} onChange={(event) => setBedCount(Number.isFinite(event.currentTarget.valueAsNumber) ? event.currentTarget.valueAsNumber : 0)} type="number" value={bedCount} /></label>
            <div className="setup-actions"><button className="button" disabled={saving || !csrfToken} onClick={saveNest} type="button">{t("nest.action")}</button></div>
          </section>}
          {currentStep === 4 && <section className="setup-form">
            <p className="setup-callout">{t("model.callout")}</p>
            {runningTask?.step === 4 ? <p className="setup-task">{t("model.running", { progress: runningTask.progress })}<span>{t("model.runningHint")}</span></p> : <>
              {modelRecommendation?.recommended_model ? <p className="setup-hint">{t("model.recommended", { memory: modelRecommendation.memory_gb, model: modelRecommendation.recommended_model })}</p> : <p className="setup-hint">{t("model.noRecommendation")}</p>}
              <TextField label={t("model.fields.reference")} onChange={setModelReference} placeholder="ollama/qwen2.5:0.5b" value={modelReference} />
              <label className="setup-check"><input checked={modelPullConfirmed} onChange={(event) => setModelPullConfirmed(event.target.checked)} type="checkbox" />{t("model.confirmPull")}</label>
              <div className="setup-actions"><button className="button" disabled={saving || !csrfToken || !modelReference.trim()} onClick={() => { void completeStep(() => setupConfiguredModel(modelReference.trim(), csrfToken), "setup.save") }} type="button">{t("model.actions.save")}</button><button className="button button--quiet" disabled={saving || !csrfToken || !modelReference.trim() || !modelPullConfirmed} onClick={() => { void completeStep(() => setupPullModel(modelReference.trim(), csrfToken), "setup.pull") }} type="button">{t("model.actions.pull")}</button><button className="button button--quiet" disabled={saving || !csrfToken} onClick={() => { void completeStep(() => setupSkipModel(csrfToken), "setup.save") }} type="button">{t("model.actions.skip")}</button></div>
            </>}
          </section>}
          {currentStep === 5 && <section className="setup-form">
            <p className="setup-callout">{t("finish.callout")}</p>
            <div className="setup-actions"><button className="button" disabled={saving || !csrfToken} onClick={() => { void completeStep(() => setupComplete(csrfToken), "setup.complete") }} type="button">{t("finish.action")}</button></div>
          </section>}
          {error ? <Notice kind="error" message={error.kind === "local" ? t(error.key) : localizeApiError(error.reason, error.operation, currentLocale(i18n))} /> : null}
        </div>
      </section>
    </section>
  </main>
}
