import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  foodVisibility,
  updateFoodVisibility,
  type FoodPackage,
  type FoodVisibility,
} from "../api/owner-foods"
import { ApiError } from "../api/http"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"

export function FoodVisibilityDialog({
  csrfToken,
  food,
  onClose,
  onSaved,
}: {
  readonly csrfToken: string
  readonly food: FoodPackage
  readonly onClose: () => void
  readonly onSaved: () => void
}) {
  const { t } = useTranslation("manage")
  const [visibility, setVisibility] = useState<FoodVisibility | null>(null)
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    void foodVisibility(food.key).then((result) => {
      setVisibility(result)
      setSelected(new Set(result.user_ids))
    }).catch((reason: unknown) => {
      setError(reason instanceof ApiError ? reason.message : t("foodPackages.errors.visibilityLoad"))
    })
  }, [food.key])
  const save = async (): Promise<void> => {
    setSaving(true)
    try {
      await updateFoodVisibility(food.key, [...selected], csrfToken)
      onSaved()
      onClose()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : t("foodPackages.errors.visibilitySave"))
    } finally {
      setSaving(false)
    }
  }
  return <ManageDialog
    description={t("foodPackages.visibility.description")}
    onOpenChange={(open) => { if (!open) onClose() }}
    open
    title={t("foodPackages.visibility.title", { name: food.display_name })}
  >
    {error ? <Notice kind="error" message={error} /> : null}
    <div className="food-visibility-list">
      {visibility?.users.length === 0 ? <p className="form-hint">{t("foodPackages.visibility.empty")}</p> : visibility?.users.map((user) => <label className="food-visibility-row" key={user.user_id}>
        <Checkbox
          checked={selected.has(user.user_id)}
          disabled={saving}
          onCheckedChange={(checked) => setSelected((current) => {
            const next = new Set(current)
            if (checked === true) next.add(user.user_id)
            else next.delete(user.user_id)
            return next
          })}
        />
        <span>{user.display_name}</span>
      </label>)}
    </div>
    <div className="manage-actions">
      <Button disabled={saving || visibility === null} onClick={() => { void save() }} type="button">{saving ? t("foodPackages.actions.saving") : t("foodPackages.actions.saveVisibility")}</Button>
      <Button variant="outline" disabled={saving} onClick={onClose} type="button">{t("foodPackages.actions.cancel")}</Button>
    </div>
  </ManageDialog>
}
