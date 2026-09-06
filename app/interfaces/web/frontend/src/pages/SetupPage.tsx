import { useEffect, useId, useRef, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"

import { ApiError } from "../api/http"
import {
  createProviderConnection,
  ensureProviderModelAvailability,
  ownerProviderCatalog,
  ownerProviderConnections,
  refreshProviderModels,
  updateProviderConnection,
  type ProviderConnection,
  type ProviderProduct,
} from "../api/owner-providers"
import { currentUser } from "../api/session"
import {
  setupInstall,
  setupSaveOwnerDraft,
  setupSaveRemoteDraft,
  setupStatus,
  type SetupStatus,
} from "../api/setup"
import { LanguageSwitcher } from "../components/LanguageSwitcher"
import { Notice } from "../components/Notice"
import { FieldRow } from "../components/FieldRow"
import { SelectField } from "../components/SelectField"
import { TextField } from "../components/TextField"
import { localizeApiError, type ErrorOperation } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { SetupCompletion } from "./SetupPageSections"
import { SetupWelcome } from "./SetupWelcome"

type SetupStepNumber = 1 | 2 | 3
type CustomInterface = "openai" | "anthropic"
type SetupError =
  | { readonly kind: "api"; readonly operation: ErrorOperation; readonly reason: unknown }
  | { readonly kind: "local"; readonly key: "errors.modelDiscovery" | "errors.modelVerification" | "errors.passwordMismatch" }

type RemotePreparationPhase = "idle" | "discovering" | "saving" | "preflight" | "failed"

const setupStepNumbers: readonly SetupStepNumber[] = [1, 2, 3]
const setupFullLogoUrl = new URL("../../../../../../docs/public/assets/elfienest-full-logo-transparent.png", import.meta.url).href
// Discovery is intentionally fail-fast. Step 2 uses one bounded model smoke
// check; the complete model validation remains in Step 3.
const SETUP_MODEL_DISCOVERY_TIMEOUT_MS = 2_000
const SETUP_MODEL_PREFLIGHT_TIMEOUT_MS = 25_000
const SETUP_BRAND_ORDER = [
  "google",
  "openai",
  "anthropic",
  "deepseek",
  "alibaba",
  "zhipu",
  "moonshot",
  "minimax",
  "volcengine",
  "xai",
  "openrouter",
  "siliconflow",
  "groq",
  "custom",
] as const
const CUSTOM_INTERFACE_PREFIX = "__custom_interface__"

function normalizeStep(value: number): SetupStepNumber {
  if (value >= 3) return 3
  if (value >= 2) return 2
  return 1
}

function isFreshSetup(status: SetupStatus): boolean {
  return status.need_setup
    && !status.locked
    && status.current_step === 1
    && !status.draft.owner_configured
    && status.draft.owner_account_id === null
}

function parseModelIds(value: string): readonly string[] {
  return [...new Set(value.split(/[,\r\n]/).map((item) => item.trim()).filter(Boolean))]
}

function normalizeModelIds(value: string): string {
  return parseModelIds(value).join(", ")
}

function chooseSetupProbeModelId(
  modelIds: readonly string[],
  connection: ProviderConnection,
): string {
  const records = new Map(connection.models.map((model) => [model.id, model]))
  const nonReasoning = modelIds.filter((modelId) => records.get(modelId)?.supports_reasoning !== true)
  const candidates = nonReasoning.length > 0 ? nonReasoning : modelIds
  return candidates.find((modelId) => /fast|lite|mini|small|flash|turbo/i.test(modelId))
    ?? candidates[0]
    ?? modelIds[0]
    ?? ""
}

function setupError(reason: unknown, operation: ErrorOperation): SetupError {
  return { kind: "api", operation, reason }
}

function setupProviderBrands(products: readonly ProviderProduct[]): readonly ProviderProduct["brand"][] {
  const brands = new Map<string, ProviderProduct["brand"]>()
  for (const product of products) {
    if (!brands.has(product.brand.brand_id)) brands.set(product.brand.brand_id, product.brand)
  }
  return SETUP_BRAND_ORDER.flatMap((brandId) => {
    const brand = brands.get(brandId)
    return brand === undefined ? [] : [brand]
  })
}

export function SetupPage() {
  const { i18n, t } = useTranslation("setup")
  const { t: commonT } = useTranslation("common")
  const [progress, setProgress] = useState<SetupStatus | null>(null)
  const [step, setStep] = useState<SetupStepNumber>(1)
  const [accountId, setAccountId] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [password, setPassword] = useState("")
  const [passwordConfirmation, setPasswordConfirmation] = useState("")
  const [welcomeDismissed, setWelcomeDismissed] = useState(false)
  const [csrfToken, setCsrfToken] = useState("")
  const [sessionCsrfToken, setSessionCsrfToken] = useState("")
  const [providerProducts, setProviderProducts] = useState<readonly ProviderProduct[]>([])
  const [providerConnections, setProviderConnections] = useState<readonly ProviderConnection[]>([])
  const [providerLoading, setProviderLoading] = useState(false)
  const [remoteProviderId, setRemoteProviderId] = useState("")
  const [remoteCatalogId, setRemoteCatalogId] = useState("")
  const [customInterface, setCustomInterface] = useState<CustomInterface>("openai")
  const [remoteConnectionId, setRemoteConnectionId] = useState<string | null>(null)
  const [remoteApiKey, setRemoteApiKey] = useState("")
  const [editingStoredApiKey, setEditingStoredApiKey] = useState(false)
  const [remoteModelIds, setRemoteModelIds] = useState("")
  const [remoteModelsLoaded, setRemoteModelsLoaded] = useState(false)
  const [remoteDiscoveryFailed, setRemoteDiscoveryFailed] = useState(false)
  const [discoveringRemote, setDiscoveringRemote] = useState(false)
  const [remotePhase, setRemotePhase] = useState<RemotePreparationPhase>("idle")
  const [error, setError] = useState<SetupError | null>(null)
  const [saving, setSaving] = useState(false)
  const remoteApiKeyInputId = useId()
  const remoteModelInputId = useId()
  const statusRequestRef = useRef<Promise<SetupStatus> | null>(null)
  const discoveryRequestRef = useRef<Promise<ProviderConnection> | null>(null)
  const lastDiscoveredCredentialRef = useRef<{ readonly connectionId: string; readonly apiKey: string } | null>(null)

  const applyStatus = (status: SetupStatus): void => {
    setProgress(status)
    setCsrfToken(status.csrf_token ?? "")
    setStep(status.locked || status.complete || status.install.state === "running" ? 3 : normalizeStep(status.current_step))
    if (status.draft.owner_account_id !== null) setAccountId(status.draft.owner_account_id)
    if (status.draft.display_name !== null) setDisplayName(status.draft.display_name)
    setRemoteConnectionId(status.draft.remote_connection_id)
  }

  const refreshStatus = (): Promise<SetupStatus> => {
    const inFlight = statusRequestRef.current
    if (inFlight !== null) return inFlight
    const request = setupStatus()
    statusRequestRef.current = request
    void request.then(
      () => { if (statusRequestRef.current === request) statusRequestRef.current = null },
      () => { if (statusRequestRef.current === request) statusRequestRef.current = null },
    )
    return request
  }

  const apiProducts = providerProducts.filter((product) => product.connection_method === "api_key")
  const brands = setupProviderBrands(apiProducts)
  const productsForBrand = apiProducts.filter((product) => product.brand.brand_id === remoteProviderId)
  const selectedProduct = apiProducts.find((product) => (
    product.catalog_id === remoteCatalogId && product.brand.brand_id === remoteProviderId
  )) ?? productsForBrand[0] ?? apiProducts[0]
  const selectedConnection = selectedProduct === undefined
    ? undefined
    : providerConnections.find((connection) => (
      connection.connection_id === remoteConnectionId && connection.catalog_id === selectedProduct.catalog_id
    )) ?? providerConnections.find((connection) => (
      connection.catalog_id === selectedProduct.catalog_id && connection.enabled && !connection.archived
    )) ?? providerConnections.find((connection) => connection.catalog_id === selectedProduct.catalog_id)
  const hasStoredCredential = Boolean(selectedConnection?.has_api_key || selectedConnection?.has_credential)
  const showingStoredApiKey = hasStoredCredential && !editingStoredApiKey && remoteApiKey.trim().length === 0
  const parsedModelIds = parseModelIds(remoteModelIds)
  const customInterfaceValue = `${CUSTOM_INTERFACE_PREFIX}:${customInterface}`
  const connectionOptions = remoteProviderId === "custom"
    ? [
      { label: t("remote.customOpenAI"), value: `${CUSTOM_INTERFACE_PREFIX}:openai` },
      { label: t("remote.customAnthropic"), value: `${CUSTOM_INTERFACE_PREFIX}:anthropic` },
    ]
    : productsForBrand.map((product) => ({ label: product.name, value: product.catalog_id }))
  const customProviderConfig = selectedProduct?.brand.brand_id === "custom"
    ? {
      api_mode: customInterface === "anthropic" ? "anthropic_messages" : "chat_completions",
      auth_type: customInterface === "anthropic" ? "x-api-key" : "bearer",
    }
    : {}

  const applyProviderResources = (
    products: readonly ProviderProduct[],
    connections: readonly ProviderConnection[],
    persistedConnectionId: string | null = remoteConnectionId,
  ): void => {
    const nextProducts = products.filter((product) => product.connection_method === "api_key")
    const persisted = persistedConnectionId === null
      ? undefined
      : connections.find((connection) => connection.connection_id === persistedConnectionId)
    const existing = persisted ?? connections.find((connection) => (
      nextProducts.some((product) => product.catalog_id === connection.catalog_id)
      && connection.enabled
      && !connection.archived
    )) ?? connections.find((connection) => nextProducts.some((product) => product.catalog_id === connection.catalog_id))
    const nextProduct = (existing === undefined
      ? undefined
      : nextProducts.find((product) => product.catalog_id === existing.catalog_id)) ?? nextProducts[0]
    const selected = existing?.catalog_id === nextProduct?.catalog_id
      ? existing
      : nextProduct === undefined
        ? undefined
        : connections.find((connection) => connection.catalog_id === nextProduct.catalog_id)
    setProviderProducts(nextProducts)
    setProviderConnections(connections)
    setRemoteProviderId(nextProduct?.brand.brand_id ?? "")
    setRemoteCatalogId(nextProduct?.catalog_id ?? "")
    setRemoteConnectionId(selected?.connection_id ?? null)
    setCustomInterface(selected?.api_mode === "anthropic_messages" ? "anthropic" : "openai")
    setRemoteApiKey("")
    setEditingStoredApiKey(false)
    if (selected !== undefined && selected.models.length > 0) {
      setRemoteModelIds(selected.models.map((model) => model.id).join(", "))
      setRemoteModelsLoaded(true)
    } else {
      setRemoteModelIds("")
      setRemoteModelsLoaded(false)
    }
  }

  const loadProviderResources = async (persistedConnectionId: string | null = remoteConnectionId): Promise<void> => {
    setProviderLoading(true)
    try {
      const [products, connections] = await Promise.all([
        ownerProviderCatalog(),
        ownerProviderConnections(),
      ])
      applyProviderResources(products, connections, persistedConnectionId)
    } finally {
      setProviderLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    const load = async (): Promise<void> => {
      try {
        const status = await refreshStatus()
        if (cancelled) return
        applyStatus(status)
        if (!status.draft.owner_configured || status.current_step < 2) return
        const user = await currentUser()
        if (cancelled) return
        const token = user.csrf_token ?? ""
        if (!token) throw new ApiError(401, "Owner session is unavailable")
        setSessionCsrfToken(token)
        await loadProviderResources(status.draft.remote_connection_id)
      } catch (reason: unknown) {
        if (!cancelled) setError(setupError(reason, "setup.load"))
      }
    }
    void load()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!progress?.locked || progress.install.state === "completed") return
    let cancelled = false
    const timer = window.setInterval(() => {
      void refreshStatus().then((status) => {
        if (!cancelled) applyStatus(status)
      }).catch((reason: unknown) => {
        if (!cancelled) setError(setupError(reason, "setup.load"))
      })
    }, 1000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [progress?.locked, progress?.install.state])

  const draft = progress?.draft
  const install = progress?.install
  const setupCompleted = install?.state === "completed"
  const remoteConfigured = draft?.remote_configured === true

  const callSetupAction = async (
    action: (token: string) => Promise<SetupStatus>,
  ): Promise<SetupStatus> => {
    const initial = await refreshStatus()
    applyStatus(initial)
    const initialToken = initial.csrf_token
    if (!initialToken) throw new ApiError(403, t("errors.csrfMissing"), [], "csrf_rejected")
    try {
      const result = await action(initialToken)
      applyStatus(result)
      return result
    } catch (reason: unknown) {
      if (!(reason instanceof ApiError) || reason.status !== 403 || reason.code !== "csrf_rejected") throw reason
      const refreshed = await refreshStatus()
      applyStatus(refreshed)
      const refreshedToken = refreshed.csrf_token
      if (!refreshedToken) throw reason
      const result = await action(refreshedToken)
      applyStatus(result)
      return result
    }
  }

  const runSetupAction = async (
    action: (token: string) => Promise<SetupStatus>,
    operation: ErrorOperation,
  ): Promise<void> => {
    setSaving(true)
    setError(null)
    try {
      await callSetupAction(action)
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
    setSaving(true)
    setError(null)
    void (async () => {
      try {
        const status = await callSetupAction((token) => setupSaveOwnerDraft(
          accountId.trim(),
          displayName.trim(),
          password.trim() || null,
          passwordConfirmation.trim() || null,
          token,
        ))
        const user = await currentUser()
        const token = user.csrf_token ?? ""
        if (!token) throw new ApiError(401, "Owner session is unavailable")
        setSessionCsrfToken(token)
        await loadProviderResources(status.draft.remote_connection_id)
      } catch (reason: unknown) {
        setError(setupError(reason, "setup.save"))
      } finally {
        setSaving(false)
      }
    })()
  }

  const getSessionCsrf = async (): Promise<string> => {
    if (sessionCsrfToken) return sessionCsrfToken
    const user = await currentUser()
    const token = user.csrf_token ?? ""
    if (!token) throw new ApiError(401, "Owner session is unavailable")
    setSessionCsrfToken(token)
    return token
  }

  const selectRemoteCatalog = (catalogId: string, nextCustomInterface?: CustomInterface): void => {
    const product = apiProducts.find((item) => item.catalog_id === catalogId)
    if (product === undefined) return
    const connection = providerConnections.find((item) => item.catalog_id === product.catalog_id)
    setRemoteProviderId(product.brand.brand_id)
    setRemoteCatalogId(product.catalog_id)
    setRemoteConnectionId(connection?.connection_id ?? null)
    setCustomInterface(nextCustomInterface ?? (connection?.api_mode === "anthropic_messages" ? "anthropic" : "openai"))
    setRemoteApiKey("")
    setEditingStoredApiKey(false)
    lastDiscoveredCredentialRef.current = null
    setRemoteModelIds(connection?.models.map((model) => model.id).join(", ") ?? "")
    setRemoteModelsLoaded(Boolean(connection?.models.length))
    setRemoteDiscoveryFailed(false)
    setRemotePhase("idle")
    setError(null)
  }

  const discoverRemoteModels = (
    timeoutMs = SETUP_MODEL_DISCOVERY_TIMEOUT_MS,
  ): Promise<ProviderConnection> => {
    const inFlight = discoveryRequestRef.current
    if (inFlight !== null) return inFlight
    const request = (async (): Promise<ProviderConnection> => {
      setDiscoveringRemote(true)
      setRemoteDiscoveryFailed(false)
      let product: ProviderProduct | undefined
      let sessionToken = ""
      let apiKey = ""
      let existing: ProviderConnection | undefined
      try {
        product = selectedProduct
        if (product === undefined) throw new Error(t("remote.selectProvider"))
        sessionToken = await getSessionCsrf()
        apiKey = remoteApiKey.trim()
        existing = providerConnections.find((connection) => (
          connection.catalog_id === product?.catalog_id
          && connection.connection_id === remoteConnectionId
        )) ?? providerConnections.find((connection) => connection.catalog_id === product?.catalog_id)
        const existingConnection = existing
        const lastDiscoveredCredential = lastDiscoveredCredentialRef.current
        const shouldRefreshForCredential = apiKey.length > 0 && (
          lastDiscoveredCredential === null
          || lastDiscoveredCredential.connectionId !== existingConnection?.connection_id
          || lastDiscoveredCredential.apiKey !== apiKey
        )
        let latest: ProviderConnection
        if (existingConnection !== undefined && shouldRefreshForCredential) {
          latest = await updateProviderConnection(existingConnection.connection_id, {
            ...customProviderConfig,
            api_key: apiKey,
            refresh_models: true,
            defer_validation: true,
          }, sessionToken, { timeout: timeoutMs })
        } else if (existingConnection !== undefined && (existingConnection.models.length > 0 || parsedModelIds.length > 0)) {
          latest = existingConnection
        } else if (existingConnection !== undefined) {
          const refresh = await refreshProviderModels(existingConnection.connection_id, sessionToken, { timeout: timeoutMs })
          if (refresh?.status === "failed") throw new Error(refresh.message ?? t("remote.discoveryFailed"))
          const connections = await ownerProviderConnections({ timeout: timeoutMs })
          const refreshed = connections.find((connection) => connection.connection_id === existingConnection.connection_id)
          if (refreshed === undefined) throw new Error(t("remote.discoveryFailed"))
          latest = refreshed
        } else {
          if (!apiKey) throw new Error(t("remote.apiKeyRequired"))
          latest = await createProviderConnection({
            catalog_id: product.catalog_id,
            ...customProviderConfig,
            api_key: apiKey,
            models: [],
            refresh_models: true,
            defer_validation: true,
          }, sessionToken, { timeout: timeoutMs })
        }
        setProviderConnections((current) => [
          ...current.filter((connection) => connection.connection_id !== latest.connection_id),
          latest,
        ])
        if (apiKey) lastDiscoveredCredentialRef.current = { connectionId: latest.connection_id, apiKey }
        setRemoteConnectionId(latest.connection_id)
        if (latest.models.length > 0) {
          setRemoteModelIds(latest.models.map((model) => model.id).join(", "))
          setRemoteModelsLoaded(true)
        } else {
          setRemoteModelsLoaded(false)
        }
        return latest
      } catch (reason: unknown) {
        setRemoteDiscoveryFailed(true)
        // Keep the durable Provider connection visible after a failed refresh,
        // but never treat that stale inventory as a successful discovery.
        if (product !== undefined && sessionToken) {
          void ownerProviderConnections({ timeout: timeoutMs }).then((persistedConnections) => {
            const persisted = persistedConnections.find((connection) => (
              connection.catalog_id === product?.catalog_id
              && (existing === undefined || connection.connection_id === existing.connection_id)
              && (connection.has_api_key || connection.has_credential)
            ))
            if (persisted !== undefined) {
              setProviderConnections(persistedConnections)
              setRemoteConnectionId(persisted.connection_id)
              setRemoteModelIds(persisted.models.map((model) => model.id).join(", "))
              setRemoteModelsLoaded(persisted.models.length > 0)
            }
          }).catch(() => undefined)
        }
        throw reason
      } finally {
        setDiscoveringRemote(false)
      }
    })()
    const tracked = request.finally(() => {
      if (discoveryRequestRef.current === tracked) discoveryRequestRef.current = null
    })
    discoveryRequestRef.current = tracked
    return tracked
  }

  const saveRemoteSubscription = async (
    modelIds: readonly string[],
    sessionToken: string,
  ): Promise<ProviderConnection> => {
    const product = selectedProduct
    if (product === undefined) throw new Error(t("remote.selectProvider"))
    const apiKey = remoteApiKey.trim()
    const models = modelIds.map((id) => ({ id }))
    if (selectedConnection !== undefined) {
      return updateProviderConnection(selectedConnection.connection_id, {
        ...customProviderConfig,
        ...(apiKey ? { api_key: apiKey } : {}),
        models,
        refresh_models: false,
        defer_validation: true,
      }, sessionToken)
    }
    if (!apiKey) throw new Error(t("remote.apiKeyRequired"))
    return createProviderConnection({
      catalog_id: product.catalog_id,
      ...customProviderConfig,
      api_key: apiKey,
      models,
      refresh_models: false,
      defer_validation: true,
    }, sessionToken)
  }

  const continueWithRemote = (): void => {
    setSaving(true)
    setError(null)
    setRemotePhase("saving")
    void (async () => {
      try {
        const sessionToken = await getSessionCsrf()
        let modelIds = parsedModelIds
        if (modelIds.length === 0 && selectedConnection !== undefined) {
          modelIds = selectedConnection.models.map((model) => model.id)
        }
        if (modelIds.length === 0) throw new Error(t("remote.modelsRequired"))
        setRemoteModelIds(modelIds.join(", "))
        // Save the inventory without triggering the Provider service's implicit
        // probes. The one explicit Step 2 smoke check below is the only
        // validation here; full validation remains in Step 3.
        const configuredConnection = await saveRemoteSubscription(modelIds, sessionToken)
        setProviderConnections((current) => [
          ...current.filter((item) => item.connection_id !== configuredConnection.connection_id),
          configuredConnection,
        ])
        setRemoteConnectionId(configuredConnection.connection_id)
        setRemotePhase("preflight")
        const probeModelId = chooseSetupProbeModelId(modelIds, configuredConnection)
        const availability = await ensureProviderModelAvailability(
          configuredConnection.connection_id,
          probeModelId,
          sessionToken,
          { timeout: SETUP_MODEL_PREFLIGHT_TIMEOUT_MS },
        )
        if (availability.status !== "available" && availability.status !== "degraded") {
          setRemotePhase("failed")
          setError({ kind: "local", key: "errors.modelVerification" })
          return
        }
        await callSetupAction((token) => setupSaveRemoteDraft(true, configuredConnection.connection_id, token))
        await callSetupAction((token) => setupInstall(token))
      } catch (reason: unknown) {
        setRemotePhase("failed")
        setError(setupError(reason, "setup.save"))
      } finally {
        setSaving(false)
      }
    })()
  }

  const skipRemote = (): void => {
    setSaving(true)
    setError(null)
    setRemotePhase("saving")
    void (async () => {
      try {
        await callSetupAction((token) => setupSaveRemoteDraft(false, null, token))
        await callSetupAction((token) => setupInstall(token))
      } catch (reason: unknown) {
        setRemotePhase("failed")
        setError(setupError(reason, "setup.install"))
      } finally {
        setSaving(false)
      }
    })()
  }

  const selectRemoteProvider = (providerId: string): void => {
    const firstProduct = apiProducts.find((product) => product.brand.brand_id === providerId)
    setRemoteProviderId(providerId)
    if (firstProduct !== undefined) selectRemoteCatalog(firstProduct.catalog_id, providerId === "custom" ? "openai" : undefined)
  }

  const currentStep: SetupStepNumber = step
  const installationStartFailed = currentStep === 3 && remotePhase === "failed" && install?.state === "idle"
  const installFailed = installationStartFailed || install?.state === "failed" || install?.state === "cancelled"
  const showCompletion = currentStep === 3 || setupCompleted || installFailed
  const isFinalizing = showCompletion && !setupCompleted && !installFailed
  const ownerEditable = !draft?.owner_configured && !isFinalizing
  const stepsLocked = currentStep === 3 || Boolean(progress?.locked || draft?.owner_configured)
  const stepCopy = {
    1: { label: "steps.owner.label", title: "steps.owner.title" },
    2: { label: "steps.remote.label", title: "steps.remote.title" },
    3: { label: "steps.complete.label", title: "steps.complete.title" },
  } as const
  const setupTitle = showCompletion
    ? installFailed
      ? t("completion.failed")
      : setupCompleted
        ? t("completion.title")
        : t("completion.preparing")
    : t(stepCopy[currentStep].title)
  const setupEyebrow = t("progress.stepCount", { current: currentStep, total: 3 })
  const modelStatusClass = !remoteDiscoveryFailed && (remoteModelsLoaded || parsedModelIds.length > 0) ? "setup-hint--installed" : "setup-hint--missing"
  const modelStatusText = remoteDiscoveryFailed
    ? t("remote.modelsDiscoveryFailed")
    : remoteModelsLoaded
      ? t("remote.modelsLoaded")
      : parsedModelIds.length > 0
        ? t("remote.modelsManual")
        : t("remote.modelsWaiting")
  const completionError = progress?.last_error ?? (
    installationStartFailed && error !== null
      ? error.kind === "local"
        ? t(error.key)
        : localizeApiError(error.reason, error.operation, currentLocale(i18n))
      : null
  )
  const showWelcome = !welcomeDismissed && (progress === null || isFreshSetup(progress))

  if (showWelcome) {
    return <main className="setup-welcome-page">
      <section aria-label={commonT("language.label")} className="setup-locale-control"><LanguageSwitcher variant="compact" /></section>
      <SetupWelcome action={t("welcome.action")} disabled={progress === null} onContinue={() => {
        if (progress !== null) setWelcomeDismissed(true)
      }} title={t("welcome.title")} />
    </main>
  }

  return <main className="setup-page">
    <aside className="setup-rail">
      <div className="setup-brand"><img alt="ELFIE NEST" className="setup-brand__logo" src={setupFullLogoUrl} /></div>
      <div className="setup-rail__intro"><p className="brand">{t("rail.brand")}</p></div>
      <ol aria-label={t("rail.stepsLabel")} className="setup-steps">
        {setupStepNumbers.map((stepNumber) => {
          const storedStep = progress?.steps.find((item) => item.number === stepNumber)
          const completed = storedStep?.status === "completed"
          const current = stepNumber === currentStep
          const stateClassName = current ? "setup-step--current" : completed ? "setup-step--completed" : ""
          const disabled = current || !completed || stepsLocked
          return <li className={`setup-step ${stateClassName}`} key={stepNumber}>
            <button aria-current={current ? "step" : undefined} className="setup-step__button" disabled={disabled} onClick={() => setStep(stepNumber)} type="button">
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
          {!showCompletion ? <p className="brand">{setupEyebrow}</p> : null}
          <h1 className="setup-card__title" id="setup-title">{setupTitle}</h1>
          {!showCompletion && currentStep === 2 ? <p className="setup-card__subtitle">{t("remote.subtitle")}</p> : null}
        </header>
        <div className="setup-card__content">
          {currentStep === 3 && showCompletion ? <SetupCompletion
            completed={setupCompleted}
            foodConfigured={remoteConfigured}
            install={install}
            lastError={completionError}
            onEnter={() => window.location.assign("/")}
            onRetry={() => { void runSetupAction((token) => setupInstall(token), "setup.install") }}
            requestFailed={installationStartFailed}
            saving={saving}
            t={t}
          /> : null}
          {currentStep === 1 ? <form className="setup-form setup-form--owner" onSubmit={submitOwner}>
            <TextField autoComplete="username" label={t("owner.fields.accountId")} minLength={3} onChange={setAccountId} readOnly={!ownerEditable} required value={accountId} />
            <TextField autoComplete="name" label={t("owner.fields.displayName")} onChange={setDisplayName} readOnly={!ownerEditable} required value={displayName} />
            <TextField {...(draft?.password_configured ? { placeholder: t("owner.passwordConfiguredPlaceholder") } : {})} autoComplete="new-password" label={t("owner.fields.password")} minLength={6} onChange={setPassword} readOnly={!ownerEditable} required={!draft?.password_configured} type="password" value={password} />
            <TextField {...(draft?.password_configured ? { placeholder: t("owner.passwordConfiguredPlaceholder") } : {})} autoComplete="new-password" label={t("owner.fields.confirmPassword")} minLength={6} onChange={setPasswordConfirmation} readOnly={!ownerEditable} required={!draft?.password_configured} type="password" value={passwordConfirmation} />
            <div className="setup-actions"><button className="button" disabled={saving || !csrfToken || !ownerEditable} type="submit">{saving ? t("owner.submitting") : t("owner.action")}</button></div>
          </form> : null}
          {currentStep === 2 && !showCompletion ? <section className="setup-form setup-form--remote">
            {providerProducts.length === 0 && <p className="setup-hint" role="status">{providerLoading ? t("remote.loading") : t("remote.noProviders")}</p>}
            <SelectField disabled={providerLoading || discoveringRemote || saving || apiProducts.length === 0} label={t("remote.provider")} onValueChange={selectRemoteProvider} options={brands.map((brand) => ({ label: brand.brand_id === "custom" ? t("remote.customProvider") : brand.name, value: brand.brand_id }))} value={remoteProviderId} />
            <SelectField
              disabled={providerLoading || discoveringRemote || saving || productsForBrand.length === 0}
              label={t("remote.connectionMethod")}
              onValueChange={(value) => {
                if (remoteProviderId === "custom") {
                  selectRemoteCatalog("custom_openai", value.endsWith(":anthropic") ? "anthropic" : "openai")
                } else {
                  selectRemoteCatalog(value)
                }
              }}
              options={connectionOptions}
              value={remoteProviderId === "custom" ? customInterfaceValue : selectedProduct?.catalog_id ?? ""}
            />
            <FieldRow
              control={<Input
                autoComplete="off"
                className="input--masked"
                data-1p-ignore="true"
                data-bwignore="true"
                data-form-type="other"
                data-lpignore="true"
                disabled={providerLoading || discoveringRemote || saving || selectedProduct === undefined}
                id={remoteApiKeyInputId}
                inputMode="text"
                name="api-key"
                onBlur={() => {
                  if (hasStoredCredential && !remoteApiKey.trim()) setEditingStoredApiKey(false)
                  void discoverRemoteModels().catch(() => undefined)
                }}
                onChange={(event) => {
                  setEditingStoredApiKey(true)
                  setRemoteApiKey(event.target.value)
                  lastDiscoveredCredentialRef.current = null
                  setRemoteModelsLoaded(false)
                  setRemoteDiscoveryFailed(false)
                  setRemotePhase("idle")
                  setError(null)
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault()
                    void discoverRemoteModels().catch(() => undefined)
                  }
                }}
                onFocus={() => {
                  if (showingStoredApiKey) {
                    setEditingStoredApiKey(true)
                    setRemoteApiKey("")
                  }
                }}
                readOnly={showingStoredApiKey}
                required={!hasStoredCredential}
                spellCheck={false}
                type="text"
                value={showingStoredApiKey ? "••••••••••••" : remoteApiKey}
              />}
              hint={hasStoredCredential ? undefined : t("remote.apiKeyHint")}
              inputId={remoteApiKeyInputId}
              label={t("remote.apiKey")}
            />
            <FieldRow
              control={<Textarea
                aria-label={t("remote.model")}
                disabled={providerLoading || discoveringRemote || saving || selectedProduct === undefined}
                onChange={(event) => {
                  setRemoteModelIds(event.target.value)
                  setRemoteModelsLoaded(false)
                  setRemoteDiscoveryFailed(false)
                  setRemotePhase("idle")
                  setError(null)
                }}
                onBlur={() => { setRemoteModelIds(normalizeModelIds(remoteModelIds)) }}
                placeholder={t("remote.modelPlaceholder")}
                rows={3}
                value={remoteModelIds}
              />}
              inputId={remoteModelInputId}
              label={t("remote.model")}
            />
            <p className={`setup-hint setup-hint--status ${modelStatusClass}`} role="status">
              {discoveringRemote
                ? t("remote.modelsDiscovering")
                : remotePhase === "preflight"
                  ? t("remote.validating")
                : modelStatusText}
            </p>
            <div className="setup-actions">
              <button className="button" disabled={saving || discoveringRemote || !sessionCsrfToken || selectedProduct === undefined || (!remoteApiKey.trim() && !hasStoredCredential) || parsedModelIds.length === 0} onClick={continueWithRemote} type="button">{t("remote.action")}</button>
              <button className="button button--quiet" disabled={saving || discoveringRemote || !csrfToken} onClick={skipRemote} type="button">{t("remote.skip")}</button>
            </div>
          </section> : null}
          {error && !installationStartFailed ? <Notice kind="error" message={error.kind === "local" ? t(error.key) : localizeApiError(error.reason, error.operation, currentLocale(i18n))} /> : null}
        </div>
      </section>
    </section>
  </main>
}
