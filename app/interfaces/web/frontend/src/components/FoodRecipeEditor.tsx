import { Button } from "@/components/ui/button"
import { useEffect, useState } from "react"

import type { FoodPackage } from "../api/owner-foods"
import { SelectField, type SelectFieldOption } from "./SelectField"
import { TextField } from "./TextField"

const NONE = "__none__"

export function FoodRecipeEditor({ food, modelOptions, onCancel, onSave }: {
  readonly food: FoodPackage
  readonly modelOptions: readonly SelectFieldOption[]
  readonly onCancel: () => void
  readonly onSave: (food: FoodPackage) => Promise<void>
}) {
  const [draft, setDraft] = useState(food)
  const [pending, setPending] = useState(false)
  useEffect(() => setDraft(food), [food])
  const options = [{ label: "未配置", value: NONE }, ...modelOptions]
  const setRole = (role: "primary" | "reasoning" | "vision" | "tool", value: string): void => {
    setDraft((current) => ({
      ...current,
      roles: { ...current.roles, [role]: value === NONE ? null : { model: value } },
    }))
  }
  return <div className="food-recipe-editor">
    <TextField label="套餐名称" onChange={(display_name) => setDraft((current) => ({ ...current, display_name }))} value={draft.display_name} />
    {([
      ["primary", "Primary"],
      ["reasoning", "Reasoning"],
      ["vision", "Vision"],
      ["tool", "Tool"],
    ] as const).map(([role, label]) => <SelectField
      key={role}
      label={label}
      onValueChange={(value) => setRole(role, value)}
      options={options}
      value={draft.roles[role]?.model ?? NONE}
    />)}
    <SelectField
      label="Fallback 1"
      onValueChange={(value) => setDraft((current) => ({ ...current, roles: { ...current.roles, fallback: value === NONE ? [] : [{ model: value }] } }))}
      options={options}
      value={draft.roles.fallback[0]?.model ?? NONE}
    />
    <div className="manage-actions">
      <Button disabled={pending} onClick={() => { setPending(true); void onSave(draft).finally(() => setPending(false)) }} type="button">保存</Button>
      <Button disabled={pending} onClick={onCancel} type="button" variant="outline">取消</Button>
    </div>
  </div>
}
