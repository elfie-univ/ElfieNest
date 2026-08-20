import { Button } from "@/components/ui/button"
import { useEffect, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { adminElfies } from "../api/admin/elfies"
import {
  elfieSettings,
  runtimeSettings,
  securitySettings,
  updateElfieSettings,
  updateRuntimeSettings,
  updateSecuritySettings,
  type ElfieSettings,
  type RuntimeSettings,
  type SecuritySettings,
} from "../api/admin/settings"
import { ownerRooms } from "../api/owner-nest"
import type { ToolKey } from "../api/owner-tools"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { Icon } from "./Icon"
import { Notice } from "./Notice"
import { NumberField } from "./NumberField"
import { RefreshButton } from "./RefreshButton"
import { LocalFileToolDetails } from "./tools/LocalFileToolDetails"
import { ToolSettingsRow } from "./tools/ToolSettingsRow"
import { useToolsPermissions } from "./tools/useToolsPermissions"
import { WebSearchToolDetails } from "./tools/WebSearchToolDetails"
import { useToast } from "./ui/toast"
import "./tools-permissions.css"

type SettingsSection = "quota" | "advanced"

const TOOL_META = [
  { key: "web_search", titleKey: "tools.webSearch.title" },
  { key: "local_file", titleKey: "tools.localFile.title" },
] as const

export function SystemSettingsPanel({ csrfToken }: { readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [engine, setEngine] = useState<RuntimeSettings | null>(null)
  const [adoption, setAdoption] = useState<ElfieSettings | null>(null)
  const [security, setSecurity] = useState<SecuritySettings | null>(null)
  const [capacity, setCapacity] = useState<number | null>(null)
  const [adoptedCount, setAdoptedCount] = useState<number | null>(null)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [saving, setSaving] = useState<SettingsSection | null>(null)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const { show } = useToast()

  const load = async (): Promise<void> => {
    try {
      const [loadedEngine, loadedAdoption, loadedSecurity, rooms, elfies] = await Promise.all([
        runtimeSettings(),
        elfieSettings(),
        securitySettings(),
        ownerRooms(),
        adminElfies(),
      ])
      const room = rooms[0]
      setEngine(loadedEngine)
      setAdoption(loadedAdoption)
      setSecurity(loadedSecurity)
      setCapacity(room?.desired_bed_count ?? null)
      setAdoptedCount(elfies.length)
      setError(null)
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.load"))
    }
  }
  useEffect(() => { void load() }, [])

  const saveQuota = async (): Promise<void> => {
    if (adoption === null) return
    setSaving("quota")
    try {
      await updateElfieSettings(adoption, csrfToken)
      show({ kind: "success", message: t("systemSettings.notices.quotaSaved") })
      setError(null)
      await load()
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setSaving(null)
    }
  }

  const saveAdvanced = async (): Promise<void> => {
    if (engine === null || security === null) return
    setSaving("advanced")
    try {
      await Promise.all([
        updateRuntimeSettings(engine, csrfToken),
        updateSecuritySettings(security, csrfToken),
      ])
      show({ kind: "success", message: t("systemSettings.notices.advancedSaved") })
      setError(null)
      await load()
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setSaving(null)
    }
  }

  const ready = engine !== null && adoption !== null && security !== null && adoptedCount !== null
  const remaining = capacity === null || adoptedCount === null ? null : Math.max(0, capacity - adoptedCount)

  return <section className="manage-card manage-card--wide system-settings">
    <div className="manage-head">
      <RefreshButton disabled={saving !== null} label={t("systemSettings.actions.refresh")} onClick={() => { void load() }} />
    </div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} /> : null}
    {!ready && !error ? <p className="empty-state">{t("systemSettings.loading")}</p> : null}

    {adoption && adoptedCount !== null ? <SettingsSection id="quota" title={t("systemSettings.quota.title")}>
      <div className="system-settings__panel system-quota">
        <div className="system-quota__summary">
          <QuotaStat
            action={<a className="system-quota__capacity-link" href="/manage?section=nest" onClick={(event) => {
              event.preventDefault()
              window.location.assign("/manage?section=nest")
            }} title={t("systemSettings.quota.openNestTooltip")}>{t("systemSettings.quota.openNest")}</a>}
            label={t("systemSettings.quota.capacity")}
            value={capacity === null ? t("systemSettings.quota.unknown") : t("systemSettings.quota.count", { count: capacity })}
          />
          <QuotaStat label={t("systemSettings.quota.adopted")} value={t("systemSettings.quota.count", { count: adoptedCount })} />
          <QuotaStat label={t("systemSettings.quota.remaining")} value={remaining === null ? t("systemSettings.quota.unknown") : t("systemSettings.quota.count", { count: remaining })} />
        </div>
        <div className="system-quota__form">
          <NumberField
            disabled={saving !== null}
            label={t("systemSettings.quota.defaultPerUser")}
            max={32}
            min={1}
            onChange={(limit) => setAdoption({ ...adoption, max_elfies_per_user: limit })}
            value={adoption.max_elfies_per_user}
          />
          <Button disabled={saving !== null} onClick={() => { void saveQuota() }} type="button">{t("systemSettings.actions.saveQuota")}</Button>
        </div>
      </div>
    </SettingsSection> : null}

    <SettingsSection id="capabilities" title={t("systemSettings.capabilities.title")}>
      <SystemCapabilities csrfToken={csrfToken} />
    </SettingsSection>

    {engine && security ? <section className="system-settings__panel system-advanced" aria-label={t("systemSettings.advanced.title")}>
      <button
        aria-label={t(advancedOpen ? "systemSettings.actions.collapseAdvanced" : "systemSettings.actions.expandAdvanced")}
        aria-expanded={advancedOpen}
        className="system-advanced__toggle"
        onClick={() => setAdvancedOpen((current) => !current)}
        type="button"
      >
        <Icon name="settings" size={18} />
        <span><strong>{t("systemSettings.advanced.title")}</strong><small>{t("systemSettings.advanced.description")}</small></span>
        <span className="system-advanced__toggle-label">{t(advancedOpen ? "systemSettings.actions.collapseAdvanced" : "systemSettings.actions.expandAdvanced")}</span>
        <Icon name={advancedOpen ? "chevron-up" : "chevron-down"} size={16} />
      </button>
      {advancedOpen ? <div className="system-advanced__body">
        <section className="system-advanced__group">
          <h3>{t("systemSettings.security.title")}</h3>
          <NumberField disabled={saving !== null} label={t("systemSettings.security.sessionTtl")} max={3650} min={1} onChange={(days) => setSecurity({ ...security, session_ttl_days: days })} value={security.session_ttl_days} />
          <NumberField disabled={saving !== null} label={t("systemSettings.security.attempts")} max={1000} min={1} onChange={(attempts) => setSecurity({ ...security, rate_limit: { ...security.rate_limit, max_attempts: attempts } })} value={security.rate_limit.max_attempts} />
          <NumberField disabled={saving !== null} label={t("systemSettings.security.window")} max={86400} min={1} onChange={(seconds) => setSecurity({ ...security, rate_limit: { ...security.rate_limit, window_seconds: seconds } })} value={security.rate_limit.window_seconds} />
        </section>
        <section className="system-advanced__group">
          <h3>{t("systemSettings.engine.title")}</h3>
          <NumberField disabled={saving !== null} hint={t("systemSettings.engine.restartHint")} label={t("systemSettings.engine.tick")} max={3600} min={0.1} onChange={(tick) => setEngine({ ...engine, tick_interval_sec: tick })} step={0.1} value={engine.tick_interval_sec} />
          <div className="system-advanced__actions"><Button disabled={saving !== null} onClick={() => { void saveAdvanced() }} type="button">{t("systemSettings.actions.saveAdvanced")}</Button></div>
        </section>
      </div> : null}
    </section> : null}
  </section>
}

