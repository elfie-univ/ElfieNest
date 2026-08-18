import { useCallback, useEffect, useRef, useState } from "react"
import type { TFunction } from "i18next"
import { useTranslation } from "react-i18next"

import {
  loadMonitorSnapshot,
  MONITOR_SOURCE_KEYS,
  type MonitorHealth,
  type MonitorElfie,
  type MonitorFood,
  type MonitorOllama,
  type MonitorProvider,
  type MonitorSnapshot,
} from "../api/owner-monitor"
import { compareLocalizedText, currentLocale } from "../i18n/format"
import { PersistentStatus } from "./PersistentStatus"
import { RefreshButton } from "./RefreshButton"
import { useToast } from "./ui/toast"

type MetricState = "good" | "neutral" | "warning" | "error"
type HealthLevel = "ok" | "attention" | "error" | "unknown"
type ServiceStatus = "healthy" | "attention" | "unavailable" | "unverified" | "disabled" | "unknown"
type AiServiceState = "healthy" | "attention" | "unavailable" | "unconfigured" | "configuredNoFood" | "unknown"
type InterstellarState = "enabled" | "unavailable" | "unknown"
const SYSTEM_SERVICE_IDS = ["core", "godotWeb", "godotRuntime"] as const
type SystemServiceId = (typeof SYSTEM_SERVICE_IDS)[number]
type SystemServiceStatus = { readonly id: SystemServiceId; readonly healthy: boolean }
type MonitorIssue =
  | { readonly kind: "system"; readonly services: readonly SystemServiceId[] }
  | { readonly kind: "runtime" }
  | { readonly kind: "no-services" }
  | { readonly kind: "provider"; readonly name: string; readonly status: "failed" | "attention" | "unverified" }
  | { readonly kind: "ollama" }
  | { readonly kind: "beds"; readonly count: number }

