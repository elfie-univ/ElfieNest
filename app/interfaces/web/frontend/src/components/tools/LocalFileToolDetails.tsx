import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"

import type { LocalFileToolConfig, ValidationSuite } from "../../api/owner-tools"
import { FieldRow } from "../FieldRow"
import { Notice } from "../Notice"
import { NumberField } from "../NumberField"
import type { LocalFileDraftUpdate } from "./tool-model"

type LocalFileToolDetailsProps = {
  readonly dirty: boolean
  readonly draft: LocalFileToolConfig
  readonly error: string | null
  readonly onCancel: () => void
  readonly onChange: (update: LocalFileDraftUpdate) => void
  readonly onSave: () => void
  readonly onVerify: () => void
  readonly saving: boolean
  readonly verification: ValidationSuite | null
  readonly verifying: boolean
}

export function LocalFileToolDetails({
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
}: LocalFileToolDetailsProps) {
  const { t } = useTranslation("manage")
  const result = verification?.results[0]

  return <div className="tool-details">
    <h3 className="tool-details__heading">{t("tools.detailsTitle")}</h3>
    {error ? <Notice kind="error" message={error} /> : null}
    <div className="tool-details__fields">
      <FieldRow
        control={({ inputId }) => <div className="tool-readonly-value" id={inputId}>{t("tools.localFile.scopeValue")}</div>}
        inputId="local-file-scope"
        label={t("tools.localFile.scope")}
      />
      <NumberField
        label={t("tools.localFile.maxReadBytes")}
        max={1_000_000}
        min={1}
        onChange={(max_read_bytes) => onChange({ max_read_bytes })}
        value={draft.max_read_bytes}
      />
    </div>
    {result ? <p className={`tool-validation tool-validation--${result.status}`} role="status">{result.message}</p> : null}
    {verification?.passed === false ? <p className="tool-details__note">{t("tools.validation.failed")}</p> : null}
    <div className="tool-details__actions">
      <Button disabled={saving} onClick={onCancel} type="button" variant="ghost">{t("tools.actions.cancel")}</Button>
      <Button disabled={saving || verifying} onClick={onSave} type="button">{saving ? t("tools.actions.saving") : t("tools.actions.save")}</Button>
      <Button disabled={dirty || saving || verifying} onClick={onVerify} type="button" variant="outline">{verifying ? t("tools.actions.verifying") : t("tools.actions.verify")}</Button>
    </div>
  </div>
}
