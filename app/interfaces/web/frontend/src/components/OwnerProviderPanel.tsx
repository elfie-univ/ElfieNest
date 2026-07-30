import { Button } from "@/components/ui/button"
import { useEffect, useMemo, useState } from "react"

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
import { ApiError } from "../api/client"
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
  const [catalog, setCatalog] = useState<readonly ProviderProduct[]>([])
  const [connections, setConnections] = useState<readonly ProviderConnection[]>([])
  const [editing, setEditing] = useState<EditTarget | null>(null)
  const [viewingModels, setViewingModels] = useState<ProviderConnection | null>(null)
  const [deleting, setDeleting] = useState<ProviderConnection | null>(null)
  const [moreTarget, setMoreTarget] = useState<ProviderConnection | null>(null)
  const [creatingCustom, setCreatingCustom] = useState(false)
  const [otherOpen, setOtherOpen] = useState(false)
  const [otherProductId, setOtherProductId] = useState(NO_PRODUCT)
  const [matrixOpen, setMatrixOpen] = useState(false)
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = async (): Promise<void> => {
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
      setError(reason instanceof ApiError ? reason.message : "模型订阅加载失败")
    }
  }
  useEffect(() => { void load() }, [])

  const productsById = useMemo(
    () => new Map(catalog.map((product) => [product.catalog_id, product])),
    [catalog],
  )
  const configured = [...connections].sort(
    (left, right) => connectionPriority(left) - connectionPriority(right) || left.alias.localeCompare(right.alias),
  )
  const featured = catalog.filter((product) => FEATURED_PRODUCTS.has(product.catalog_id))
  const otherProducts = catalog.filter(
    (product) => !FEATURED_PRODUCTS.has(product.catalog_id)
      && product.catalog_id !== "ollama",
  )

  const save = async (draft: ProviderConnectionUpdate): Promise<void> => {
    if (!editing) return
    try {
      const result = editing.connection
        ? await updateProviderConnection(editing.connection.connection_id, draft, csrfToken)
        : await createProviderConnection(
          { catalog_id: editing.product.catalog_id, ...draft },
          csrfToken,
        )
      setNotice(result.model_refresh?.message
        ?? `${result.alias} 已保存并完成验证；可在“查看模型”中维护模型清单。`)
      setEditing(null)
      await load()
      if (result.model_refresh?.status === "failed") setViewingModels(result)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "订阅配置没有保存")
      throw reason
    }
  }

  const saveCustom = async (draft: ProviderConnectionDraft): Promise<void> => {
    const result = await createProviderConnection(draft, csrfToken)
    setError(null)
    setNotice(result.model_refresh?.message ?? `${result.alias} 已添加并完成验证。`)
    setCreatingCustom(false)
    await load()
    if (result.model_refresh?.status === "failed") setViewingModels(result)
  }

  const verify = async (connection: ProviderConnection): Promise<void> => {
    setPending(`verify:${connection.connection_id}`)
    try {
      await verifyProviderConnection(connection.connection_id, csrfToken)
      setNotice(`${connection.alias} 验证已完成。`)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "订阅验证失败")
    } finally {
      setPending(null)
    }
  }

  const verifyBatch = async (): Promise<void> => {
    setPending("batch")
    try {
      const result = await validateAllProviderModels(csrfToken)
      const passed = result.results.filter((item) => item.status === "passed").length
      setNotice(`全部验证完成：${passed} 项通过，报告 ${result.run_id}。`)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "批量验证失败")
    } finally {
      setPending(null)
    }
  }

  const lifecycle = async (action: "enable" | "disable" | "archive" | "restore"): Promise<void> => {
    if (!moreTarget) return
    setPending(`${action}:${moreTarget.connection_id}`)
    try {
      await changeProviderConnectionLifecycle(moreTarget.connection_id, action, csrfToken)
      setNotice(`${moreTarget.alias} 状态已更新。`)
      setMoreTarget(null)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "连接状态没有更新")
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
      <div><h2>供应商与模型连接</h2><p>一个品牌可以配置多个订阅账号；模型和粮食始终引用稳定的连接实例。</p></div>
      <div className="manage-actions">
        <Button disabled={pending !== null || configured.length === 0} onClick={() => { void verifyBatch() }} type="button">{pending === "batch" ? "验证中…" : "批量验证"}</Button>
        <Button onClick={() => setMatrixOpen(true)} type="button">跨订阅模型对比</Button>
        <RefreshButton disabled={pending !== null} label="重新读取" onClick={() => { void load() }} />
      </div>
    </div>
    {error ? <Notice kind="error" message={error} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <section aria-labelledby="configured-provider-title" className="provider-section">
      <div className="provider-section__heading"><div><h3 id="configured-provider-title">已配置的订阅</h3><p>连接状态、模型数量和验证结果分别记录。</p></div><span>{configured.length} 个</span></div>
      {configured.length === 0 ? <p className="empty-state">尚未配置模型订阅。</p> : <div className="provider-grid">{configured.map((connection) => <ConfiguredProviderCard
        busy={pending?.endsWith(connection.connection_id) ?? false}
        connection={connection}
        key={connection.connection_id}
        onEdit={() => {
          const product = productsById.get(connection.catalog_id)
          if (product) setEditing({ connection, product })
        }}
        onModels={() => setViewingModels(connection)}
        onMore={() => setMoreTarget(connection)}
        onVerify={() => { void verify(connection) }}
        product={productsById.get(connection.catalog_id)}
      />)}</div>}
    </section>
    <section aria-labelledby="available-provider-title" className="provider-section provider-section--available">
      <div className="provider-section__heading"><div><h3 id="available-provider-title">添加新的订阅</h3><p>常用产品只需填写 API Key；系统自动生成 ID、验证连接并读取模型。</p></div></div>
      <div className="provider-grid">{featured.map((product) => <button
        aria-label={`配置 ${product.name}`}
        className="provider-card provider-card--available provider-product-card"
        key={product.catalog_id}
        onClick={() => setEditing({ connection: null, product })}
        type="button"
      >
        <BrandMark product={product} />
        <span>{connectionMethodLabel(product)}</span>
      </button>)}<button aria-label="添加其他订阅" className="provider-card provider-card--add" onClick={() => setOtherOpen(true)} type="button"><Icon name="plus" size={28} /><strong>添加其他订阅</strong><span>选择内置产品或自定义连接</span></button></div>
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
      confirmLabel="确认删除"
      danger
      description={deleting ? `将删除 ${deleting.alias} 的本机密钥和模型清单。若粮食仍在引用，系统会拒绝删除。` : "确认删除这个订阅连接吗？"}
      onConfirm={() => { void remove() }}
      onOpenChange={(open) => { if (!open && pending === null) setDeleting(null) }}
      open={deleting !== null}
      pending={pending?.startsWith("delete:") ?? false}
      title="删除模型订阅"
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

function ConfiguredProviderCard({ busy, connection, onEdit, onModels, onMore, onVerify, product }: {
  readonly busy: boolean
  readonly connection: ProviderConnection
  readonly onEdit: () => void
  readonly onModels: () => void
  readonly onMore: () => void
  readonly onVerify: () => void
  readonly product: ProviderProduct | undefined
}) {
  const verification = connection.verification
  return <article className={`provider-card provider-card--${verification.status}`}>
    <div className="provider-card__title"><div><h4>{connection.alias}</h4>{product && connection.alias !== product.name ? <p>{product.name}</p> : null}</div><div className="provider-card__badges"><span className="status-badge status-badge--configured">已配置</span><span className={`status-badge status-badge--${verification.status}`}>{verificationLabel(verification.status)}</span></div></div>
    <p>{product ? connectionMethodLabel(product) : connection.api_mode} · {connection.models.filter((model) => !model.hidden).length} 个模型</p>
    <dl><dt>上次验证</dt><dd>{verification.checked_at ? new Date(verification.checked_at).toLocaleString() : "从未验证"}</dd><dt>延迟</dt><dd>{verification.latency_ms === null ? "未提供" : `${Math.round(verification.latency_ms)}ms`}</dd></dl>
    {verification.error ? <p className="provider-card__error">{verification.error}</p> : null}
    <div className="manage-actions">
      <Button aria-label={`查看 ${connection.alias} 的模型`} disabled={busy} onClick={onModels} type="button" variant="outline">模型</Button>
      <Button aria-label={`验证 ${connection.alias}`} disabled={busy} onClick={onVerify} type="button" variant="outline">{busy ? "验证中…" : "验证"}</Button>
      <Button aria-label={`修改 ${connection.alias}`} disabled={busy || !product} onClick={onEdit} type="button" variant="outline">修改</Button>
      <Button aria-label={`${connection.alias} 更多操作`} disabled={busy} onClick={onMore} type="button" variant="outline">更多</Button>
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

function connectionPriority(connection: ProviderConnection): number {
  if (connection.catalog_id === "ollama") return 0
  return connection.verification.status === "passed" ? 1 : connection.verification.status === "never" ? 2 : 3
}

function verificationLabel(status: ProviderConnection["verification"]["status"]): string {
  return status === "passed" ? "验证通过" : status === "failed" ? "验证失败" : "未验证"
}

function connectionMethodLabel(product: ProviderProduct): string {
  if (product.connection_method === "local") return "本地服务"
  if (product.connection_method === "oauth") return product.oauth_available ? "登录授权" : "登录授权待接入"
  return "API Key"
}
