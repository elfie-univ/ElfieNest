import { Button } from "@/components/ui/button"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  changeProviderConnectionLifecycle,
  createProviderConnection,
  deleteProviderConnection,
  ownerProviderCatalog,
  ownerProviderConnections,
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
  readonly product: ProviderProduct
}

type OtherSubscriptionOption =
  | { readonly kind: "catalog"; readonly label: string; readonly product: ProviderProduct; readonly value: string }
  | { readonly kind: "interface"; readonly label: string; readonly preset: CustomProviderPreset; readonly value: string }

const NO_PRODUCT = "__none__"
const OPENAI_INTERFACE_OPTION = "__openai_interface__"
const ANTHROPIC_INTERFACE_OPTION = "__anthropic_interface__"
const FEATURED_PRODUCT_LIMIT = 8

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
  const featuredProducts = useMemo(() => catalog
    .filter((product) => product.catalog_id !== "ollama" && product.catalog_id !== "custom_openai")
    .slice(0, FEATURED_PRODUCT_LIMIT), [catalog])
  const featuredProductIds = useMemo(() => new Set(featuredProducts.map((product) => product.catalog_id)), [featuredProducts])
  const otherProducts = useMemo(() => catalog.filter((product) => product.catalog_id !== "ollama"
    && product.catalog_id !== "custom_openai"
    && !featuredProductIds.has(product.catalog_id)), [catalog, featuredProductIds])
  const otherOptions = useMemo<readonly OtherSubscriptionOption[]>(() => [
    ...otherProducts.map((product) => ({ kind: "catalog" as const, label: product.name, product, value: product.catalog_id })),
    { kind: "interface" as const, label: t("providerConnections.other.openaiInterface"), preset: "openai" as const, value: OPENAI_INTERFACE_OPTION },
    { kind: "interface" as const, label: t("providerConnections.other.anthropicInterface"), preset: "anthropic" as const, value: ANTHROPIC_INTERFACE_OPTION },
  ], [otherProducts, t])

  const save = async (draft: ProviderConnectionUpdate): Promise<void> => {
    if (!editing) return
    try {
      const result = editing.connection
        ? await updateProviderConnection(editing.connection.connection_id, draft, csrfToken)
        : await createProviderConnection({ catalog_id: editing.product.catalog_id, ...draft }, csrfToken)
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
      setEditing({ connection: null, product: option.product })
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
        onEdit={() => { const product = productsById.get(connection.catalog_id); if (product) setEditing({ connection, product }) }}
        onModels={() => setViewingModels(connection)}
        onDelete={() => setDeleting(connection)}
        onLifecycle={(action) => { void lifecycle(connection, action) }}
        onVerify={() => { void verify(connection) }}
      />)}</div>}
    </section>
    <section aria-labelledby="available-provider-title" className="provider-section provider-section--available"><div className="provider-section__heading"><div><h3 id="available-provider-title">{t("providerConnections.available.title")}</h3></div></div><div className="provider-grid">
      {featuredProducts.map((product) => <button aria-label={t("providerConnections.actions.configure", { name: product.name })} className="provider-card provider-card--available" key={product.catalog_id} onClick={() => setEditing({ connection: null, product })} type="button"><span className="provider-card__brand"><ProviderBrandLogo product={product} /><strong>{product.name}</strong></span></button>)}
      <button aria-label={t("providerConnections.actions.addOther")} className="provider-card provider-card--add" onClick={() => setOtherOpen(true)} type="button"><span className="provider-card__add-mark"><Icon name="plus" size={24} /></span><strong>{t("providerConnections.actions.addOther")}</strong></button>
    </div></section>
    <ProviderFormDialog connection={editing?.connection ?? null} onOpenChange={(open) => { if (!open) setEditing(null) }} onSave={save} open={editing !== null} product={editing?.product ?? null} />
    <CustomProviderDialog onOpenChange={setCreatingCustom} onSave={saveCustom} open={creatingCustom} preset={customPreset} />
    <ProviderModelsDialog connection={viewingModels} csrfToken={csrfToken} onChanged={load} onOpenChange={(open) => { if (!open) setViewingModels(null) }} open={viewingModels !== null} />
    <ModelMatrixDialog csrfToken={csrfToken} onOpenChange={setMatrixOpen} open={matrixOpen} />
    <ManageDialog onOpenChange={setOtherOpen} open={otherOpen} title={t("providerConnections.other.title")}><SelectField label={t("providerConnections.other.product")} onValueChange={setOtherProductId} options={[{ label: t("providerConnections.other.placeholder"), value: NO_PRODUCT }, ...otherOptions.map(({ label, value }) => ({ label, value }))]} value={otherProductId} /><div className="manage-actions"><Button disabled={otherProductId === NO_PRODUCT} onClick={chooseOther} type="button">{t("providerConnections.actions.choose")}</Button><Button onClick={() => setOtherOpen(false)} type="button" variant="outline">{t("providerConnections.actions.cancel")}</Button></div></ManageDialog>
    <ConfirmDialog confirmLabel={t("providerConnections.delete.confirm")} danger description={deleting ? t("providerConnections.delete.description", { name: deleting.alias }) : t("providerConnections.delete.descriptionGeneric")} onConfirm={() => { void remove() }} onOpenChange={(open) => { if (!open && pending === null) setDeleting(null) }} open={deleting !== null} pending={pending?.startsWith("delete:") ?? false} title={t("providerConnections.delete.title")} />
  </section>
}

function ConfiguredConnectionCard({ busy, connection, onDelete, onEdit, onLifecycle, onModels, onVerify }: {
  readonly busy: boolean
  readonly connection: ProviderConnection
  readonly onDelete: () => void
  readonly onEdit: () => void
  readonly onLifecycle: (action: ProviderLifecycleAction) => void
  readonly onModels: () => void
  readonly onVerify: () => void
}) {
  const { t } = useTranslation("manage")
  const enabledCount = connection.models.filter((model) => !model.hidden).length
  const verifiedCount = connection.models.filter((model) => model.verification.status === "passed").length
  const availableCount = connection.models.filter((model) => !model.hidden && model.available && model.verification.status === "passed").length
  const health = enabledCount === 0
    ? "never"
    : availableCount === enabledCount
      ? "passed"
      : availableCount > 0
        ? "partial"
        : "failed"
  const status = health === "passed"
    ? t("providerConnections.status.passed")
    : health === "partial"
      ? t("providerConnections.status.partial")
      : health === "failed"
        ? t("providerConnections.status.failed")
        : t("providerConnections.status.never")
  return <article className={`provider-card provider-card--${health}`}><div className="provider-card__title"><h4>{connection.alias}</h4><span className={`status-badge status-badge--${health}`}>{status}</span></div><p className="provider-card__model-stats">{t("providerConnections.card.modelStats", { total: connection.models.length, enabled: enabledCount, verified: verifiedCount })}</p><div className="manage-actions"><Button disabled={busy} onClick={onModels} type="button" variant="outline">{t("providerConnections.actions.models")}</Button><Button disabled={busy} onClick={onVerify} type="button" variant="outline">{busy ? t("providerConnections.actions.validating") : t("providerConnections.actions.validate")}</Button><Button disabled={busy} onClick={onEdit} type="button" variant="outline">{t("providerConnections.actions.edit")}</Button><ProviderLifecycleMenu archived={connection.archived} busy={busy} enabled={connection.enabled} onDelete={onDelete} onLifecycle={onLifecycle} /></div></article>
}
