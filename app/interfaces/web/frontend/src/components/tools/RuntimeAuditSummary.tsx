import { useTranslation } from "react-i18next"

import type { RuntimeAudit } from "../../api/owner-tools"
import { Notice } from "../Notice"

type RuntimeAuditSummaryProps = {
  readonly audit: RuntimeAudit | null
  readonly error: string | null
  readonly loading: boolean
}

function eventTypeLabel(eventType: string, t: (key: string) => string): string {
  switch (eventType) {
    case "tool_call": return "tool_call"
    case "permission_decision": return "permission_decision"
    case "provider_verify": return "provider_verify"
    case "model_call": return "model_call"
    case "fallback": return "fallback"
    case "food_decision": return "food_decision"
    default: return eventType || t("tools.audit.empty")
  }
}

export function RuntimeAuditSummary({ audit, error, loading }: RuntimeAuditSummaryProps) {
  const { t } = useTranslation("manage")
  return <section aria-labelledby="tools-permissions-audit" className="tools-permissions__section">
    <div className="tools-permissions__section-heading">
      <h2 id="tools-permissions-audit">{t("tools.sections.audit")}</h2>
      {audit ? <span className="tool-audit-count">{t("tools.audit.eventCount", { count: audit.event_count })}</span> : null}
    </div>
    {error ? <Notice message={error} /> : null}
    {loading ? <p className="empty-state">{t("tools.loading")}</p> : null}
    {!loading && !error && audit?.events.length === 0 ? <p className="empty-state">{t("tools.audit.empty")}</p> : null}
    {!loading && !error && audit && audit.events.length > 0 ? <ul className="tool-audit-list">
      {audit.events.map((event, index) => <li key={`${event.event_type}-${event.subject}-${index}`}>
        <strong>{event.subject}</strong>
        <span>{t("tools.audit.type", { type: eventTypeLabel(event.event_type, t) })}</span>
        <span>{t("tools.audit.status", { status: event.status })}</span>
      </li>)}
    </ul> : null}
  </section>
}
