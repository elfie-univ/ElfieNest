import { useEffect, useState } from "react"

import {
  createProvider,
  deleteProvider,
  ownerProviders,
  updateProvider,
  verifyProvider,
  verifyProvidersBatch,
  type ProviderDraft,
  type ProviderView,
} from "../api/owner-providers"
import { ApiError } from "../api/client"
import { ConfirmDialog } from "./ConfirmDialog"
import { CustomProviderDialog } from "./CustomProviderDialog"
import { Icon } from "./Icon"
import { ModelMatrixDialog } from "./ModelMatrixDialog"
import { Notice } from "./Notice"
import { ProviderFormDialog } from "./ProviderFormDialog"

export function OwnerProviderPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [providers, setProviders] = useState<readonly ProviderView[]>([])
  const [editing, setEditing] = useState<ProviderView | null>(null)
  const [deleting, setDeleting] = useState<ProviderView | null>(null)
  const [creating, setCreating] = useState(false)
  const [matrixOpen, setMatrixOpen] = useState(false)
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const load = async (): Promise<void> => {
    try {
      setProviders(await ownerProviders())
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "模型订阅加载失败")
    }
  }
  useEffect(() => { void load() }, [])

  const configured = providers
    .filter((provider) => provider.configured)
    .sort((left, right) => providerPriority(left) - providerPriority(right) || left.name.localeCompare(right.name))
  const available = providers
    .filter((provider) => !provider.configured)
    .sort((left, right) => left.name.localeCompare(right.name))

  const save = async (draft: ProviderDraft): Promise<void> => {
    if (!editing) return
    try {
      await updateProvider(editing.provider_id, draft, csrfToken)
      setNotice(`${editing.name} 已保存；需要验证后才会标记可用。`)
      setEditing(null)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "供应商配置没有保存")
      throw reason
    }
  }
  const saveCustom = async (draft: ProviderDraft): Promise<void> => {
    try {
      await createProvider(draft, csrfToken)
      setNotice(`${draft.display_name || draft.provider_id || "自定义供应商"} 已添加；验证通过后才会标记可用。`)
      setCreating(false)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "自定义供应商没有添加")
      throw reason
    }
  }
  const verify = async (provider: ProviderView): Promise<void> => {
    setPending(`verify:${provider.provider_id}`)
    try {
      await verifyProvider(provider.provider_id, csrfToken)
      setNotice(`${provider.name} 验证已完成。`)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "供应商验证失败")
    } finally {
      setPending(null)
    }
  }
  const verifyBatch = async (): Promise<void> => {
    setPending("batch")
    try {
      const result = await verifyProvidersBatch(csrfToken)
      const passed = result.results.filter((item) => item.status === "passed").length
      const failed = result.results.filter((item) => item.status === "failed").length
      setNotice(`批量验证完成：${passed} 个通过，${failed} 个失败。`)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "批量验证失败")
    } finally {
      setPending(null)
    }
  }
  const remove = async (): Promise<void> => {
    if (!deleting) return
    setPending(`delete:${deleting.provider_id}`)
    try {
      await deleteProvider(deleting.provider_id, csrfToken)
      setNotice(`${deleting.name} 的本机配置已删除。`)
      setDeleting(null)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "供应商配置没有删除")
    } finally {
      setPending(null)
    }
  }

  return <section className="manage-card manage-card--wide provider-page">
    <div className="manage-head">
      <div><h2>供应商与模型连接</h2><p>配置与验证分开记录；只有真实验证通过后才显示可用。</p></div>
      <div className="manage-actions">
        <button className="button" disabled={pending !== null || configured.length === 0} onClick={() => { void verifyBatch() }} type="button">{pending === "batch" ? "验证中…" : "批量验证"}</button>
        <button className="button button--quiet" onClick={() => setMatrixOpen(true)} type="button">查看支持模型</button>
        <button className="button button--quiet" disabled={pending !== null} onClick={() => { void load() }} type="button">重新读取</button>
      </div>
    </div>
    {error ? <Notice kind="error" message={error} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <section aria-labelledby="configured-provider-title" className="provider-section">
      <div className="provider-section__heading"><div><h3 id="configured-provider-title">已配置的订阅</h3><p>Ollama 固定置顶；验证时间与延迟只来自真实检查。</p></div><span>{configured.length} 个</span></div>
      {configured.length === 0 ? <p className="empty-state">尚无完整配置的模型订阅。</p> : <div className="provider-grid">{configured.map((provider) => <ConfiguredProviderCard
        busy={pending?.endsWith(provider.provider_id) ?? false}
        key={provider.provider_id}
        onDelete={() => setDeleting(provider)}
        onEdit={() => setEditing(provider)}
        onVerify={() => { void verify(provider) }}
        provider={provider}
      />)}</div>}
    </section>
    <section aria-labelledby="available-provider-title" className="provider-section provider-section--available">
      <div className="provider-section__heading"><div><h3 id="available-provider-title">配置新的订阅</h3><p>未配置项只提供“配置”，不会出现无意义的验证或删除操作。</p></div><span>{available.length} 个</span></div>
      <div className="provider-grid">{available.map((provider) => <article className="provider-card provider-card--available" key={provider.provider_id}>
        <div className="provider-card__title"><h4>{provider.name}</h4><span className="status-badge status-badge--muted">待配置</span></div>
        <p>{connectionLabel(provider)}</p>
        <button aria-label={`配置 ${provider.name}`} className="button button--quiet" onClick={() => setEditing(provider)} type="button">配置</button>
      </article>)}<button aria-label="添加自定义供应商" className="provider-card provider-card--add" onClick={() => setCreating(true)} type="button"><Icon name="plus" size={28} /><strong>添加自定义供应商</strong><span>配置其他兼容接口或本地网关</span></button></div>
    </section>
    <ProviderFormDialog onOpenChange={(open) => { if (!open) setEditing(null) }} onSave={save} open={editing !== null} provider={editing} />
    <CustomProviderDialog onOpenChange={setCreating} onSave={saveCustom} open={creating} />
    <ModelMatrixDialog csrfToken={csrfToken} onOpenChange={setMatrixOpen} open={matrixOpen} />
    <ConfirmDialog
      confirmLabel="确认删除"
      danger
      description={deleting ? `将删除 ${deleting.name} 的本机密钥、模型清单和验证记录。此操作不会删除供应商账户。` : "确认删除这个供应商配置吗？"}
      onConfirm={() => { void remove() }}
      onOpenChange={(open) => { if (!open && pending === null) setDeleting(null) }}
      open={deleting !== null}
      pending={pending?.startsWith("delete:") ?? false}
      title="删除模型订阅"
    />
  </section>
}

