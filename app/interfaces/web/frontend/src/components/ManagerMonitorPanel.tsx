import { useEffect, useState } from "react"
import { z } from "zod"

import { ApiError, ownerRead } from "../api/client"
import { Notice } from "./Notice"

const RuntimeStatusSchema = z.object({
  status: z.string(),
  providers: z.object({ total: z.number(), active: z.number(), inactive: z.number() }),
  models: z.object({ total: z.number(), visible: z.number(), hidden: z.number() }),
  fallback: z.object({ provider: z.string(), configured: z.boolean() }),
  observer: z.object({ event_count: z.number(), last_event: z.string().nullable() }),
  notes: z.array(z.string()),
})

type ManagerMonitorPanelProps = { readonly elfieCount: number }

export function ManagerMonitorPanel({ elfieCount }: ManagerMonitorPanelProps) {
  const [status, setStatus] = useState<z.infer<typeof RuntimeStatusSchema> | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = async (): Promise<void> => {
    try {
      setStatus(RuntimeStatusSchema.parse(await ownerRead("/api/owner/runtime/status")))
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "运行状态加载失败")
    }
  }

  useEffect(() => { void load() }, [])
  const health = status?.status === "ok" ? "正常" : "待检查"
  return <section className="monitor-panel">
    <div className="manage-head"><div><h2>综合监控</h2><p>本机服务、模型、精灵巢连接与最近运行事件的可读摘要。</p></div><button className="button button--quiet" onClick={() => { void load() }} type="button">刷新状态</button></div>
    {error && <Notice kind="error" message={error} />}
    <div className="monitor-metrics">
      <Metric label="系统健康" value={health} detail={status?.fallback.configured ? `默认回退：${status.fallback.provider}` : "默认回退尚未配置"} state={status?.status === "ok" ? "good" : "warning"} />
      <Metric label="已登记精灵" value={String(elfieCount)} detail="当前管理范围内的精灵" state="neutral" />
      <Metric label="可用供应商" value={status ? `${status.providers.active}/${status.providers.total}` : "—"} detail={status ? `${status.providers.inactive} 个待配置或离线` : "正在读取"} state={status?.providers.active ? "good" : "warning"} />
      <Metric label="可见模型" value={status ? String(status.models.visible) : "—"} detail={status ? `目录共 ${status.models.total} 个模型` : "正在读取"} state="neutral" />
    </div>
    <div className="monitor-layout">
      <section className="monitor-module"><h3>模型服务</h3><p>按连接结果，而不是密钥文本展示。</p><dl><div><dt>已启用</dt><dd>{status?.providers.active ?? "—"}</dd></div><div><dt>待配置 / 离线</dt><dd>{status?.providers.inactive ?? "—"}</dd></div><div><dt>运行事件</dt><dd>{status?.observer.event_count ?? "—"}</dd></div></dl></section>
      <section className="monitor-module"><h3>系统提醒</h3>{status === null ? <p className="empty">正在读取运行状态…</p> : <ul className="monitor-notices">{status.notes.length === 0 ? <li>各项指标平稳，暂无额外提醒。</li> : status.notes.map((note) => <li key={note}>{note}</li>)}</ul>}<p className="monitor-last-event">最近事件：{status?.observer.last_event ?? "暂无"}</p></section>
    </div>
  </section>
}

function Metric({ detail, label, state, value }: { readonly detail: string; readonly label: string; readonly state: "good" | "neutral" | "warning"; readonly value: string }) {
  return <article className={`monitor-metric monitor-metric--${state}`}><p>{label}</p><strong>{value}</strong><small>{detail}</small></article>
}
