import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

import { SEARCH_PROVIDERS, type SearchProvider, type ValidationSuite } from "../../api/owner-tools"
import { FieldRow } from "../FieldRow"
import { Notice } from "../Notice"
import { NumberField } from "../NumberField"
import { SelectField } from "../SelectField"
import { assertNever, type WebSearchDraft, type WebSearchDraftUpdate } from "./tool-model"

type WebSearchToolDetailsProps = {
  readonly dirty: boolean
  readonly draft: WebSearchDraft
  readonly error: string | null
  readonly onCancel: () => void
  readonly onChange: (update: WebSearchDraftUpdate) => void
  readonly onSave: () => void
  readonly onVerify: () => void
  readonly saving: boolean
  readonly verification: ValidationSuite | null
  readonly verifying: boolean
}

type ValidationStatus = ValidationSuite["results"][number]["status"]

function validationLabel(status: ValidationStatus, t: (key: string) => string): string {
  switch (status) {
    case "passed": return t("tools.validation.passed")
    case "failed": return t("tools.validation.failed")
    case "warning": return t("tools.validation.warning")
    case "skipped": return t("tools.validation.skipped")
    default: return assertNever(status)
  }
}

function isSearchProvider(value: string): value is SearchProvider {
  return SEARCH_PROVIDERS.some((provider) => provider === value)
}

export function WebSearchToolDetails({
  dirty,
  draft,
  error,
  onCancel,
  onChange,
  onSave,
  onVerify,
  saving,
  verification,
  verifying,
}: WebSearchToolDetailsProps) {
  const { t } = useTranslation("manage")
  const result = verification?.results[0]

  return <div className="tool-details">
    <h3 className="tool-details__heading">{t("tools.detailsTitle")}</h3>
    <div className="tool-details__intro">
      <p>{t("tools.webSearch.description")}</p>
    </div>
    {error ? <Notice kind="error" message={error} /> : null}
    <div className="tool-details__fields">
      <SelectField
        label={t("tools.webSearch.provider")}
        onValueChange={(provider) => {
          if (isSearchProvider(provider)) onChange({ provider })
        }}
        options={[
          { label: "DuckDuckGo", value: "duckduckgo" },
          { label: "Brave", value: "brave" },
          { label: "Tavily", value: "tavily" },
        ]}
        value={draft.provider}
      />
      <FieldRow
        control={<Input value={draft.api_base} onChange={(event) => onChange({ api_base: event.target.value })} />}
        hint={t("tools.webSearch.apiBaseHint")}
        inputId="web-search-api-base"
        label={t("tools.webSearch.apiBase")}
      />
      <FieldRow
        control={<Input autoComplete="new-password" placeholder={draft.has_api_key ? "••••••••" : undefined} type="password" value={draft.api_key} onChange={(event) => onChange({ api_key: event.target.value })} />}
        hint={draft.has_api_key ? t("tools.webSearch.apiKeyConfigured") : t("tools.webSearch.apiKeyHint")}
        inputId="web-search-api-key"
        label={t("tools.webSearch.apiKey")}
      />
      <NumberField
        hint={t("tools.webSearch.maxResultsHint")}
        label={t("tools.webSearch.maxResults")}
        max={10}
        min={1}
        onChange={(max_results) => onChange({ max_results })}
        value={draft.max_results}
      />
      <NumberField
        hint={t("tools.webSearch.maxResultBytesHint")}
        label={t("tools.webSearch.maxResultBytes")}
        max={1_000_000}
        min={1}
        onChange={(max_result_bytes) => onChange({ max_result_bytes })}
        value={draft.max_result_bytes}
      />
    </div>
    <dl className="tool-details__limits">
      <div><dt>timeout</dt><dd>{draft.timeout_seconds}s</dd></div>
      <div><dt>max_tool_calls</dt><dd>{draft.max_tool_calls}</dd></div>
      <div><dt>max_total_result_bytes</dt><dd>{draft.max_total_result_bytes}</dd></div>
    </dl>
    {result ? <p className={`tool-validation tool-validation--${result.status}`} role="status">
      {validationLabel(result.status, t)}{result.duration_ms === null ? "" : ` · ${t("tools.validation.latency", { value: Math.round(result.duration_ms) })}`}
    </p> : null}
    <div className="tool-details__actions">
      <Button disabled={saving} onClick={onCancel} type="button" variant="ghost">{t("tools.actions.cancel")}</Button>
      <Button disabled={saving || verifying} onClick={onSave} type="button">{saving ? t("tools.actions.saving") : t("tools.actions.save")}</Button>
      <Button disabled={dirty || saving || verifying} onClick={onVerify} type="button" variant="outline">{verifying ? t("tools.actions.verifying") : t("tools.actions.verify")}</Button>
    </div>
  </div>
}