export function ManageMonitorPanel() {
  const { t, i18n } = useTranslation("manage")
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
  const systemIssues = filterSystemIssues(operationalIssues)
  const health = resolveHealth(snapshot, systemIssues)
  const modelSummary = summarizeModels(snapshot)
  const aiService = summarizeAiService(snapshot, modelSummary)
  const aiCardState = aiService === null ? null : aiServiceDisplayState(aiService, snapshot)
  const unassignedCount = countUnassignedElfies(snapshot)
  const authRequired = snapshot?.authRequired === true
  const allSourcesFailed = !authRequired && snapshot?.failedSources.length === MONITOR_SOURCE_KEYS.length
  const partiallyLoaded = !authRequired && snapshot !== null && snapshot.failedSources.length > 0 && !allSourcesFailed
  const issueAttention = !authRequired && !allSourcesFailed && !partiallyLoaded && snapshot !== null && systemIssues.length > 0

  return <section className="manage-card manage-card--wide monitor-panel">
    <div className="manage-head"><RefreshButton disabled={loading} label={t("runtimeMonitor.refresh")} onClick={() => { void load() }} /></div>
    {authRequired && <PersistentStatus kind="error" message={t("runtimeMonitor.authRequired")} />}
    {allSourcesFailed && <PersistentStatus kind="error" message={t("runtimeMonitor.allLoadFailed")} />}
    {partiallyLoaded && <PersistentStatus kind="warning" message={t("runtimeMonitor.partialLoad")} />}
    {issueAttention && <PersistentStatus kind="warning" message={t("runtimeMonitor.health.pending")} />}
    <div className="monitor-metrics">
      <Metric label={t("runtimeMonitor.cards.health")} value={t(`runtimeMonitor.health.${health}`)} detail={healthDetail(health, systemIssues, snapshot, t)} state={healthMetricState(health)} />
      <Metric label={t("runtimeMonitor.cards.aiService")} value={aiCardState === null ? "—" : t(`runtimeMonitor.aiService.${aiCardState}`)} detail={aiService === null ? t("runtimeMonitor.cards.reading") : aiServiceCardDetail(aiService, snapshot, t)} state={aiCardState === null ? "neutral" : aiServiceMetricState(aiCardState)} />
      <Metric label={t("runtimeMonitor.cards.users")} value={snapshot?.users === null || snapshot === null ? "—" : String(snapshot.users.length)} detail={snapshot?.users === null || snapshot === null ? t("runtimeMonitor.cards.reading") : t("runtimeMonitor.cards.usersDetail", { count: onlineUsers(snapshot.users) })} state="neutral" />
      <Metric label={t("runtimeMonitor.cards.elfies")} value={snapshot?.elfies === null || snapshot === null ? "—" : String(snapshot.elfies.length)} detail={snapshot?.elfies === null || snapshot === null ? t("runtimeMonitor.cards.reading") : t("runtimeMonitor.cards.elfiesDetail", { online: onlineElfies(snapshot.elfies), unassigned: unassignedCount ?? "—" })} state="neutral" />
    </div>
    <div className="monitor-layout">
      <section className="monitor-module">
        <h3>{t("runtimeMonitor.modules.events")}</h3>
        <p className="monitor-module__subheading">{t("runtimeMonitor.events.pendingTitle")}</p>
        <ul className="monitor-notices">
          {loading ? <li>{t("runtimeMonitor.readingStatus")}</li> : snapshot?.runtime === null || snapshot === null ? <li>{t("runtimeMonitor.moduleUnavailable")}</li> : issues.length === 0 && snapshot.runtime.observer.last_event === null ? <li>{t("runtimeMonitor.events.empty")}</li> : issues.slice(0, 4).map((issue) => <li key={issueKey(issue)}>{issueText(issue, t)}</li>)}
          {snapshot?.runtime?.observer.last_event && <li className="monitor-notices__event"><span>{t("runtimeMonitor.events.recentTitle")}</span>{t("runtimeMonitor.events.latest", { subject: snapshot.runtime.observer.last_event.subject })}</li>}
        </ul>
      </section>
      <section className="monitor-module">
        <h3>{t("runtimeMonitor.modules.services")}</h3>
        {snapshot?.providers === null || snapshot === null ? <p className="empty">{t("runtimeMonitor.moduleUnavailable")}</p> : <ul className="monitor-service-list">
          {operationalProviders(snapshot.providers).map((provider) => <ServiceRow key={`${provider.catalog_id}-${provider.alias}`} provider={provider} ollama={snapshot.ollama} t={t} />)}
          {!operationalProviders(snapshot.providers).some((provider) => provider.catalog_id !== "ollama") ? <RemoteModelsUnavailableRow t={t} /> : null}
        </ul>}
        <FoodStatusGrid foods={snapshot?.foods ?? null} locale={currentLocale(i18n)} t={t} />
        <InterstellarStatus snapshot={snapshot} t={t} />
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

type UnifiedModelCounts = {
  readonly total: number
  readonly enabled: number
  readonly in_use: number
  readonly available: number
  readonly degraded: number
  readonly pending: number
  readonly unavailable: number
}

type ModelSummary = {
  readonly configured: number
  readonly configuredProviders: number
  readonly healthy: number
  readonly availableModels: number
  readonly inUseModels: number
  readonly degradedModels: number
  readonly pendingModels: number
  readonly unavailableModels: number
}

function summarizeModels(snapshot: MonitorSnapshot | null): ModelSummary | null {
  if (snapshot?.providers === null || snapshot === null) return null
  const relevant = operationalProviders(snapshot.providers)
  const healthy = relevant.filter((provider) => serviceStatus(provider, snapshot.ollama) === "healthy").length
  const counts = relevant.map((provider) => modelCountsForProvider(provider, snapshot.ollama))
  return {
    configured: counts.reduce((total, value) => total + value.enabled, 0),
    configuredProviders: relevant.length,
    healthy,
    availableModels: counts.reduce((total, value) => total + value.available, 0),
    inUseModels: counts.reduce((total, value) => total + value.in_use, 0),
    degradedModels: counts.reduce((total, value) => total + value.degraded, 0),
    pendingModels: counts.reduce((total, value) => total + value.pending, 0),
    unavailableModels: counts.reduce((total, value) => total + value.unavailable, 0),
  }
}

type FoodState = "healthy" | "degraded" | "unavailable" | "unconfigured" | "unknown"

type AiServiceSummary = {
  readonly state: AiServiceState
  readonly common: FoodState
  readonly emergency: FoodState
  readonly enabledFoods: number
  readonly pendingFoods: number
  readonly configuredProviders: number
  readonly healthyProviders: number
  readonly availableModels: number
  readonly inUseModels: number
  readonly pendingModels: number
  readonly degradedModels: number
  readonly unavailableModels: number
}

function summarizeAiService(snapshot: MonitorSnapshot | null, modelSummary: ReturnType<typeof summarizeModels>): AiServiceSummary | null {
  if (snapshot === null) return null
  const foods = summarizeFoods(snapshot.foods)
  const runtimeState = snapshot.runtime?.lifecycle?.model_state
  const state = resolveAiServiceState(modelSummary, foods, runtimeState)
  return {
    state,
    common: foods.common,
    emergency: foods.emergency,
    enabledFoods: foods.enabledFoods,
    pendingFoods: foods.pendingFoods,
    configuredProviders: modelSummary?.configuredProviders ?? 0,
    healthyProviders: modelSummary?.healthy ?? 0,
    availableModels: modelSummary?.availableModels ?? 0,
    inUseModels: modelSummary?.inUseModels ?? 0,
    pendingModels: modelSummary?.pendingModels ?? 0,
    degradedModels: modelSummary?.degradedModels ?? 0,
    unavailableModels: modelSummary?.unavailableModels ?? 0,
  }
}

type FoodSummary = { readonly loaded: boolean; readonly common: FoodState; readonly emergency: FoodState; readonly enabledFoods: number; readonly pendingFoods: number }

function summarizeFoods(foods: readonly MonitorFood[] | null): FoodSummary {
  if (foods === null) return { loaded: false, common: "unknown", emergency: "unknown", enabledFoods: 0, pendingFoods: 0 }
  const enabled = foods.filter((food) => food.enabled && !food.archived)
  return {
    loaded: true,
    common: foodState(foods.find((food) => food.system_role === "common")),
    emergency: foodState(foods.find((food) => food.system_role === "emergency")),
    enabledFoods: enabled.length,
    pendingFoods: enabled.filter((food) => food.latest_evidence_at === null || ["unconfigured", "unknown", "never_verified", "stale"].includes(food.health)).length,
  }
}

function resolveAiServiceState(modelSummary: ModelSummary | null, foods: FoodSummary, runtimeState: string | undefined): AiServiceState {
  if (modelSummary === null) return "unknown"
  if (modelSummary.configured === 0) return "unconfigured"
  if (foods.loaded && foods.enabledFoods === 0) return "configuredNoFood"
  if (runtimeState === "unavailable") return "unavailable"
  if (runtimeState === "degraded") return "attention"
  if (foods.loaded && [foods.common, foods.emergency].some((state) => state === "unavailable")) return "unavailable"
  if (modelSummary.availableModels === 0 && modelSummary.pendingModels === 0 && modelSummary.unavailableModels > 0) return "unavailable"
  if (foods.loaded && [foods.common, foods.emergency].some((state) => state !== "healthy")) return "attention"
  if (modelSummary.pendingModels > 0 || modelSummary.degradedModels > 0 || modelSummary.unavailableModels > 0) return "attention"
  if (runtimeState === "ready") return "healthy"
  if (modelSummary.healthy === 0) return "attention"
  return "healthy"
}

function foodState(food: MonitorFood | undefined): FoodState {
  if (food === undefined || food.archived || !food.enabled) return "unconfigured"
  if (food.health === "healthy") return "healthy"
  if (food.health === "degraded") return "degraded"
  if (food.health === "unavailable") return "unavailable"
  return "unknown"
}

function aiServiceMetricState(state: AiServiceState): MetricState {
  if (state === "healthy") return "good"
  if (state === "unavailable") return "error"
  if (state === "attention" || state === "configuredNoFood") return "warning"
  return "neutral"
}

function aiServiceDetail(summary: AiServiceSummary, t: TFunction<"manage">): string {
  if (summary.state === "healthy") {
    return t("runtimeMonitor.cards.aiServiceHealthyDetail", {
      subscriptions: summary.configuredProviders,
      models: summary.availableModels,
      foods: summary.enabledFoods,
      inUse: summary.inUseModels,
    })
  }
  const issues: string[] = []
  if (summary.common !== "healthy") {
    issues.push(t("runtimeMonitor.cards.aiServiceIssueCommon", { state: foodStateLabel(summary.common, t) }))
  }
  if (summary.emergency !== "healthy") {
    issues.push(t("runtimeMonitor.cards.aiServiceIssueEmergency", { state: foodStateLabel(summary.emergency, t) }))
  }
  if (summary.configuredProviders > 0 && summary.healthyProviders < summary.configuredProviders) {
    issues.push(t("runtimeMonitor.cards.aiServiceIssueProviders", { healthy: summary.healthyProviders, total: summary.configuredProviders }))
  }
  if (summary.pendingModels > 0) {
    issues.push(t("runtimeMonitor.cards.aiServiceIssuePendingModels", { count: summary.pendingModels }))
  }
  if (summary.unavailableModels > 0) {
    issues.push(t("runtimeMonitor.cards.aiServiceIssueUnavailableModels", { count: summary.unavailableModels }))
  }
  if (summary.enabledFoods === 0) {
    issues.push(t("runtimeMonitor.cards.aiServiceIssueNoFoods"))
  } else if (summary.pendingFoods > 0) {
    issues.push(t("runtimeMonitor.cards.aiServiceIssuePendingFoods", { count: summary.pendingFoods }))
  }
  return t("runtimeMonitor.cards.aiServiceDetail", { issues: issues[0] || t(`runtimeMonitor.aiService.${summary.state}`) })
}

function aiServiceCardDetail(summary: AiServiceSummary, snapshot: MonitorSnapshot | null, t: TFunction<"manage">): string {
  if (summary.state === "unknown") return t("runtimeMonitor.cards.reading")
  if (!hasRemoteSubscription(snapshot)) return t("runtimeMonitor.blockers.noRemoteSubscription")
  return aiServiceDetail(summary, t)
}

function aiServiceDisplayState(summary: AiServiceSummary, snapshot: MonitorSnapshot | null): AiServiceState {
  if (summary.state === "unknown") return "unknown"
  return hasRemoteSubscription(snapshot) ? summary.state : "attention"
}

function hasRemoteSubscription(snapshot: MonitorSnapshot | null): boolean {
  return snapshot?.providers?.some((provider) => provider.enabled && !provider.archived && provider.catalog_id !== "ollama") === true
}

function foodStateLabel(state: FoodState, t: TFunction<"manage">): string {
  return t(`runtimeMonitor.foodStates.${state}`)
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
  if (provider.catalog_id === "ollama") {
    if (ollama === null) return "unknown"
    const counts = modelCountsForProvider(provider, ollama)
    if (["absent", "deleted", "failed", "repair_required"].includes(ollama.state)) return "unavailable"
    if (ollama.state !== "healthy" || counts.enabled === 0) return "attention"
    if (counts.available === counts.enabled) return "healthy"
    if (counts.available === 0 && counts.unavailable === counts.enabled) return "unavailable"
    return "attention"
  }
  const counts = provider.model_counts
  if (provider.verification.status === "failed" || provider.verification.availability_status === "unavailable") return "unavailable"
  if (counts.enabled === 0) return "unverified"
  if (counts.available === counts.enabled) return "healthy"
  if (counts.available === 0 && counts.unavailable === counts.enabled) return "unavailable"
  if (counts.pending > 0 || counts.degraded > 0 || counts.unavailable > 0) return "attention"
  return provider.verification.status === "never" ? "unverified" : "unknown"
}

function buildIssues(snapshot: MonitorSnapshot): readonly MonitorIssue[] {
  const issues: MonitorIssue[] = []
  const unhealthySystemServices = snapshot.health === null ? [] : getSystemServiceStatuses(snapshot.health).filter((service) => !service.healthy).map((service) => service.id)
  if (unhealthySystemServices.length > 0) issues.push({ kind: "system", services: unhealthySystemServices })
  if (snapshot.runtime !== null && snapshot.runtime.status !== "ok") issues.push({ kind: "runtime" })
  const providers = snapshot.providers ? operationalProviders(snapshot.providers) : []
  if (snapshot.providers !== null && providers.length === 0) issues.push({ kind: "no-services" })
  const lifecycle = snapshot.runtime?.lifecycle
  if (lifecycle !== undefined && (lifecycle.failures.length > 0 || lifecycle.tier === "offline")) {
    issues.push({ kind: "runtime" })
  }
  for (const provider of providers) {
    const status = serviceStatus(provider, snapshot.ollama)
    if (status === "attention" || status === "unavailable") {
      if (provider.catalog_id === "ollama") issues.push({ kind: "ollama" })
      else issues.push({ kind: "provider", name: provider.alias, status: status === "attention" ? "attention" : "failed" })
    }
    if (status === "unverified") issues.push({ kind: "provider", name: provider.alias, status: "unverified" })
  }
  const unassigned = countUnassignedElfies(snapshot)
  if (unassigned !== null && unassigned > 0) issues.push({ kind: "beds", count: unassigned })
  return issues
}

function filterOperationalIssues(issues: readonly MonitorIssue[]): readonly MonitorIssue[] {
  return issues.filter((issue) => issue.kind !== "beds" && issue.kind !== "no-services")
}

function filterSystemIssues(issues: readonly MonitorIssue[]): readonly MonitorIssue[] {
  return issues.filter((issue) => issue.kind === "system" || issue.kind === "runtime")
}

function resolveHealth(snapshot: MonitorSnapshot | null, issues: readonly MonitorIssue[]): HealthLevel {
  if (snapshot === null || snapshot.health === null) return "unknown"
  if (issues.some((issue) => issue.kind === "system")) return "error"
  if (snapshot.runtime?.lifecycle?.tier === "offline") return "error"
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
    case "provider": return t(issue.status === "failed" ? "runtimeMonitor.events.providerFailed" : issue.status === "attention" ? "runtimeMonitor.events.providerAttention" : "runtimeMonitor.events.providerUnverified", { name: issue.name })
    case "ollama": return t("runtimeMonitor.events.ollama")
    case "beds": return t("runtimeMonitor.events.beds", { count: issue.count })
  }
}

