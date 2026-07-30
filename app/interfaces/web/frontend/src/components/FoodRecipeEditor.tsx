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
  readonly onSave: (food: FoodRecipe) => Promise<void>
}

export function FoodRecipeEditor({ food, modelOptions, onCancel, onSave }: FoodRecipeEditorProps) {
  const { t } = useTranslation("manage")
  const [draft, setDraft] = useState<FoodRecipe>(food)
  const [pending, setPending] = useState(false)
  useEffect(() => setDraft(food), [food])
  const options = [{ label: "未配置", value: NONE }, ...modelOptions]
  const setRole = (role: "primary" | "reasoning" | "vision" | "tool", value: string): void => {
    setDraft((current) => ({
      ...current,
      roles: { ...current.roles, [role]: value === NONE ? null : { model: value } },
    }))
  }
  return <div aria-label={t("foods.editor.ariaLabel", { name: food.display_name })} className="food-recipe-editor" role="group">
    <p className="form-hint">{t("foods.editor.hint")}</p>
    <ExecutionProfileFields label={t("foods.roles.primaryShort")} modelOptions={modelOptions} onChange={(primary) => { if (primary) update({ primary }) }} profile={draft.primary} />
    <ExecutionProfileFields label={t("foods.roles.deepShort")} modelOptions={modelOptions} onChange={(deep) => update({ deep })} optional profile={draft.deep} />
    <ExecutionProfileFields label={t("foods.roles.verifierShort")} modelOptions={modelOptions} onChange={(verifier) => update({ verifier })} optional profile={draft.verifier} />
    <section className="food-fallback-editor"><div className="food-fallback-editor__heading"><h3>{t("foods.editor.fallbackTitle")}</h3><Button variant="outline"
      onClick={() => update({ technical_fallbacks: [...draft.technical_fallbacks, defaultFallback()] })}
      type="button"
    >{t("foods.actions.addFallback")}</Button></div>
    {draft.technical_fallbacks.length === 0 ? <p className="form-hint">{t("foods.editor.emptyFallbacks")}</p> : draft.technical_fallbacks.map((fallback, index) => <div className="food-fallback-editor__item" key={index}>
      <ExecutionProfileFields label={t("foods.roles.fallback", { number: index + 1 })} modelOptions={modelOptions} onChange={(next) => {
        if (!next) return
        update({ technical_fallbacks: draft.technical_fallbacks.map((item, itemIndex) => itemIndex === index ? next : item) })
      }} profile={fallback} />
      <Button variant="outline" onClick={() => update({ technical_fallbacks: draft.technical_fallbacks.filter((_, itemIndex) => itemIndex !== index) })} type="button">{t("foods.actions.removeFallback")}</Button>
    </div>)}</section>
    <div className="manage-actions"><Button aria-label={t("foods.actions.saveFor", { name: food.display_name })} disabled={pending} onClick={() => { void save() }} type="button">{pending ? t("foods.actions.saving") : t("foods.actions.save")}</Button><Button variant="outline" disabled={pending} onClick={onCancel} type="button">{t("foods.actions.cancel")}</Button></div>
  </div>
}
