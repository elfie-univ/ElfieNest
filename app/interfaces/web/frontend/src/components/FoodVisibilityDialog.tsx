import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { useEffect, useState } from "react"

import {
  foodVisibility,
  updateFoodVisibility,
  type FoodRecipe,
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
  readonly food: FoodRecipe
  readonly onClose: () => void
  readonly onSaved: () => void
}) {
  const [visibility, setVisibility] = useState<FoodVisibility | null>(null)
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    void foodVisibility(food.key).then((result) => {
      setVisibility(result)
      setSelected(new Set(result.user_ids))
    }).catch((reason: unknown) => {
      setError(reason instanceof ApiError ? reason.message : "用户范围加载失败")
    })
  }, [food.key])
  const save = async (): Promise<void> => {
    setSaving(true)
    try {
      await updateFoodVisibility(food.key, [...selected], csrfToken)
      onSaved()
      onClose()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "用户范围没有保存")
    } finally {
      setSaving(false)
    }
  }
  return <ManageDialog
    description="勾选后，该用户名下的精灵可以把此套餐设为主粮。全局默认粮和保底粮始终可用。"
    onOpenChange={(open) => { if (!open) onClose() }}
    open
    title={`分配 ${food.display_name}`}
  >
    {error ? <Notice kind="error" message={error} /> : null}
    <div className="food-visibility-list">
      {visibility?.users.length === 0 ? <p className="form-hint">暂无普通用户。</p> : visibility?.users.map((user) => <label className="food-visibility-row" key={user.user_id}>
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
      <Button disabled={saving || visibility === null} onClick={() => { void save() }} type="button">{saving ? "保存中…" : "保存分配"}</Button>
      <Button variant="outline" disabled={saving} onClick={onClose} type="button">取消</Button>
    </div>
  </ManageDialog>
}
