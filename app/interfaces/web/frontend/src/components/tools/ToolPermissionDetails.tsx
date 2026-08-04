import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"

import type { EditablePermissionMode, ToolPermissionAction } from "../../api/owner-tools"
import { SelectField } from "../SelectField"
import { assertNever, type PermissionMode } from "./tool-model"

type ToolPermissionDetailsProps = {
  readonly action: ToolPermissionAction
  readonly dirty: boolean
  readonly error: string | null
  readonly mode: PermissionMode
  readonly onChange: (mode: EditablePermissionMode) => void
  readonly onSave: () => void
  readonly saving: boolean
}

function modeLabel(mode: PermissionMode, t: (key: string) => string): string {
  switch (mode) {
    case "allow": return t("tools.permissions.allow")
    case "deny": return t("tools.permissions.deny")
    case "ask": return t("tools.permissions.ask")
    case "owner": return t("tools.permissions.owner")
    default: return assertNever(mode)
  }
}

export function ToolPermissionDetails({
  action,
  dirty,
  error,
  mode,
  onChange,
  onSave,
  saving,
}: ToolPermissionDetailsProps) {
  const { t } = useTranslation("manage")
  const titleId = `tool-permission-${action.toLowerCase()}-title`
  const editableMode = mode === "allow" || mode === "deny"
  const currentValue = editableMode ? mode : ""

  return <section className="tool-permission-details" aria-labelledby={titleId}>
    <div className="tool-details__subheading">
      <h3 id={titleId}>{t("tools.sections.permissions")}</h3>
    </div>
    <SelectField
      disabled={!editableMode}
      label={t("tools.permissions.label")}
      onValueChange={(value) => onChange(value === "allow" ? "allow" : "deny")}
      options={[
        { label: t("tools.permissions.allow"), value: "allow" },
        { label: t("tools.permissions.deny"), value: "deny" },
      ]}
      {...(editableMode ? {} : { placeholder: modeLabel(mode, t) })}
      value={currentValue}
    />
    {!editableMode ? <p className="tool-details__note">{modeLabel(mode, t)}</p> : null}
    {error ? <p className="tool-details__error" role="alert">{error}</p> : null}
    <div className="tool-details__actions">
      <Button disabled={!dirty || saving} onClick={onSave} type="button">{saving ? t("tools.actions.savingPermission") : t("tools.actions.savePermission")}</Button>
    </div>
  </section>
}
