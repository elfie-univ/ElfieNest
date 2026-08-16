import { Button } from "@/components/ui/button"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  changeProviderConnectionLifecycle,
  completeProviderOAuthLogin,
  createProviderConnection,
  deleteProviderConnection,
  ownerProviderCatalog,
  ownerProviderConnections,
  startProviderOAuthLogin,
  updateProviderConnection,
  validateAllProviderModels,
  verifyProviderConnection,
  type ProviderConnection,
  type ProviderConnectionDraft,
  type ProviderConnectionUpdate,
  type ProviderProduct,
} from "../api/owner-providers"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { compareLocalizedText, currentLocale } from "../i18n/format"
import { ConfirmDialog } from "./ConfirmDialog"
import { CustomProviderDialog, type CustomProviderPreset } from "./CustomProviderDialog"
import { Icon } from "./Icon"
import { ManageDialog } from "./ManageDialog"
import { ModelMatrixDialog } from "./ModelMatrixDialog"
import { Notice } from "./Notice"
import { OwnerOllamaPanel } from "./OwnerOllamaPanel"
import { ProviderFormDialog } from "./ProviderFormDialog"
import { ProviderBrandLogo } from "./ProviderBrandLogo"
import { ProviderLifecycleMenu, type ProviderLifecycleAction } from "./ProviderLifecycleMenu"
import { ProviderModelsDialog } from "./ProviderModelsDialog"
import { RefreshButton } from "./RefreshButton"
import { SelectField } from "./SelectField"
import { useToast } from "./ui/toast"

type EditTarget = {
  readonly connection: ProviderConnection | null
  readonly products: readonly ProviderProduct[]
}

type ProviderBrandGroup = {
  readonly brand: ProviderProduct["brand"]
  readonly products: readonly ProviderProduct[]
}

type OtherSubscriptionOption =
  | { readonly group: ProviderBrandGroup; readonly kind: "catalog"; readonly label: string; readonly value: string }
  | { readonly kind: "interface"; readonly label: string; readonly preset: CustomProviderPreset; readonly value: string }

const NO_PRODUCT = "__none__"
const OPENAI_INTERFACE_OPTION = "__openai_interface__"
const ANTHROPIC_INTERFACE_OPTION = "__anthropic_interface__"
const FEATURED_BRAND_LIMIT = 8
const FEATURED_BRAND_ORDER = [
  "google",
  "openai",
  "anthropic",
  "deepseek",
  "alibaba",
  "zhipu",
  "moonshot",
  "minimax",
] as const

