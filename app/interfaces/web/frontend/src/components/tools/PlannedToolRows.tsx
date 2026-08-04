import { useTranslation } from "react-i18next"

const PLANNED_TOOL_KEYS = [
  "code",
  "terminal",
  "fileWrite",
  "tasks",
  "subagents",
  "skillEvolution",
] as const

export function PlannedToolRows() {
  const { t } = useTranslation("manage")
  return <section aria-labelledby="tools-permissions-unavailable" className="tools-permissions__section">
    <div className="tools-permissions__section-heading">
      <h2 id="tools-permissions-unavailable">{t("tools.sections.unavailable")}</h2>
    </div>
    <div className="planned-tool-list">
      {PLANNED_TOOL_KEYS.map((key) => <article className="planned-tool-row" data-planned-tool={key} key={key}>
        <div>
          <strong>{t(`tools.future.${key}`)}</strong>
        </div>
        <span className="planned-tool-row__status">{t("tools.status.unavailable")}</span>
      </article>)}
    </div>
  </section>
}