function ConfiguredProviderCard({ busy, onDelete, onEdit, onVerify, provider }: {
  readonly busy: boolean
  readonly onDelete: () => void
  readonly onEdit: () => void
  readonly onVerify: () => void
  readonly provider: ProviderView
}) {
  const verification = provider.verification
  return <article className={`provider-card provider-card--${verification.status}`}>
    <div className="provider-card__title"><h4>{provider.name}</h4><div className="provider-card__badges"><span className="status-badge status-badge--configured">已配置</span><span className={`status-badge status-badge--${verification.status}`}>{verificationLabel(verification.status)}</span></div></div>
    <p>{connectionLabel(provider)} · {provider.models.length} 个已知模型</p>
    <dl><dt>上次验证</dt><dd>{verification.checked_at ? new Date(verification.checked_at).toLocaleString() : "从未验证"}</dd><dt>延迟</dt><dd>{verification.latency_ms === null ? "未提供" : `${Math.round(verification.latency_ms)}ms`}</dd></dl>
    {verification.error ? <p className="provider-card__error">{verification.error}</p> : null}
    <div className="manage-actions">
      <button aria-label={`修改 ${provider.name}`} className="button button--quiet" disabled={busy} onClick={onEdit} type="button">修改</button>
      <button aria-label={`验证 ${provider.name}`} className="button button--quiet" disabled={busy} onClick={onVerify} type="button">{busy ? "验证中…" : "验证"}</button>
      <button aria-label={`删除 ${provider.name}`} className="button button--quiet" disabled={busy || provider.provider_id === "ollama"} onClick={onDelete} type="button">删除</button>
    </div>
  </article>
}

function providerPriority(provider: ProviderView): number {
  if (provider.provider_id === "ollama") return 0
  return provider.verification.status === "passed" ? 1 : provider.verification.status === "never" ? 2 : 3
}

function verificationLabel(status: ProviderView["verification"]["status"]): string {
  return status === "passed" ? "验证通过" : status === "failed" ? "验证失败" : "未验证"
}

function connectionLabel(provider: ProviderView): string {
  const method = provider.capabilities.connection_method
  if (method === "local") return "本地服务"
  if (method === "oauth") return provider.capabilities.oauth_available ? "登录授权" : "登录授权尚未接入"
  return "API Key"
}