export function OwnerProviderPanel({ csrfToken }: { readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [catalog, setCatalog] = useState<readonly ProviderProduct[]>([])
  const [connections, setConnections] = useState<readonly ProviderConnection[]>([])
  const [editing, setEditing] = useState<EditTarget | null>(null)
  const [viewingModels, setViewingModels] = useState<ProviderConnection | null>(null)
  const [deleting, setDeleting] = useState<ProviderConnection | null>(null)
  const [creatingCustom, setCreatingCustom] = useState(false)
  const [customPreset, setCustomPreset] = useState<CustomProviderPreset>("openai")
  const [otherOpen, setOtherOpen] = useState(false)
  const [otherProductId, setOtherProductId] = useState(NO_PRODUCT)
  const [matrixOpen, setMatrixOpen] = useState(false)
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const { show } = useToast()

  const load = async (): Promise<void> => {
    try {
      const [nextCatalog, nextConnections] = await Promise.all([ownerProviderCatalog(), ownerProviderConnections()])
      setCatalog(nextCatalog)
      setConnections(nextConnections)
      setViewingModels((current) => current
        ? nextConnections.find((item) => item.connection_id === current.connection_id) ?? null
        : null)
      setError(null)
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.load"))
    }
  }
  useEffect(() => { void load() }, [])

  const productsById = useMemo(() => new Map(catalog.map((product) => [product.catalog_id, product])), [catalog])
  const configured = connections
    .filter((connection) => connection.catalog_id !== "ollama")
    .sort((left, right) => compareLocalizedText(left.alias, right.alias, locale))
  const brandGroups = useMemo(() => groupRemoteProductsByBrand(catalog), [catalog])
  const featuredBrands = useMemo(() => [...brandGroups]
    .sort((left, right) => featuredBrandRank(left.brand.brand_id) - featuredBrandRank(right.brand.brand_id))
    .slice(0, FEATURED_BRAND_LIMIT), [brandGroups])
  const featuredBrandIds = useMemo(() => new Set(featuredBrands.map((group) => group.brand.brand_id)), [featuredBrands])
  const otherBrands = useMemo(() => brandGroups.filter((group) => !featuredBrandIds.has(group.brand.brand_id)), [brandGroups, featuredBrandIds])
  const otherOptions = useMemo<readonly OtherSubscriptionOption[]>(() => [
    { kind: "interface" as const, label: t("providerConnections.other.openaiInterface"), preset: "openai" as const, value: OPENAI_INTERFACE_OPTION },
    { kind: "interface" as const, label: t("providerConnections.other.anthropicInterface"), preset: "anthropic" as const, value: ANTHROPIC_INTERFACE_OPTION },
    ...otherBrands.map((group) => ({ group, kind: "catalog" as const, label: group.brand.name, value: group.brand.brand_id })),
  ], [otherBrands, t])

  const save = async (catalogId: string, draft: ProviderConnectionUpdate): Promise<void> => {
    if (!editing) return
    try {
      const result = editing.connection
        ? await updateProviderConnection(editing.connection.connection_id, draft, csrfToken)
        : await createProviderConnection({ catalog_id: catalogId, ...draft }, csrfToken)
      show({ kind: "success", message: result.model_refresh?.message ?? t("providerConnections.notices.saved", { name: result.alias }) })
      setEditing(null)
      await load()
    } catch (reason: unknown) {
      throw reason
    }
  }

  const saveCustom = async (draft: ProviderConnectionDraft): Promise<void> => {
    const result = await createProviderConnection(draft, csrfToken)
    show({ kind: "success", message: result.model_refresh?.message ?? t("providerConnections.notices.added", { name: result.alias }) })
    setCreatingCustom(false)
    await load()
  }

  const authorize = async (
    catalogId: string,
    alias: string | undefined,
    onStarted: (started: Awaited<ReturnType<typeof startProviderOAuthLogin>>) => void,
    signal: AbortSignal,
  ): Promise<void> => {
    if (!editing) return
    const started = await startProviderOAuthLogin(catalogId, csrfToken)
    signal.throwIfAborted()
    onStarted(started)
    for (;;) {
      await waitForOAuthPoll(started.poll_interval_seconds * 1000, signal)
      const status = await completeProviderOAuthLogin(started.login_id, catalogId, alias, csrfToken)
      signal.throwIfAborted()
      if (status.state === "pending") continue
      const connection = status.connection
      const product = editing.products.find((item) => item.catalog_id === catalogId)
      show({
        kind: "success",
        message: t("providerConnections.notices.authorized", { name: connection?.alias ?? product?.name ?? editing.products[0]?.brand.name ?? catalogId }),
      })
      setEditing(null)
      await load()
      return
    }
  }

  const verify = async (connection: ProviderConnection): Promise<void> => {
    setPending(`verify:${connection.connection_id}`)
    try {
      await verifyProviderConnection(connection.connection_id, csrfToken)
      show({ kind: "success", message: t("providerConnections.notices.validated", { name: connection.alias }) })
      await load()
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(null)
    }
  }

  const forceFullVerify = async (connection: ProviderConnection): Promise<void> => {
    setPending(`verify:${connection.connection_id}`)
    try {
      await verifyProviderConnection(connection.connection_id, csrfToken, true)
      setNotice(t("providerConnections.notices.forceValidated", { name: connection.alias }))
      await load()
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(null)
    }
  }

  const runValidation = async (): Promise<void> => {
    setPending("batch")
    try {
      const result = await validateAllProviderModels(csrfToken)
      const passed = result.results.filter((item) => item.status === "passed").length
      setNotice(t("providerConnections.notices.validatedAll", { count: passed, runId: result.run_id }))
      await load()
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(null)
    }
  }

  const lifecycle = async (connection: ProviderConnection, action: ProviderLifecycleAction): Promise<void> => {
    setPending(`${action}:${connection.connection_id}`)
    try {
      await changeProviderConnectionLifecycle(connection.connection_id, action, csrfToken)
      await load()
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(null)
    }
  }

  const remove = async (): Promise<void> => {
    if (!deleting) return
    setPending(`delete:${deleting.connection_id}`)
    try {
      await deleteProviderConnection(deleting.connection_id, csrfToken)
      setDeleting(null)
      await load()
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.delete"))
    } finally {
      setPending(null)
    }
  }

  const chooseOther = (): void => {
    const option = otherOptions.find((item) => item.value === otherProductId)
    if (!option) return
    setOtherOpen(false)
    setOtherProductId(NO_PRODUCT)
    if (option.kind === "catalog") {
      setEditing({ connection: null, products: option.group.products })
      return
    }
    setCustomPreset(option.preset)
    setCreatingCustom(true)
  }

  return <section className="manage-card manage-card--wide provider-page">
    <div className="manage-head"><div className="manage-actions">
      <Button disabled={pending !== null || configured.length === 0} onClick={() => { void runValidation() }} type="button">{pending === "batch" ? t("providerConnections.actions.validating") : t("providerConnections.actions.batchValidate")}</Button>
      <Button onClick={() => setMatrixOpen(true)} type="button">{t("providerConnections.actions.matrix")}</Button>
      <RefreshButton disabled={pending !== null} label={t("providerConnections.actions.refresh")} onClick={() => { void load() }} />
    </div></div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.load")} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <OwnerOllamaPanel csrfToken={csrfToken} />
    <section aria-labelledby="configured-provider-title" className="provider-section provider-section--configured"><div className="provider-section__heading"><div><h3 id="configured-provider-title">{t("providerConnections.section.configuredTitle")}</h3></div><span>{t("providerConnections.section.count", { count: configured.length })}</span></div>
      {configured.length === 0 ? <p className="empty-state">{t("providerConnections.section.configuredEmpty")}</p> : <div className="provider-grid">{configured.map((connection) => <ConfiguredConnectionCard
        busy={pending?.endsWith(connection.connection_id) ?? false}
        connection={connection}
        key={connection.connection_id}
        onEdit={() => { const product = productsById.get(connection.catalog_id); if (product) setEditing({ connection, products: [product] }) }}
        onModels={() => setViewingModels(connection)}
        onDelete={() => setDeleting(connection)}
        onLifecycle={(action) => { void lifecycle(connection, action) }}
        onVerify={() => { void verify(connection) }}
        onForceFull={() => { void forceFullVerify(connection) }}
      />)}</div>}
    </section>
    <section aria-labelledby="available-provider-title" className="provider-section provider-section--available"><div className="provider-section__heading"><div><h3 id="available-provider-title">{t("providerConnections.available.title")}</h3></div></div><div className="provider-grid">
      {featuredBrands.map((group) => <button aria-label={t("providerConnections.actions.configure", { name: group.brand.name })} className="provider-card provider-card--available" key={group.brand.brand_id} onClick={() => setEditing({ connection: null, products: group.products })} type="button"><span className="provider-card__brand"><ProviderBrandLogo brand={group.brand} /><strong>{group.brand.name}</strong></span></button>)}
      <button aria-label={t("providerConnections.actions.addOther")} className="provider-card provider-card--add" onClick={() => setOtherOpen(true)} type="button"><span className="provider-card__add-mark"><Icon name="plus" size={24} /></span><strong>{t("providerConnections.actions.addOther")}</strong></button>
    </div></section>
    <ProviderFormDialog connection={editing?.connection ?? null} onAuthorize={authorize} onOpenChange={(open) => { if (!open) setEditing(null) }} onSave={save} open={editing !== null} products={editing?.products ?? []} />
    <CustomProviderDialog onOpenChange={setCreatingCustom} onSave={saveCustom} open={creatingCustom} preset={customPreset} />
    <ProviderModelsDialog connection={viewingModels} csrfToken={csrfToken} onChanged={load} onOpenChange={(open) => { if (!open) setViewingModels(null) }} open={viewingModels !== null} />
    <ModelMatrixDialog csrfToken={csrfToken} onOpenChange={setMatrixOpen} open={matrixOpen} />
    <ManageDialog onOpenChange={setOtherOpen} open={otherOpen} title={t("providerConnections.other.title")}><SelectField label={t("providerConnections.other.product")} onValueChange={setOtherProductId} options={[{ label: t("providerConnections.other.placeholder"), value: NO_PRODUCT }, ...otherOptions.map(({ label, value }) => ({ label, value }))]} value={otherProductId} /><div className="manage-actions"><Button disabled={otherProductId === NO_PRODUCT} onClick={chooseOther} type="button">{t("providerConnections.actions.choose")}</Button><Button onClick={() => setOtherOpen(false)} type="button" variant="outline">{t("providerConnections.actions.cancel")}</Button></div></ManageDialog>
    <ConfirmDialog confirmLabel={t("providerConnections.delete.confirm")} danger description={deleting ? t("providerConnections.delete.description", { name: deleting.alias }) : t("providerConnections.delete.descriptionGeneric")} onConfirm={() => { void remove() }} onOpenChange={(open) => { if (!open && pending === null) setDeleting(null) }} open={deleting !== null} pending={pending?.startsWith("delete:") ?? false} title={t("providerConnections.delete.title")} />
  </section>
}

function groupRemoteProductsByBrand(catalog: readonly ProviderProduct[]): readonly ProviderBrandGroup[] {
  const groups = new Map<string, { brand: ProviderProduct["brand"]; products: ProviderProduct[] }>()
  for (const product of catalog) {
    if (product.catalog_id === "ollama" || product.brand.brand_id === "custom") continue
    const existing = groups.get(product.brand.brand_id)
    if (existing) existing.products.push(product)
    else groups.set(product.brand.brand_id, { brand: product.brand, products: [product] })
  }
  return [...groups.values()]
}

function featuredBrandRank(brandId: string): number {
  const rank = FEATURED_BRAND_ORDER.indexOf(brandId as typeof FEATURED_BRAND_ORDER[number])
  return rank === -1 ? FEATURED_BRAND_ORDER.length : rank
}

function waitForOAuthPoll(delayMs: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason ?? new DOMException("Authorization cancelled", "AbortError"))
      return
    }
    const aborted = (): void => {
      window.clearTimeout(timeout)
      reject(signal.reason ?? new DOMException("Authorization cancelled", "AbortError"))
    }
    const timeout = window.setTimeout(() => {
      signal.removeEventListener("abort", aborted)
      resolve()
    }, delayMs)
    signal.addEventListener("abort", aborted, { once: true })
  })
}

