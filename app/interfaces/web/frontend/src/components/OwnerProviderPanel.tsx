import { Button } from "@/components/ui/button"
import { useCallback, useEffect, useState } from "react"
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
import {
  compareLocalizedText,
  currentLocale,
  formatDateTime,
} from "../i18n/format"
import { describeApiError, localizeBackendDetail, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import type { SupportedLocale } from "../i18n/locale"
import { ConfirmDialog } from "./ConfirmDialog"
import { CustomProviderDialog } from "./CustomProviderDialog"
import { Icon } from "./Icon"
import { ManageDialog } from "./ManageDialog"
import { ModelMatrixDialog } from "./ModelMatrixDialog"
import { Notice } from "./Notice"
import { ProviderFormDialog } from "./ProviderFormDialog"
import { ProviderModelsDialog } from "./ProviderModelsDialog"
import { RefreshButton } from "./RefreshButton"
import { SelectField } from "./SelectField"

const FEATURED_PRODUCTS = new Set([
  "openai_api",
  "anthropic_api",
  "qwen_api",
  "deepseek_api",
  "gemini_api",
])
const LOCAL_BRAND_LOGOS = new Set([
  "ollama",
  "anthropic",
  "deepseek",
  "google",
  "alibaba",
  "xai",
  "mistral",
])
const NO_PRODUCT = "__none__"

type EditTarget = {
  readonly connection: ProviderConnection | null
  readonly product: ProviderProduct
}

export function OwnerProviderPanel({ csrfToken }: { readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [providers, setProviders] = useState<readonly ProviderView[]>([])
  const [editing, setEditing] = useState<ProviderView | null>(null)
  const [deleting, setDeleting] = useState<ProviderView | null>(null)
  const [creating, setCreating] = useState(false)
  const [matrixOpen, setMatrixOpen] = useState(false)
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = useCallback(async (): Promise<void> => {
    try {
      const [nextCatalog, nextConnections] = await Promise.all([
        ownerProviderCatalog(),
        ownerProviderConnections(),
      ])
      setCatalog(nextCatalog)
      setConnections(nextConnections)
      setViewingModels((current) => current
        ? nextConnections.find((item) => item.connection_id === current.connection_id) ?? null
        : null)
      setError(null)
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.load"))
    }
  }, [])
  useEffect(() => { void load() }, [load])

  const configured = providers
    .filter((provider) => provider.configured)
    .sort((left, right) => providerPriority(left) - providerPriority(right) || compareLocalizedText(left.name, right.name, locale))
  const available = providers
    .filter((provider) => !provider.configured)
    .sort((left, right) => compareLocalizedText(left.name, right.name, locale))

  const save = async (draft: ProviderConnectionUpdate): Promise<void> => {
    if (!editing) return
    try {
      await updateProvider(editing.provider_id, draft, csrfToken)
      setNotice(t("providers.notices.saved", { name: editing.name }))
      setEditing(null)
      await load()
      if (result.model_refresh?.status === "failed") setViewingModels(result)
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
      throw reason
    }
  }
  const saveCustom = async (draft: ProviderDraft): Promise<void> => {
    try {
      await createProvider(draft, csrfToken)
      setNotice(t("providers.notices.added", { name: draft.display_name || draft.provider_id || t("providers.custom.title") }))
      setCreating(false)
      await load()
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
      throw reason
    }
  }

  const verify = async (connection: ProviderConnection): Promise<void> => {
    setPending(`verify:${connection.connection_id}`)
    try {
      await verifyProvider(provider.provider_id, csrfToken)
      setNotice(t("providers.notices.verified", { name: provider.name }))
      await load()
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(null)
    }
  }

  const verifyBatch = async (): Promise<void> => {
    setPending("batch")
    try {
      const result = await validateAllProviderModels(csrfToken)
      const passed = result.results.filter((item) => item.status === "passed").length
      const failed = result.results.filter((item) => item.status === "failed").length
      setNotice(t("providers.notices.batchVerified", { failed, passed }))
      await load()
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(null)
    }
  }

  const lifecycle = async (action: "enable" | "disable" | "archive" | "restore"): Promise<void> => {
    if (!moreTarget) return
    setPending(`${action}:${moreTarget.connection_id}`)
    try {
      await deleteProvider(deleting.provider_id, csrfToken)
      setNotice(t("providers.notices.deleted", { name: deleting.name }))
      setDeleting(null)
      await load()
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.delete"))
    } finally {
      setPending(null)
    }
  }

  const remove = async (): Promise<void> => {
    if (!deleting) return
    setPending(`delete:${deleting.connection_id}`)
    try {
      await deleteProviderConnection(deleting.connection_id, csrfToken)
      setNotice(`${deleting.alias} 的本机连接已删除。`)
      setDeleting(null)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "订阅连接没有删除")
    } finally {
      setPending(null)
    }
  }

  const chooseOther = (): void => {
    const product = catalog.find((item) => item.catalog_id === otherProductId)
    if (!product) return
    setOtherOpen(false)
    setOtherProductId(NO_PRODUCT)
    if (product.catalog_id === "custom_openai") setCreatingCustom(true)
    else setEditing({ connection: null, product })
  }

  return <section className="manage-card manage-card--wide provider-page">
    <div className="manage-head">
      <div><h2>{t("providers.title")}</h2><p>{t("providers.description")}</p></div>
      <div className="manage-actions">
        <Button disabled={pending !== null || configured.length === 0} onClick={() => { void verifyBatch() }} type="button">{pending === "batch" ? t("providers.actions.verifying") : t("providers.actions.batchVerify")}</Button>
        <Button onClick={() => setMatrixOpen(true)} type="button">{t("providers.actions.showModels")}</Button>
        <RefreshButton disabled={pending !== null} label={t("providers.actions.refresh")} onClick={() => { void load() }} />
      </div>
    </div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <section aria-labelledby="configured-provider-title" className="provider-section">
      <div className="provider-section__heading"><div><h3 id="configured-provider-title">{t("providers.section.configuredTitle")}</h3><p>{t("providers.section.configuredDescription")}</p></div><span>{t("providers.section.configuredCount", { count: configured.length })}</span></div>
      {configured.length === 0 ? <p className="empty-state">{t("providers.section.configuredEmpty")}</p> : <div className="provider-grid">{configured.map((provider) => <ConfiguredProviderCard
        busy={pending?.endsWith(provider.provider_id) ?? false}
        key={provider.provider_id}
        onDelete={() => setDeleting(provider)}
        onEdit={() => setEditing(provider)}
        onVerify={() => { void verify(provider) }}
        provider={provider}
        locale={locale}
      />)}</div>}
    </section>
    <section aria-labelledby="available-provider-title" className="provider-section provider-section--available">
      <div className="provider-section__heading"><div><h3 id="available-provider-title">{t("providers.section.availableTitle")}</h3><p>{t("providers.section.availableDescription")}</p></div><span>{t("providers.section.availableCount", { count: available.length })}</span></div>
      <div className="provider-grid">{available.map((provider) => <article className="provider-card provider-card--available" key={provider.provider_id}>
        <div className="provider-card__title"><h4>{provider.name}</h4><span className="status-badge status-badge--muted">{t("providers.status.pending")}</span></div>
        <p>{t(connectionKey(provider))}</p>
        <Button variant="outline" aria-label={t("providers.actions.configureFor", { name: provider.name })} onClick={() => setEditing(provider)} type="button">{t("providers.actions.configure")}</Button>
      </article>)}<button aria-label={t("providers.actions.addCustom")} className="provider-card provider-card--add" data-slot="button" data-variant="outline" onClick={() => setCreating(true)} type="button"><Icon name="plus" size={28} /><strong>{t("providers.actions.addCustom")}</strong><span>{t("providers.custom.description")}</span></button></div>
    </section>
    <ProviderFormDialog
      connection={editing?.connection ?? null}
      onOpenChange={(open) => { if (!open) setEditing(null) }}
      onSave={save}
      open={editing !== null}
      product={editing?.product ?? null}
    />
    <CustomProviderDialog onOpenChange={setCreatingCustom} onSave={saveCustom} open={creatingCustom} />
    <ProviderModelsDialog connection={viewingModels} csrfToken={csrfToken} onChanged={load} onOpenChange={(open) => { if (!open) setViewingModels(null) }} open={viewingModels !== null} />
    <ModelMatrixDialog csrfToken={csrfToken} onOpenChange={setMatrixOpen} open={matrixOpen} />
    <ManageDialog description="选择一个已经内置地址、协议和认证方式的订阅产品。" onOpenChange={setOtherOpen} open={otherOpen} title="添加其他订阅">
      <SelectField label="订阅产品" onValueChange={setOtherProductId} options={[
        { label: "请选择", value: NO_PRODUCT },
        ...otherProducts.map((product) => ({ label: product.name, value: product.catalog_id })),
      ]} value={otherProductId} />
      <div className="manage-actions">
        <Button disabled={otherProductId === NO_PRODUCT} onClick={chooseOther} type="button">继续</Button>
        <Button onClick={() => setOtherOpen(false)} type="button" variant="outline">取消</Button>
      </div>
    </ManageDialog>
    <ConfirmDialog
      confirmLabel={t("providers.actions.confirmDelete")}
      danger
      description={deleting ? t("providers.delete.description", { name: deleting.name }) : t("providers.delete.descriptionGeneric")}
      onConfirm={() => { void remove() }}
      onOpenChange={(open) => { if (!open && pending === null) setDeleting(null) }}
      open={deleting !== null}
      pending={pending?.startsWith("delete:") ?? false}
      title={t("providers.delete.title")}
    />
    <ManageDialog description={moreTarget ? `管理 ${moreTarget.alias} 的生命周期；连接归档后才允许删除。` : ""} onOpenChange={(open) => { if (!open) setMoreTarget(null) }} open={moreTarget !== null} title="更多操作">
      {moreTarget ? <div className="manage-actions">
        {moreTarget.archived
          ? <Button onClick={() => { void lifecycle("restore") }} type="button">恢复</Button>
          : moreTarget.enabled
            ? <Button onClick={() => { void lifecycle("disable") }} type="button" variant="outline">停用</Button>
            : <Button onClick={() => { void lifecycle("enable") }} type="button">启用</Button>}
        {!moreTarget.archived ? <Button onClick={() => { void lifecycle("archive") }} type="button" variant="outline">归档</Button> : null}
        <Button disabled={!moreTarget.archived || moreTarget.catalog_id === "ollama"} onClick={() => { setDeleting(moreTarget); setMoreTarget(null) }} type="button" variant="outline">删除</Button>
      </div> : null}
    </ManageDialog>
  </section>
}

function ConfiguredProviderCard({ busy, locale, onDelete, onEdit, onVerify, provider }: {
  readonly busy: boolean
  readonly locale: SupportedLocale
  readonly onDelete: () => void
  readonly onEdit: () => void
  readonly onModels: () => void
  readonly onMore: () => void
  readonly onVerify: () => void
  readonly product: ProviderProduct | undefined
}) {
  const { t } = useTranslation("manage")
  const verification = provider.verification
  return <article className={`provider-card provider-card--${verification.status}`}>
    <div className="provider-card__title"><h4>{provider.name}</h4><div className="provider-card__badges"><span className="status-badge status-badge--configured">{t("providers.card.configured")}</span><span className={`status-badge status-badge--${verification.status}`}>{t(verificationKey(verification.status))}</span></div></div>
    <p>{t(connectionKey(provider))} · {t("providers.card.knownModels", { count: provider.models.length })}</p>
    <dl><dt>{t("providers.card.lastVerified")}</dt><dd>{verification.checked_at ? formatDateTime(verification.checked_at, locale) : t("providers.card.neverVerified")}</dd><dt>{t("providers.card.latency")}</dt><dd>{verification.latency_ms === null ? t("providers.card.notProvided") : `${Math.round(verification.latency_ms)}ms`}</dd></dl>
    {verification.error ? <p className="provider-card__error">{localizeBackendDetail(verification.error, "manage.load", locale)}</p> : null}
    <div className="manage-actions">
      <Button variant="outline" aria-label={t("providers.actions.editFor", { name: provider.name })} disabled={busy} onClick={onEdit} type="button">{t("providers.actions.edit")}</Button>
      <Button variant="outline" aria-label={t("providers.actions.verifyFor", { name: provider.name })} disabled={busy} onClick={onVerify} type="button">{busy ? t("providers.actions.verifying") : t("providers.actions.verify")}</Button>
      <Button variant="outline" aria-label={t("providers.actions.deleteFor", { name: provider.name })} disabled={busy || provider.provider_id === "ollama"} onClick={onDelete} type="button">{t("providers.actions.delete")}</Button>
    </div>
  </article>
}

function BrandMark({ product }: { readonly product: ProviderProduct }) {
  return <div className="provider-product-card__brand">
    <span aria-hidden="true" className={`provider-brand-mark provider-brand-mark--${product.brand.brand_id}`}>
      {LOCAL_BRAND_LOGOS.has(product.brand.brand_id) && product.brand.logo_asset
        ? <img alt="" src={`/${product.brand.logo_asset}`} />
        : product.brand.name.slice(0, 1)}
    </span>
    <strong>{product.name}</strong>
  </div>
}

function verificationKey(status: ProviderView["verification"]["status"]): "providers.status.failed" | "providers.status.never" | "providers.status.passed" {
  return status === "passed" ? "providers.status.passed" : status === "failed" ? "providers.status.failed" : "providers.status.never"
}

function connectionKey(provider: ProviderView): "providers.connection.apiKey" | "providers.connection.local" | "providers.connection.oauth" | "providers.connection.oauthUnavailable" {
  const method = provider.capabilities.connection_method
  if (method === "local") return "providers.connection.local"
  if (method === "oauth") return provider.capabilities.oauth_available ? "providers.connection.oauth" : "providers.connection.oauthUnavailable"
  return "providers.connection.apiKey"
}
