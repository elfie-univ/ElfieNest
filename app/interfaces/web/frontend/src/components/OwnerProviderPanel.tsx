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
import { CustomProviderDialog } from "./CustomProviderDialog"
import { ManageDialog } from "./ManageDialog"
import { ModelMatrixDialog } from "./ModelMatrixDialog"
import { Notice } from "./Notice"
import { ProviderFormDialog } from "./ProviderFormDialog"
import { ProviderModelsDialog } from "./ProviderModelsDialog"
import { RefreshButton } from "./RefreshButton"
import { SelectField } from "./SelectField"

type EditTarget = {
  readonly connection: ProviderConnection | null
  readonly product: ProviderProduct
}

const NO_PRODUCT = "__none__"

export function OwnerProviderPanel({ csrfToken }: { readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [catalog, setCatalog] = useState<readonly ProviderProduct[]>([])
  const [connections, setConnections] = useState<readonly ProviderConnection[]>([])
  const [editing, setEditing] = useState<EditTarget | null>(null)
  const [viewingModels, setViewingModels] = useState<ProviderConnection | null>(null)
  const [moreTarget, setMoreTarget] = useState<ProviderConnection | null>(null)
  const [deleting, setDeleting] = useState<ProviderConnection | null>(null)
  const [creatingCustom, setCreatingCustom] = useState(false)
  const [otherOpen, setOtherOpen] = useState(false)
  const [otherProductId, setOtherProductId] = useState(NO_PRODUCT)
  const [matrixOpen, setMatrixOpen] = useState(false)
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [notice, setNotice] = useState<string | null>(null)

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
  const configured = [...connections].sort((left, right) => compareLocalizedText(left.alias, right.alias, locale))

  const save = async (draft: ProviderConnectionUpdate): Promise<void> => {
    if (!editing) return
    try {
      const result = editing.connection
        ? await updateProviderConnection(editing.connection.connection_id, draft, csrfToken)
        : await createProviderConnection({ catalog_id: editing.product.catalog_id, ...draft }, csrfToken)
      setNotice(result.model_refresh?.message ?? t("providerConnections.notices.saved", { name: result.alias }))
      setEditing(null)
      await load()
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
      throw reason
    }
  }

  const saveCustom = async (draft: ProviderConnectionDraft): Promise<void> => {
    const result = await createProviderConnection(draft, csrfToken)
    setNotice(result.model_refresh?.message ?? t("providerConnections.notices.added", { name: result.alias }))
    setCreatingCustom(false)
    await load()
  }

  const verify = async (connection: ProviderConnection): Promise<void> => {
    setPending(`verify:${connection.connection_id}`)
    try {
      await verifyProviderConnection(connection.connection_id, csrfToken)
      setNotice(t("providerConnections.notices.validated", { name: connection.alias }))
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

  const lifecycle = async (action: "enable" | "disable" | "archive" | "restore"): Promise<void> => {
    if (!moreTarget) return
    setPending(`${action}:${moreTarget.connection_id}`)
    try {
      await changeProviderConnectionLifecycle(moreTarget.connection_id, action, csrfToken)
      setMoreTarget(null)
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
    const product = productsById.get(otherProductId)
    if (!product) return
    setOtherOpen(false)
    setOtherProductId(NO_PRODUCT)
    if (product.catalog_id === "custom_openai") setCreatingCustom(true)
    else setEditing({ connection: null, product })
  }

  return <section className="manage-card manage-card--wide provider-page">
    <div className="manage-head"><div><h2>{t("providerConnections.title")}</h2><p>{t("providerConnections.description")}</p></div><div className="manage-actions">
      <Button disabled={pending !== null || configured.length === 0} onClick={() => { void runValidation() }} type="button">{pending === "batch" ? t("providerConnections.actions.validating") : t("providerConnections.actions.batchValidate")}</Button>
      <Button onClick={() => setMatrixOpen(true)} type="button">{t("providerConnections.actions.matrix")}</Button>
      <RefreshButton disabled={pending !== null} label={t("providerConnections.actions.refresh")} onClick={() => { void load() }} />
    </div></div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.load")} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <section aria-labelledby="configured-provider-title" className="provider-section"><div className="provider-section__heading"><div><h3 id="configured-provider-title">{t("providerConnections.section.configuredTitle")}</h3><p>{t("providerConnections.section.configuredDescription")}</p></div><span>{t("providerConnections.section.count", { count: configured.length })}</span></div>
      {configured.length === 0 ? <p className="empty-state">{t("providerConnections.section.configuredEmpty")}</p> : <div className="provider-grid">{configured.map((connection) => <ConfiguredConnectionCard
        busy={pending?.endsWith(connection.connection_id) ?? false}
        connection={connection}
        key={connection.connection_id}
        onEdit={() => { const product = productsById.get(connection.catalog_id); if (product) setEditing({ connection, product }) }}
        onModels={() => setViewingModels(connection)}
        onMore={() => setMoreTarget(connection)}
        onVerify={() => { void verify(connection) }}
      />)}</div>}
    </section>
    <section aria-labelledby="available-provider-title" className="provider-section provider-section--available"><div className="provider-section__heading"><div><h3 id="available-provider-title">{t("providerConnections.available.title")}</h3><p>{t("providerConnections.available.description")}</p></div></div><div className="provider-grid">
      {catalog.filter((product) => product.catalog_id !== "custom_openai").map((product) => <button aria-label={t("providerConnections.actions.configure", { name: product.name })} className="provider-card provider-card--available" key={product.catalog_id} onClick={() => setEditing({ connection: null, product })} type="button"><strong>{product.name}</strong><span>{product.connection_method}</span></button>)}
      <button aria-label={t("providerConnections.actions.addCustom")} className="provider-card provider-card--add" onClick={() => setCreatingCustom(true)} type="button"><strong>{t("providerConnections.actions.addCustom")}</strong><span>{t("providerConnections.available.customDescription")}</span></button>
      <button aria-label={t("providerConnections.actions.addOther")} className="provider-card provider-card--add" onClick={() => setOtherOpen(true)} type="button"><strong>{t("providerConnections.actions.addOther")}</strong></button>
    </div></section>
    <ProviderFormDialog connection={editing?.connection ?? null} onOpenChange={(open) => { if (!open) setEditing(null) }} onSave={save} open={editing !== null} product={editing?.product ?? null} />
    <CustomProviderDialog onOpenChange={setCreatingCustom} onSave={saveCustom} open={creatingCustom} />
    <ProviderModelsDialog connection={viewingModels} csrfToken={csrfToken} onChanged={load} onOpenChange={(open) => { if (!open) setViewingModels(null) }} open={viewingModels !== null} />
    <ModelMatrixDialog csrfToken={csrfToken} onOpenChange={setMatrixOpen} open={matrixOpen} />
    <ManageDialog description={t("providerConnections.other.description")} onOpenChange={setOtherOpen} open={otherOpen} title={t("providerConnections.other.title")}><SelectField label={t("providerConnections.other.product")} onValueChange={setOtherProductId} options={[{ label: t("providerConnections.other.placeholder"), value: NO_PRODUCT }, ...catalog.map((product) => ({ label: product.name, value: product.catalog_id }))]} value={otherProductId} /><div className="manage-actions"><Button disabled={otherProductId === NO_PRODUCT} onClick={chooseOther} type="button">{t("providerConnections.actions.choose")}</Button><Button onClick={() => setOtherOpen(false)} type="button" variant="outline">{t("providerConnections.actions.cancel")}</Button></div></ManageDialog>
    <ConfirmDialog confirmLabel={t("providerConnections.delete.confirm")} danger description={deleting ? t("providerConnections.delete.description", { name: deleting.alias }) : t("providerConnections.delete.descriptionGeneric")} onConfirm={() => { void remove() }} onOpenChange={(open) => { if (!open && pending === null) setDeleting(null) }} open={deleting !== null} pending={pending?.startsWith("delete:") ?? false} title={t("providerConnections.delete.title")} />
    <ManageDialog description={moreTarget ? t("providerConnections.lifecycle.description", { name: moreTarget.alias }) : ""} onOpenChange={(open) => { if (!open) setMoreTarget(null) }} open={moreTarget !== null} title={t("providerConnections.lifecycle.title")}>{moreTarget ? <div className="manage-actions">{moreTarget.archived ? <Button onClick={() => { void lifecycle("restore") }} type="button">{t("providerConnections.actions.restore")}</Button> : moreTarget.enabled ? <Button onClick={() => { void lifecycle("disable") }} type="button" variant="outline">{t("providerConnections.actions.disable")}</Button> : <Button onClick={() => { void lifecycle("enable") }} type="button">{t("providerConnections.actions.enable")}</Button>}{!moreTarget.archived ? <Button onClick={() => { void lifecycle("archive") }} type="button" variant="outline">{t("providerConnections.actions.archive")}</Button> : null}<Button disabled={!moreTarget.archived} onClick={() => { setDeleting(moreTarget); setMoreTarget(null) }} type="button" variant="outline">{t("providerConnections.actions.delete")}</Button></div> : null}</ManageDialog>
  </section>
}

function ConfiguredConnectionCard({ busy, connection, onEdit, onModels, onMore, onVerify }: {
  readonly busy: boolean
  readonly connection: ProviderConnection
  readonly onEdit: () => void
  readonly onModels: () => void
  readonly onMore: () => void
  readonly onVerify: () => void
}) {
  const { t } = useTranslation("manage")
  const status = connection.verification.status === "passed" ? t("providerConnections.status.passed") : connection.verification.status === "failed" ? t("providerConnections.status.failed") : t("providerConnections.status.never")
  return <article className={`provider-card provider-card--${connection.verification.status}`}><div className="provider-card__title"><h4>{connection.alias}</h4><span className={`status-badge status-badge--${connection.verification.status}`}>{status}</span></div><p>{t("providerConnections.card.visibleModels", { count: connection.models.filter((model) => !model.hidden).length })}</p><div className="manage-actions"><Button disabled={busy} onClick={onModels} type="button" variant="outline">{t("providerConnections.actions.models")}</Button><Button disabled={busy} onClick={onVerify} type="button" variant="outline">{busy ? t("providerConnections.actions.validating") : t("providerConnections.actions.validate")}</Button><Button disabled={busy} onClick={onEdit} type="button" variant="outline">{t("providerConnections.actions.edit")}</Button><Button disabled={busy} onClick={onMore} type="button" variant="outline">{t("providerConnections.actions.more")}</Button></div></article>
}
