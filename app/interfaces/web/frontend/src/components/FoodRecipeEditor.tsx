import { Button } from "@/components/ui/button"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

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
  const { t } = useTranslation("manage")
  const [draft, setDraft] = useState(food)
  const [pending, setPending] = useState(false)
  useEffect(() => setDraft(food), [food])
  const options = [{ label: t("foodPackages.recipe.none"), value: NONE }, ...modelOptions]
  const setRole = (role: "primary" | "reasoning" | "vision" | "tool", value: string): void => {
    setDraft((current) => ({
      ...current,
      roles: { ...current.roles, [role]: value === NONE ? null : { model: value } },
    }))
  }
  return <div className="food-recipe-editor">
    <TextField label={t("foodPackages.recipe.name")} onChange={(display_name) => setDraft((current) => ({ ...current, display_name }))} value={draft.display_name} />
    {([
      ["primary", t("foodPackages.roles.primary")],
      ["reasoning", t("foodPackages.roles.reasoning")],
      ["vision", t("foodPackages.roles.vision")],
      ["tool", t("foodPackages.roles.tool")],
    ] as const).map(([role, label]) => <SelectField
      key={role}
      label={label}
      onValueChange={(value) => setRole(role, value)}
      options={options}
      value={draft.roles[role]?.model ?? NONE}
    />)}
    <SelectField
      label={t("foodPackages.recipe.fallback")}
      onValueChange={(value) => setDraft((current) => ({ ...current, roles: { ...current.roles, fallback: value === NONE ? [] : [{ model: value }] } }))}
      options={options}
      value={draft.roles.fallback[0]?.model ?? NONE}
    />
    <div className="manage-actions">
      <Button disabled={pending} onClick={() => { setPending(true); void onSave(draft).finally(() => setPending(false)) }} type="button">{t("foodPackages.actions.save")}</Button>
      <Button disabled={pending} onClick={onCancel} type="button" variant="outline">{t("foodPackages.actions.cancel")}</Button>
    </div>
  </div>
}
