import { useTranslation } from "react-i18next"

import { resolveLocalizedError } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { Notice } from "./Notice"
import { PlannedToolRows } from "./tools/PlannedToolRows"
import { RuntimeAuditSummary } from "./tools/RuntimeAuditSummary"
import { ToolDetailsContent } from "./tools/ToolDetailsContent"
import { ToolSettingsRow } from "./tools/ToolSettingsRow"
import { permissionActionForTool, type PermissionMode } from "./tools/tool-model"
import { useToolsPermissions } from "./tools/useToolsPermissions"
import "./tools-permissions.css"

const TOOL_META = [
  { key: "web_search", titleKey: "tools.webSearch.title", descriptionKey: "tools.webSearch.description" },
  { key: "local_file", titleKey: "tools.localFile.title", descriptionKey: "tools.localFile.description" },
] as const

type ToolPermissionPanelProps = {
  readonly csrfToken: string
}

function toolStatus(mode: PermissionMode, enabled: boolean, t: (key: string) => string): string {
  if (!enabled) return t("tools.status.disabled")
  switch (mode) {
    case "allow": return t("tools.status.allowed")
    case "deny": return t("tools.status.blocked")
    case "ask": return t("tools.status.blocked")
    case "owner": return t("tools.status.blocked")
  }
}

function errorText(error: ReturnType<typeof useToolsPermissions>["toolErrors"]["web_search"], locale: Parameters<typeof resolveLocalizedError>[1], fallback: string): string | null {
  return resolveLocalizedError(error, locale) ?? (error === null ? null : fallback)
}

export function ToolsPermissionsPanel({ csrfToken }: ToolPermissionPanelProps) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const state = useToolsPermissions(csrfToken)

  if (state.drafts === null || state.permissionDrafts === null) {
    return <section className="tools-permissions" aria-labelledby="tools-permissions-title">
      {state.error ? <Notice kind="error" message={resolveLocalizedError(state.error, locale) ?? t("tools.errors.load")} /> : <p className="empty-state">{t("tools.loading")}</p>}
    </section>
  }
  const drafts = state.drafts
  const permissionDrafts = state.permissionDrafts

  return <section className="tools-permissions" aria-labelledby="tools-permissions-title">
    <header className="tools-permissions__intro">
      <p id="tools-permissions-title">{t("tools.description")}</p>
    </header>
    {state.error ? <Notice kind="error" message={resolveLocalizedError(state.error, locale) ?? t("tools.errors.load")} /> : null}
    <section aria-labelledby="tools-permissions-available" className="tools-permissions__section">
      <div className="tools-permissions__section-heading">
        <h2 id="tools-permissions-available">{t("tools.sections.available")}</h2>
      </div>
      <div className="tool-settings-list">
        {TOOL_META.map((meta) => {
          const draft = drafts[meta.key]
          const action = permissionActionForTool(meta.key)
          const mode = permissionDrafts[action]
          const title = t(meta.titleKey)
          return <ToolSettingsRow
            details={<ToolDetailsContent
              dirtyPermission={state.dirtyPermissions.includes(action)}
              dirtyTool={state.dirtyTools.includes(meta.key)}
              localFile={drafts.local_file}
              onCancelPermission={state.cancelPermission}
              onCancelTool={state.cancelTool}
              onChangeLocalFile={state.changeLocalFile}
              onChangePermission={(nextMode) => state.changePermission(action, nextMode)}
              onChangeWebSearch={state.changeWebSearch}
              onSavePermission={(nextAction) => { void state.savePermission(nextAction) }}
              onSaveTool={(nextToolKey) => { void state.saveTool(nextToolKey) }}
              onVerifyTool={(nextToolKey) => { void state.verifyTool(nextToolKey) }}
              permissionError={errorText(state.permissionErrors[action], locale, t("tools.errors.save"))}
              permissionMode={mode}
              savingPermission={state.savingPermission === action}
              savingTool={state.savingTool === meta.key}
              toolError={errorText(state.toolErrors[meta.key], locale, t("tools.errors.save"))}
              toolKey={meta.key}
              verification={state.verification[meta.key]}
              verifying={state.verifying === meta.key}
              webSearch={drafts.web_search}
            />}
            disabledLabel={t("tools.status.disabled")}
            enabled={draft.enabled}
            enabledLabel={t("tools.status.enabled")}
            collapseLabel={t("tools.actions.collapse", { name: title })}
            collapseText={t("tools.actions.collapseConfig")}
            expandLabel={t("tools.actions.expand", { name: title })}
            expandText={t("tools.actions.expandConfig")}
            expanded={state.expanded.includes(meta.key)}
            key={meta.key}
            onToggle={(enabled) => state.toggleTool(meta.key, enabled)}
            onToggleDetails={() => state.toggleExpanded(meta.key)}
            pending={state.savingTool === meta.key}
            statusLabel={toolStatus(mode, draft.enabled, t)}
            switchLabel={t(draft.enabled ? "tools.actions.disable" : "tools.actions.enable", { name: title })}
            title={title}
            description={t(meta.descriptionKey)}
            toolKey={meta.key}
            unsavedLabel={state.dirtyTools.includes(meta.key) ? t("tools.status.unsaved") : ""}
          />
        })}
      </div>
    </section>
    <PlannedToolRows />
    <RuntimeAuditSummary
      audit={state.audit}
      error={errorText(state.auditError, locale, t("tools.errors.audit"))}
      loading={state.auditLoading}
    />
  </section>
}
