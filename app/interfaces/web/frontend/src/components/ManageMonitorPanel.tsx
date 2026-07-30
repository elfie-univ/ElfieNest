import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { z } from "zod"

import { ownerRead } from "../api/client"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { Notice } from "./Notice"
import { RefreshButton } from "./RefreshButton"

const RuntimeStatusSchema = z.object({
  status: z.string(),
  providers: z.object({ total: z.number(), active: z.number(), inactive: z.number() }),
  models: z.object({ total: z.number(), visible: z.number(), hidden: z.number() }),
  fallback: z.object({ provider: z.string(), configured: z.boolean() }),
  observer: z.object({ event_count: z.number(), last_event: z.string().nullable() }),
  notes: z.array(z.string()),
})

type ManageMonitorPanelProps = { readonly elfieCount: number }

export function ManageMonitorPanel({ elfieCount }: ManageMonitorPanelProps) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [status, setStatus] = useState<z.infer<typeof RuntimeStatusSchema> | null>(null)
  const [error, setError] = useState<LocalizedErrorState>(null)

  const load = useCallback(async (): Promise<void> => {
    try {
      setStatus(RuntimeStatusSchema.parse(await ownerRead("/api/owner/runtime/status")))
      setError(null)
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.load"))
    }
  }, [])

  useEffect(() => { void load() }, [load])
  const health = status?.status === "ok" ? t("runtimeMonitor.health.ok") : t("runtimeMonitor.health.attention")
  return <section className="monitor-panel">
    <div className="manage-head"><div><h2>{t("runtimeMonitor.title")}</h2><p>{t("runtimeMonitor.description")}</p></div><RefreshButton label={t("runtimeMonitor.refresh")} onClick={() => { void load() }} /></div>
    {error && <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.load")} />}
    <div className="monitor-metrics">
      <Metric label={t("runtimeMonitor.labels.health")} value={health} detail={status?.fallback.configured ? t("runtimeMonitor.fallback.configured", { provider: status.fallback.provider }) : t("runtimeMonitor.fallback.missing")} state={status?.status === "ok" ? "good" : "warning"} />
      <Metric label={t("runtimeMonitor.labels.elfies")} value={String(elfieCount)} detail={t("runtimeMonitor.labels.elfiesDetail")} state="neutral" />
      <Metric label={t("runtimeMonitor.labels.providers")} value={status ? `${status.providers.active}/${status.providers.total}` : "—"} detail={status ? `${status.providers.inactive} ${t("runtimeMonitor.labels.fallbackProviders")}` : t("runtimeMonitor.labels.reading")} state={status?.providers.active ? "good" : "warning"} />
      <Metric label={t("runtimeMonitor.labels.models")} value={status ? String(status.models.visible) : "—"} detail={status ? t("runtimeMonitor.labels.modelsDetail", { count: status.models.total }) : t("runtimeMonitor.labels.reading")} state="neutral" />
    </div>
    <div className="monitor-layout">
      <section className="monitor-module"><h3>{t("runtimeMonitor.modules.models")}</h3><p>{t("runtimeMonitor.modules.modelsDescription")}</p><dl><div><dt>{t("runtimeMonitor.labels.active")}</dt><dd>{status?.providers.active ?? "—"}</dd></div><div><dt>{t("runtimeMonitor.labels.fallbackProviders")}</dt><dd>{status?.providers.inactive ?? "—"}</dd></div><div><dt>{t("runtimeMonitor.labels.runtimeEvents")}</dt><dd>{status?.observer.event_count ?? "—"}</dd></div></dl></section>
      <section className="monitor-module"><h3>{t("runtimeMonitor.modules.alerts")}</h3>{status === null ? <p className="empty">{t("runtimeMonitor.readingStatus")}</p> : <ul className="monitor-notices">{status.notes.length === 0 || locale === "en-US" ? <li>{t("runtimeMonitor.noAlerts")}</li> : status.notes.map((note) => <li key={note}>{note}</li>)}</ul>}<p className="monitor-last-event">{t("runtimeMonitor.labels.lastEvent", { event: status?.observer.last_event ?? t("runtimeMonitor.labels.noEvent") })}</p></section>
    </div>
  </section>
}

function Metric({ detail, label, state, value }: { readonly detail: string; readonly label: string; readonly state: "good" | "neutral" | "warning"; readonly value: string }) {
  return <article className={`monitor-metric monitor-metric--${state}`}><p>{label}</p><strong>{value}</strong><small>{detail}</small></article>
}
