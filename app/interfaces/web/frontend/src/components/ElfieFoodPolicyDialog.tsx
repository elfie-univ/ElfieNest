import { Button } from "@/components/ui/button"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { ownerWrite, type OwnerElfie } from "../api/client"
import {
  describeApiError,
  resolveLocalizedError,
  type LocalizedErrorState,
} from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"

type ElfieFoodPolicyDialogProps = {
  readonly csrfToken: string
  readonly elfie: OwnerElfie
  readonly onClose: () => void
  readonly onSaved: () => Promise<void>
}

export function ElfieFoodPolicyDialog({
  csrfToken,
  elfie,
  onClose,
  onSaved,
}: ElfieFoodPolicyDialogProps) {
  const { t, i18n } = useTranslation("manage")
  const [defaultFood, setDefaultFood] = useState(elfie.food_policy.default_food)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [saving, setSaving] = useState(false)

  const save = async (): Promise<void> => {
    setSaving(true)
    try {
      await ownerWrite(
        `/api/user/elfies/${encodeURIComponent(elfie.elfie_id)}/food-policy/`,
        "PUT",
        csrfToken,
        {
          default_food: defaultFood,
          allowed_foods: elfie.food_policy.allowed_foods,
          fallback_food: elfie.food_policy.fallback_food,
        },
      )
      await onSaved()
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setSaving(false)
    }
  }

  return <ManageDialog
    description={t("elfieFoodPolicy.description", { name: elfie.profile.name })}
    onOpenChange={(open) => { if (!open) onClose() }}
    open
    title={t("elfieFoodPolicy.title")}
  >
    {error ? <Notice kind="error" message={resolveLocalizedError(error, currentLocale(i18n)) ?? t("errors.save")} /> : null}
    <SelectField
      disabled={saving}
      label={t("elfieFoodPolicy.fields.defaultFood")}
      onValueChange={setDefaultFood}
      options={elfie.food_policy.allowed_foods.map((food) => ({ label: food, value: food }))}
      value={defaultFood}
    />
    <p className="form-hint">
      {t("elfieFoodPolicy.hint", {
        allowed: elfie.food_policy.allowed_foods.join(t("elfies.values.foodSeparator")),
        fallback: elfie.food_policy.fallback_food,
      })}
    </p>
    <div className="manage-actions">
      <Button disabled={saving} onClick={() => { void save() }} type="button">
        {saving ? t("elfieFoodPolicy.actions.saving") : t("elfieFoodPolicy.actions.save")}
      </Button>
      <Button variant="outline" disabled={saving} onClick={onClose} type="button">
        {t("elfieFoodPolicy.actions.cancel")}
      </Button>
    </div>
  </ManageDialog>
}