function ServiceRow({ ollama, provider, t }: { readonly ollama: MonitorOllama | null; readonly provider: MonitorProvider; readonly t: TFunction<"manage"> }) {
  const status = serviceStatus(provider, ollama)
  const counts = modelCountsForProvider(provider, ollama)
  return <li className={`monitor-service monitor-service--${status}`}>
    <div className="monitor-service__heading"><strong>{provider.alias}</strong><span>{t("runtimeMonitor.services.modelStats", { available: counts.available, total: counts.enabled })}</span></div>
    {status === "healthy" ? null : <small>{t(`runtimeMonitor.services.status.${status}`)}</small>}
  </li>
}

function RemoteModelsUnavailableRow({ t }: { readonly t: TFunction<"manage"> }) {
  return <li className="monitor-service monitor-service--unavailable">
    <div className="monitor-service__heading"><strong>{t("runtimeMonitor.services.remoteModels")}</strong><span className="monitor-service__status">{t("runtimeMonitor.services.status.unavailable")}{t("runtimeMonitor.services.configureSeparator")}<a className="monitor-service__configure" href="/manage?section=providers" onClick={(event) => { event.preventDefault(); window.location.assign("/manage?section=providers") }}>{t("runtimeMonitor.services.configureSubscription")}</a></span></div>
  </li>
}

