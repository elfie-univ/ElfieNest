import { useCallback, useEffect, useRef, useState } from "react"
import type { TFunction } from "i18next"
import { useTranslation } from "react-i18next"

import {
  loadMonitorSnapshot,
  MONITOR_SOURCE_KEYS,
  type MonitorHealth,
  type MonitorElfie,
  type MonitorOllama,
  type MonitorProvider,
  type MonitorSnapshot,
} from "../api/owner-monitor"
import { PersistentStatus } from "./PersistentStatus"
import { RefreshButton } from "./RefreshButton"
import { useToast } from "./ui/toast"

type MetricState = "good" | "neutral" | "warning" | "error"
type HealthLevel = "ok" | "attention" | "error" | "unknown"
type ServiceStatus = "healthy" | "attention" | "unverified" | "disabled" | "unknown"
const SYSTEM_SERVICE_IDS = ["core", "godotWeb", "godotRuntime"] as const
type SystemServiceId = (typeof SYSTEM_SERVICE_IDS)[number]
type SystemServiceStatus = { readonly id: SystemServiceId; readonly healthy: boolean }
type MonitorIssue =
  | { readonly kind: "system"; readonly services: readonly SystemServiceId[] }
  | { readonly kind: "runtime" }
  | { readonly kind: "no-services" }
  | { readonly kind: "provider"; readonly name: string; readonly status: "failed" | "unverified" }
  | { readonly kind: "ollama" }
  | { readonly kind: "beds"; readonly count: number }

export function ManageMonitorPanel() {
  const { t } = useTranslation("manage")
  const [snapshot, setSnapshot] = useState<MonitorSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const wasAttention = useRef(false)
  const { show } = useToast()

  const load = useCallback(async (): Promise<void> => {
    setLoading(true)
    const nextSnapshot = await loadMonitorSnapshot()
    const nextIssues = buildIssues(nextSnapshot)
    const nextOperationalIssues = filterOperationalIssues(nextIssues)
    const nextRequiresAttention = nextSnapshot.authRequired || nextSnapshot.failedSources.length > 0 || nextOperationalIssues.length > 0
    const recovered = wasAttention.current && !nextRequiresAttention
    setSnapshot(nextSnapshot)
    setLoading(false)
    wasAttention.current = nextRequiresAttention
    if (recovered) show({ dedupeKey: "runtime-status-recovered", kind: "success", message: t("runtimeMonitor.notices.recovered") })
  }, [show, t])

  useEffect(() => { void load() }, [load])

  const issues = snapshot === null ? [] : buildIssues(snapshot)
  const operationalIssues = filterOperationalIssues(issues)
  const health = resolveHealth(snapshot, operationalIssues)
  const modelSummary = summarizeModels(snapshot)
  const unassignedCount = countUnassignedElfies(snapshot)
  const authRequired = snapshot?.authRequired === true
  const allSourcesFailed = !authRequired && snapshot?.failedSources.length === MONITOR_SOURCE_KEYS.length
  const partiallyLoaded = !authRequired && snapshot !== null && snapshot.failedSources.length > 0 && !allSourcesFailed
  const issueAttention = !authRequired && !allSourcesFailed && !partiallyLoaded && snapshot !== null && operationalIssues.length > 0

  return <section className="manage-card manage-card--wide monitor-panel">
    <div className="manage-head"><RefreshButton disabled={loading} label={t("runtimeMonitor.refresh")} onClick={() => { void load() }} /></div>
    {authRequired && <PersistentStatus kind="error" message={t("runtimeMonitor.authRequired")} />}
    {allSourcesFailed && <PersistentStatus kind="error" message={t("runtimeMonitor.allLoadFailed")} />}
    {partiallyLoaded && <PersistentStatus kind="warning" message={t("runtimeMonitor.partialLoad")} />}
    {issueAttention && <PersistentStatus kind="warning" message={t("runtimeMonitor.health.pending")} />}
    <div className="monitor-metrics">
      <Metric label={t("runtimeMonitor.cards.health")} value={t(`runtimeMonitor.health.${health}`)} detail={healthDetail(health, operationalIssues, snapshot, t)} state={healthMetricState(health)} />
      <Metric label={t("runtimeMonitor.cards.users")} value={snapshot?.users === null || snapshot === null ? "—" : String(snapshot.users.length)} detail={snapshot?.users === null || snapshot === null ? t("runtimeMonitor.cards.reading") : t("runtimeMonitor.cards.usersDetail", { count: onlineUsers(snapshot.users) })} state="neutral" />
      <Metric label={t("runtimeMonitor.cards.elfies")} value={snapshot?.elfies === null || snapshot === null ? "—" : String(snapshot.elfies.length)} detail={snapshot?.elfies === null || snapshot === null ? t("runtimeMonitor.cards.reading") : t("runtimeMonitor.cards.elfiesDetail", { online: onlineElfies(snapshot.elfies), unassigned: unassignedCount ?? "—" })} state="neutral" />
      <Metric label={t("runtimeMonitor.cards.services")} value={modelSummary === null ? "—" : `${modelSummary.healthy}/${modelSummary.configured}`} detail={modelSummary === null ? t("runtimeMonitor.cards.reading") : t("runtimeMonitor.cards.servicesDetail", { count: modelSummary.availableModels, local: localServiceText(snapshot?.ollama ?? null, t) })} state={modelSummary === null ? "neutral" : modelSummary.healthy === modelSummary.configured ? "good" : "warning"} />
    </div>
    <div className="monitor-layout">
      <section className="monitor-module">
        <h3>{t("runtimeMonitor.modules.services")}</h3>
        {snapshot?.providers === null || snapshot === null ? <p className="empty">{t("runtimeMonitor.moduleUnavailable")}</p> : snapshot.providers.filter((provider) => !provider.archived).length === 0 ? <p className="empty">{t("runtimeMonitor.services.empty")}</p> : <ul className="monitor-service-list">{snapshot.providers.filter((provider) => !provider.archived).map((provider) => <ServiceRow key={`${provider.catalog_id}-${provider.alias}`} provider={provider} ollama={snapshot.ollama} t={t} />)}</ul>}
      </section>
      <section className="monitor-module">
        <h3>{t("runtimeMonitor.modules.events")}</h3>
        <p className="monitor-module__subheading">{t("runtimeMonitor.events.pendingTitle")}</p>
        <ul className="monitor-notices">
          {loading ? <li>{t("runtimeMonitor.readingStatus")}</li> : snapshot?.runtime === null || snapshot === null ? <li>{t("runtimeMonitor.moduleUnavailable")}</li> : issues.length === 0 && snapshot.runtime.observer.last_event === null ? <li>{t("runtimeMonitor.events.empty")}</li> : issues.slice(0, 4).map((issue) => <li key={issueKey(issue)}>{issueText(issue, t)}</li>)}
          {snapshot?.runtime?.observer.last_event && <li className="monitor-notices__event"><span>{t("runtimeMonitor.events.recentTitle")}</span>{t("runtimeMonitor.events.latest", { subject: snapshot.runtime.observer.last_event.subject })}</li>}
        </ul>
      </section>
    </div>
  </section>
}

