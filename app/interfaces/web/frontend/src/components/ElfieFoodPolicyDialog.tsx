import { Button } from "@/components/ui/button"
import { useState } from "react"

import { ApiError, ownerWrite, type OwnerElfie } from "../api/client"
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
  const [defaultFood, setDefaultFood] = useState(elfie.food_policy.default_food)
  const [error, setError] = useState<string | null>(null)
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
      setError(reason instanceof ApiError ? reason.message : "粮食策略没有保存")
    } finally {
      setSaving(false)
    }
  }

  return <ManageDialog
    description={`${elfie.profile.name} · 仅允许调整默认粮食，其他公开档案保持只读。`}
    onOpenChange={(open) => { if (!open) onClose() }}
    open
    title="编辑粮食策略"
  >
    {error ? <Notice kind="error" message={error} /> : null}
    <SelectField
      disabled={saving}
      label="默认粮食"
      onValueChange={setDefaultFood}
      options={elfie.food_policy.allowed_foods.map((food) => ({ label: food, value: food }))}
      value={defaultFood}
    />
    <p className="form-hint">
      允许：{elfie.food_policy.allowed_foods.join("、")}；回退：{elfie.food_policy.fallback_food}
    </p>
    <div className="manage-actions">
      <Button disabled={saving} onClick={() => { void save() }} type="button">
        {saving ? "保存中…" : "保存粮食策略"}
      </Button>
      <Button variant="outline" disabled={saving} onClick={onClose} type="button">
        取消
      </Button>
    </div>
  </ManageDialog>
}