function FoodStatusGrid({ foods, locale, t }: { readonly foods: readonly MonitorFood[] | null; readonly locale: ReturnType<typeof currentLocale>; readonly t: TFunction<"manage"> }) {
  const visible = visibleMonitorFoods(foods, locale)
  return <section aria-label={t("runtimeMonitor.foods.title")} className="monitor-food-status">
    <h4>{t("runtimeMonitor.foods.title")}</h4>
    {foods === null ? <p className="empty">{t("runtimeMonitor.moduleUnavailable")}</p> : visible.length === 0 ? <p className="empty">{t("runtimeMonitor.foods.empty")}</p> : <div className="monitor-food-grid">
      {visible.map((food) => {
        const state = foodState(food)
        return <article className={`monitor-food monitor-food--${state}`} key={food.key}><strong>{food.display_name}</strong><span>{food.enabled ? foodStateLabel(state, t) : t("runtimeMonitor.foods.disabled")}</span></article>
      })}
    </div>}
  </section>
}

function InterstellarStatus({ snapshot, t }: { readonly snapshot: MonitorSnapshot | null; readonly t: TFunction<"manage"> }) {
  const state = resolveInterstellarState(snapshot)
  return <section aria-label={t("runtimeMonitor.interstellar.title")} className="monitor-interstellar-status">
    <h4>{t("runtimeMonitor.interstellar.title")}</h4>
    {state === "unknown" ? <p className="empty">{t("runtimeMonitor.interstellar.reading")}</p> : <article className={`monitor-interstellar monitor-interstellar--${state}`}>
      <strong>{t(`runtimeMonitor.interstellar.status.${state}`)}</strong>
      {state === "unavailable" ? <small>{t("runtimeMonitor.interstellar.unavailableDetail")}</small> : null}
    </article>}
  </section>
}