function onlineUsers(users: readonly { readonly presence: string }[]): number {
  return users.filter((user) => user.presence === "online").length
}

function onlineElfies(elfies: readonly MonitorElfie[]): number {
  return elfies.filter((elfie) => elfie.profile.online_status === "online").length
}

function countUnassignedElfies(snapshot: MonitorSnapshot | null): number | null {
  if (snapshot === null || snapshot.elfies === null || snapshot.rooms === null) return null
  const occupiedIds = new Set(snapshot.rooms.flatMap((room) => room.beds.map((bed) => bed.occupant_id).filter((id): id is string => id !== null)))
  return snapshot.elfies.filter((elfie) => !occupiedIds.has(elfie.elfie_id)).length
}

function summarizeModels(snapshot: MonitorSnapshot | null): { readonly configured: number; readonly healthy: number; readonly availableModels: number } | null {
  if (snapshot?.providers === null || snapshot === null) return null
  const providers = snapshot.providers.filter((provider) => !provider.archived)
  const healthy = providers.filter((provider) => serviceStatus(provider, snapshot.ollama) === "healthy").length
  const availableModels = providers.filter((provider) => provider.enabled).flatMap((provider) => provider.models).filter((model) => model.available && !model.hidden && !model.retired).length
  return { configured: providers.length, healthy, availableModels }
}

function getSystemServiceStatuses(health: MonitorHealth): readonly SystemServiceStatus[] {
  return [
    { id: "core", healthy: health.status === "ok" && health.engine_ready },
    { id: "godotWeb", healthy: health.godot_web_ready },
    { id: "godotRuntime", healthy: health.godot_runtime_ready },
  ]
}

function systemServiceName(id: SystemServiceId, t: TFunction<"manage">): string {
  return t(`runtimeMonitor.health.services.${id}`)
}

function serviceStatus(provider: MonitorProvider, ollama: MonitorOllama | null): ServiceStatus {
  if (!provider.enabled) return "disabled"
  if (provider.catalog_id === "ollama") return ollama === null ? "unknown" : ollama.state === "healthy" ? "healthy" : "attention"
  switch (provider.verification.status) {
    case "passed": return "healthy"
    case "failed": return "attention"
    case "never": return "unverified"
    default: return "unknown"
  }
}