function SettingsSection({ children, description, id, title }: { readonly children: ReactNode; readonly description?: string; readonly id: string; readonly title: string }) {
  return <section className="system-settings__section" aria-labelledby={`system-settings-${id}`}>
    <div className="system-settings__section-heading">
      <h2 id={`system-settings-${id}`}>{title}</h2>
      {description ? <span>{description}</span> : null}
    </div>
    {children}
  </section>
}

function QuotaStat({ action, label, value }: { readonly action?: ReactNode; readonly label: string; readonly value: string }) {
  return <div className="system-quota__stat">
    <span>{label}</span>
    <div className="system-quota__value-row">
      <strong>{value}</strong>
      {action ? <div className="system-quota__stat-action">{action}</div> : null}
    </div>
  </div>
}

function SystemCapabilities({ csrfToken }: { readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const state = useToolsPermissions(csrfToken)
  const [expanded, setExpanded] = useState<readonly ToolKey[]>([])

  if (state.drafts === null) {
    return <div className="system-settings__panel system-capabilities">
      {state.error ? <Notice kind="error" message={resolveLocalizedError(state.error, locale) ?? t("tools.errors.load")} /> : <p className="empty-state">{t("systemSettings.capabilities.loading")}</p>}
    </div>
  }
  const drafts = state.drafts
  const toggleExpanded = (toolKey: ToolKey): void => setExpanded((current) => current.includes(toolKey)
    ? current.filter((item) => item !== toolKey)
    : [...current, toolKey])
  const toolError = (toolKey: ToolKey): string | null => resolveLocalizedError(state.toolErrors[toolKey], locale)
    ?? (state.toolErrors[toolKey] === null ? null : t("tools.errors.save"))

  return <div className="system-settings__panel system-capabilities">
    {state.error ? <Notice kind="error" message={resolveLocalizedError(state.error, locale) ?? t("tools.errors.load")} /> : null}
    {TOOL_META.map((meta) => {
      const draft = drafts[meta.key]
      const title = t(meta.titleKey)
      const isExpanded = expanded.includes(meta.key)
      const details = meta.key === "web_search"
        ? <div className="system-capability-details" data-provider={drafts.web_search.provider}><WebSearchToolDetails
            dirty={state.dirtyTools.includes(meta.key)}
            draft={drafts.web_search}
            error={toolError(meta.key)}
            onCancel={() => state.cancelTool(meta.key)}
            onChange={state.changeWebSearch}
            onSave={() => { void state.saveTool(meta.key) }}
            onVerify={() => { void state.verifyTool(meta.key) }}
            saving={state.savingTool === meta.key}
            verification={state.verification[meta.key]}
            verifying={state.verifying === meta.key}
          /></div>
        : <LocalFileToolDetails
            dirty={state.dirtyTools.includes(meta.key)}
            draft={drafts.local_file}
            error={toolError(meta.key)}
            onCancel={() => state.cancelTool(meta.key)}
            onChange={state.changeLocalFile}
            onSave={() => { void state.saveTool(meta.key) }}
            onVerify={() => { void state.verifyTool(meta.key) }}
            saving={state.savingTool === meta.key}
            verification={state.verification[meta.key]}
            verifying={state.verifying === meta.key}
          />
      return <ToolSettingsRow
        collapseLabel={t("tools.actions.collapse", { name: title })}
        collapseText={t("tools.actions.collapseConfig")}
        details={details}
        disabledLabel={t("tools.status.disabled")}
        enabled={draft.enabled}
        enabledLabel={t("tools.status.enabled")}
        expandLabel={t("tools.actions.expand", { name: title })}
        expandText={t("tools.actions.expandConfig")}
        expanded={isExpanded}
        key={meta.key}
        onToggle={(enabled) => {
          state.toggleTool(meta.key, enabled)
          if (!expanded.includes(meta.key)) setExpanded((current) => [...current, meta.key])
        }}
        onToggleDetails={() => toggleExpanded(meta.key)}
        pending={state.savingTool === meta.key}
        statusLabel={t(draft.enabled ? "systemSettings.capabilities.available" : "systemSettings.capabilities.disabled")}
        switchLabel={t(draft.enabled ? "tools.actions.disable" : "tools.actions.enable", { name: title })}
        title={title}
        toolKey={meta.key}
        unsavedLabel={state.dirtyTools.includes(meta.key) ? t("tools.status.unsaved") : ""}
      />
    })}
  </div>
}
