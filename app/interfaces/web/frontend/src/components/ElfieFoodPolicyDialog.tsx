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
  const [mainFood, setMainFood] = useState(elfie.food_policy.main_food_id || elfie.food_policy.effective_main_food_id)
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
          main_food_id: mainFood,
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
    description={`${elfie.profile.name} · 这里只选择一份主粮；保底策略由全局粮食配置负责。`}
    onOpenChange={(open) => { if (!open) onClose() }}
    open
    title="选择主粮"
  >
    {error ? <Notice kind="error" message={error} /> : null}
    <SelectField
      disabled={saving}
      label="主粮"
      onValueChange={setMainFood}
      options={elfie.food_policy.main_food_options.map((food) => ({ label: food.display_name, value: food.food_id }))}
      value={mainFood}
    />
    <div className="manage-actions">
      <Button disabled={saving} onClick={() => { void save() }} type="button">
        {saving ? "保存中…" : "保存主粮"}
      </Button>
      <Button variant="outline" disabled={saving} onClick={onClose} type="button">
        取消
      </Button>
    </div>
  </ManageDialog>
}