function resolveInterstellarState(snapshot: MonitorSnapshot | null): InterstellarState {
  if (snapshot === null || snapshot.runtime === null || snapshot.providers === null || snapshot.foods === null) return "unknown"
  const common = snapshot.foods.find((food) => food.system_role === "common")
  if (common === undefined || common.archived || !common.enabled || common.roles.primary === null || common.locality === "local") return "unavailable"
  const commonState = snapshot.runtime.lifecycle?.model_common_state
  if (commonState === "unconfigured" || commonState === "unavailable") return "unavailable"
  const remoteModelAvailable = operationalProviders(snapshot.providers).some((provider) => provider.catalog_id !== "ollama" && provider.model_counts.available > 0)
  return remoteModelAvailable && (commonState === undefined || commonState === "ready" || commonState === "degraded") ? "enabled" : "unavailable"
}

function visibleMonitorFoods(foods: readonly MonitorFood[] | null, locale: ReturnType<typeof currentLocale>): readonly MonitorFood[] {
  if (foods === null) return []
  const rank = (food: MonitorFood): number => food.system_role === "common" ? 0 : food.system_role === "emergency" ? 1 : 2
  return foods
    .filter((food) => !food.archived && (food.enabled || food.system_role !== null))
    .sort((left, right) => rank(left) - rank(right) || compareLocalizedText(left.display_name, right.display_name, locale))
}

function operationalProviders(providers: readonly MonitorProvider[]): readonly MonitorProvider[] {
  return providers
    .filter((provider) => provider.enabled && !provider.archived)
    .sort((left, right) => Number(right.catalog_id === "ollama") - Number(left.catalog_id === "ollama"))
}

function modelCountsForProvider(provider: MonitorProvider, ollama: MonitorOllama | null): UnifiedModelCounts {
  if (provider.catalog_id === "ollama" && ollama !== null) {
    const counts = ollama.supported_model_counts ?? ollama.model_counts
    return {
      total: counts.installed,
      enabled: counts.installed,
      in_use: 0,
      available: counts.available,
      degraded: counts.degraded,
      pending: counts.pending,
      unavailable: counts.unavailable,
    }
  }
  return provider.model_counts
}

function Metric({ detail, label, state, value }: { readonly detail: string; readonly label: string; readonly state: MetricState; readonly value: string }) {
  return <article className={`monitor-metric monitor-metric--${state}`}><p>{label}</p><strong>{value}</strong><small>{detail}</small></article>
}