function ConfiguredConnectionCard({ busy, connection, onDelete, onEdit, onForceFull, onLifecycle, onModels, onVerify }: {
  readonly busy: boolean
  readonly connection: ProviderConnection
  readonly onDelete: () => void
  readonly onEdit: () => void
  readonly onForceFull: () => void
  readonly onLifecycle: (action: ProviderLifecycleAction) => void
  readonly onModels: () => void
  readonly onVerify: () => void
}) {
  const { t } = useTranslation("manage")
  const activeModels = connection.models.filter((model) => !model.hidden && !model.retired && model.discovery_state !== "source_missing")
  const enabledCount = activeModels.length
  const verifiedCount = activeModels.filter((model) => model.verification.status === "passed").length
  const failedCount = activeModels.filter((model) => model.verification.status === "failed").length
  const hasAvailability = activeModels.some((model) => model.verification.availability_status !== undefined)
  const availableCount = activeModels.filter((model) => {
    const status = model.verification.availability_status
    return status === "available"
  }).length
  const coreModels = activeModels.filter((model) => model.verification.is_core === true)
  const coreAvailableCount = coreModels.filter((model) => {
    const status = model.verification.availability_status
    return status === "available"
  }).length
  const health = hasAvailability
    ? availabilityCardHealth(connection, activeModels)
    : enabledCount === 0
      ? "never"
      : verifiedCount === enabledCount
        ? "passed"
        : verifiedCount > 0
          ? "partial"
          : failedCount > 0 ? "failed" : "never"
  const status = hasAvailability
    ? availabilityCardLabel(health, t)
    : health === "passed"
      ? t("providerConnections.status.passed")
      : health === "partial"
        ? t("providerConnections.status.partial")
        : health === "failed"
          ? t("providerConnections.status.failed")
          : t("providerConnections.status.never")
  const modelStats = hasAvailability
    ? t("providerConnections.card.availabilityStats", {
      total: enabledCount,
      available: availableCount,
      core: coreAvailableCount,
      coreTotal: coreModels.length,
    })
    : t("providerConnections.card.modelStats", { total: connection.models.length, enabled: enabledCount, verified: verifiedCount })
  const validationHint = connection.verification.needs_full_validation
    ? t("providerConnections.card.needsFullValidation")
    : connection.verification.needs_heartbeat
      ? t("providerConnections.card.needsHeartbeat")
      : connection.verification.validation_mode === "cached"
        ? t("providerConnections.card.cached")
        : null
  return <article className={`provider-card provider-card--${health}`}><div className="provider-card__title"><h4>{connection.alias}</h4><span className={`status-badge status-badge--${health}`}>{status}</span></div><p className="provider-card__model-stats">{modelStats}</p>{validationHint ? <small className="provider-card__validation-hint">{validationHint}</small> : null}<div className="manage-actions"><Button disabled={busy} onClick={onModels} type="button" variant="outline">{t("providerConnections.actions.models")}</Button><Button disabled={busy} onClick={onVerify} type="button" variant="outline">{busy ? t("providerConnections.actions.validating") : t("providerConnections.actions.validate")}</Button><Button disabled={busy} onClick={onEdit} type="button" variant="outline">{t("providerConnections.actions.edit")}</Button><ProviderLifecycleMenu archived={connection.archived} busy={busy} enabled={connection.enabled} onDelete={onDelete} onForceFull={onForceFull} onLifecycle={onLifecycle} /></div></article>
}

type AvailabilityModel = ProviderConnection["models"][number]

function availabilityCardHealth(
  connection: ProviderConnection,
  models: readonly AvailabilityModel[],
): "passed" | "partial" | "failed" | "never" {
  if (!connection.enabled || connection.archived || models.length === 0) return "never"
  const statuses = models.map((model) => model.verification.availability_status)
  if (statuses.every((status) => status === "available")) return "passed"
  if (statuses.some((status) => status === "available" || status === "degraded")) return "partial"
  return statuses.some((status) => status === "unavailable") ? "failed" : "never"
}

function availabilityCardLabel(
  health: "passed" | "partial" | "failed" | "never",
  t: (key: string) => string,
): string {
  switch (health) {
    case "passed": return t("providerConnections.status.available")
    case "partial": return t("providerConnections.status.degraded")
    case "failed": return t("providerConnections.status.unavailable")
    case "never": return t("providerConnections.status.unknown")
  }
}