function buildIssues(snapshot: MonitorSnapshot): readonly MonitorIssue[] {
  const issues: MonitorIssue[] = []
  const unhealthySystemServices = snapshot.health === null ? [] : getSystemServiceStatuses(snapshot.health).filter((service) => !service.healthy).map((service) => service.id)
  if (unhealthySystemServices.length > 0) issues.push({ kind: "system", services: unhealthySystemServices })
  if (snapshot.runtime !== null && snapshot.runtime.status !== "ok") issues.push({ kind: "runtime" })
  const providers = snapshot.providers?.filter((provider) => !provider.archived) ?? []
  if (snapshot.providers !== null && providers.length === 0) issues.push({ kind: "no-services" })
  for (const provider of providers) {
    const status = serviceStatus(provider, snapshot.ollama)
    if (status === "attention") {
      if (provider.catalog_id === "ollama") issues.push({ kind: "ollama" })
      else issues.push({ kind: "provider", name: provider.alias, status: "failed" })
    }
    if (status === "unverified") issues.push({ kind: "provider", name: provider.alias, status: "unverified" })
  }
  const unassigned = countUnassignedElfies(snapshot)
  if (unassigned !== null && unassigned > 0) issues.push({ kind: "beds", count: unassigned })
  return issues
}

function filterOperationalIssues(issues: readonly MonitorIssue[]): readonly MonitorIssue[] {
  return issues.filter((issue) => issue.kind !== "beds")
}

function resolveHealth(snapshot: MonitorSnapshot | null, issues: readonly MonitorIssue[]): HealthLevel {
  if (snapshot === null || snapshot.health === null) return "unknown"
  if (issues.some((issue) => issue.kind === "system")) return "error"
  return issues.length === 0 ? "ok" : "attention"
}

function healthMetricState(level: HealthLevel): MetricState {
  switch (level) {
    case "ok": return "good"
    case "attention": return "warning"
    case "error": return "error"
    case "unknown": return "neutral"
  }
}

function healthDetail(level: HealthLevel, issues: readonly MonitorIssue[], snapshot: MonitorSnapshot | null, t: TFunction<"manage">): string {
  if (snapshot === null) return t("runtimeMonitor.cards.reading")
  if (level === "unknown" || snapshot.health === null) return t("runtimeMonitor.health.unknown")
  if (issues.length === 0) return t("runtimeMonitor.health.stable")
  const systemIssue = issues.find((issue): issue is Extract<MonitorIssue, { readonly kind: "system" }> => issue.kind === "system")
  if (systemIssue !== undefined) {
    const separator = t("runtimeMonitor.health.serviceSeparator")
    const services = systemIssue.services.map((service) => `${systemServiceName(service, t)}${t("runtimeMonitor.health.issueSuffix")}`).join(separator)
    return t("runtimeMonitor.health.servicesWithIssues", { services })
  }
  return t("runtimeMonitor.health.pending")
}

function localServiceText(ollama: MonitorOllama | null, t: TFunction<"manage">): string {
  if (ollama === null) return t("runtimeMonitor.services.localUnknown")
  return ollama.state === "healthy" ? t("runtimeMonitor.services.localRunning") : t("runtimeMonitor.services.localStopped")
}

function issueKey(issue: MonitorIssue): string {
  switch (issue.kind) {
    case "system": return "system"
    case "runtime": return "runtime"
    case "no-services": return "no-services"
    case "provider": return `${issue.kind}-${issue.name}`
    case "ollama": return "ollama"
    case "beds": return `beds-${issue.count}`
  }
}

function issueText(issue: MonitorIssue, t: TFunction<"manage">): string {
  switch (issue.kind) {
    case "system": return issue.services.map((service) => `${systemServiceName(service, t)}${t("runtimeMonitor.health.issueSuffix")}`).join(t("runtimeMonitor.health.serviceSeparator"))
    case "runtime": return t("runtimeMonitor.health.pending")
    case "no-services": return t("runtimeMonitor.events.noServices")
    case "provider": return t(issue.status === "failed" ? "runtimeMonitor.events.providerFailed" : "runtimeMonitor.events.providerUnverified", { name: issue.name })
    case "ollama": return t("runtimeMonitor.events.ollama")
    case "beds": return t("runtimeMonitor.events.beds", { count: issue.count })
  }
}

function ServiceRow({ ollama, provider, t }: { readonly ollama: MonitorOllama | null; readonly provider: MonitorProvider; readonly t: TFunction<"manage"> }) {
  const status = serviceStatus(provider, ollama)
  const availableModels = provider.models.filter((model) => model.available && !model.hidden && !model.retired).length
  return <li className={`monitor-service monitor-service--${status}`}><div className="monitor-service__heading"><strong>{provider.alias}</strong><span>{t(`runtimeMonitor.services.status.${status}`)}</span></div><small>{t("runtimeMonitor.services.availableModels", { count: availableModels })}</small></li>
}

function Metric({ detail, label, state, value }: { readonly detail: string; readonly label: string; readonly state: MetricState; readonly value: string }) {
  return <article className={`monitor-metric monitor-metric--${state}`}><p>{label}</p><strong>{value}</strong><small>{detail}</small></article>
}
