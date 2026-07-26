import { useEffect, useState } from "react"

import type { ExecutionProfile, FoodRecipe } from "../api/owner-foods"
import type { SelectOption } from "./SelectField"
import { ExecutionProfileFields } from "./ExecutionProfileFields"
import { ManagerDialog } from "./ManagerDialog"

type FoodRecipeEditorProps = {
  readonly food: FoodRecipe | null
  readonly modelOptions: readonly SelectOption[]
  readonly onOpenChange: (open: boolean) => void
  readonly onSave: (food: FoodRecipe) => Promise<void>
  readonly open: boolean
}

export function FoodRecipeEditor({ food, modelOptions, onOpenChange, onSave, open }: FoodRecipeEditorProps) {
  const [draft, setDraft] = useState<FoodRecipe | null>(food)
  const [pending, setPending] = useState(false)
  useEffect(() => { if (open) setDraft(food) }, [food, open])
  if (!food || !draft) return null
  const update = (patch: Partial<FoodRecipe>): void => setDraft((current) => current ? { ...current, ...patch } : current)
  const save = async (): Promise<void> => {
    setPending(true)
    try { await onSave(draft) } finally { setPending(false) }
  }
  return <ManagerDialog
    contentClassName="food-recipe-dialog"
    description="只修改这一种粮食；保存后保留后端验证警告。"
    onOpenChange={onOpenChange}
    open={open}
    title={`编辑 ${food.display_name}`}
  >
    <div className="food-recipe-editor">
      <ExecutionProfileFields label="主" modelOptions={modelOptions} onChange={(primary) => { if (primary) update({ primary }) }} profile={draft.primary} />
      <ExecutionProfileFields label="深度" modelOptions={modelOptions} onChange={(deep) => update({ deep })} optional profile={draft.deep} />
      <ExecutionProfileFields label="校验" modelOptions={modelOptions} onChange={(verifier) => update({ verifier })} optional profile={draft.verifier} />
      <section className="food-fallback-editor"><div className="food-fallback-editor__heading"><h3>技术回退</h3><button
        className="button button--quiet"
        onClick={() => update({ technical_fallbacks: [...draft.technical_fallbacks, defaultFallback()] })}
        type="button"
      >添加技术回退</button></div>
      {draft.technical_fallbacks.length === 0 ? <p className="form-hint">没有技术回退模型。</p> : draft.technical_fallbacks.map((fallback, index) => <div className="food-fallback-editor__item" key={index}>
        <ExecutionProfileFields label={`技术回退 ${index + 1}`} modelOptions={modelOptions} onChange={(next) => {
          if (!next) return
          update({ technical_fallbacks: draft.technical_fallbacks.map((item, itemIndex) => itemIndex === index ? next : item) })
        }} profile={fallback} />
        <button className="button button--quiet" onClick={() => update({ technical_fallbacks: draft.technical_fallbacks.filter((_, itemIndex) => itemIndex !== index) })} type="button">移除此回退</button>
      </div>)}</section>
      <div className="manage-actions"><button aria-label={`保存${food.display_name}`} className="button" disabled={pending} onClick={() => { void save() }} type="button">{pending ? "保存中…" : "保存"}</button><button className="button button--quiet" disabled={pending} onClick={() => onOpenChange(false)} type="button">取消</button></div>
    </div>
  </ManagerDialog>
}

function defaultFallback(): ExecutionProfile {
  return { model: "", reasoning_profile: "low", max_tokens: 1500, temperature: 0.7, tools: [], provider_options: {} }
}
