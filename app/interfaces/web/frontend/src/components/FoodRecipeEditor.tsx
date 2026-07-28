import { Button } from "@/components/ui/button"
import { useEffect, useState } from "react"

import type { ExecutionProfile, FoodRecipe } from "../api/owner-foods"
import type { SelectFieldOption } from "./SelectField"
import { ExecutionProfileFields } from "./ExecutionProfileFields"

type FoodRecipeEditorProps = {
  readonly food: FoodRecipe
  readonly modelOptions: readonly SelectFieldOption[]
  readonly onCancel: () => void
  readonly onSave: (food: FoodRecipe) => Promise<void>
}

export function FoodRecipeEditor({ food, modelOptions, onCancel, onSave }: FoodRecipeEditorProps) {
  const [draft, setDraft] = useState<FoodRecipe>(food)
  const [pending, setPending] = useState(false)
  useEffect(() => setDraft(food), [food])
  const update = (patch: Partial<FoodRecipe>): void => setDraft((current) => ({ ...current, ...patch }))
  const save = async (): Promise<void> => {
    setPending(true)
    try { await onSave(draft) } finally { setPending(false) }
  }
  return <div aria-label={`编辑 ${food.display_name}`} className="food-recipe-editor" role="group">
    <p className="form-hint">只修改这一种粮食；保存后保留后端验证警告。</p>
    <ExecutionProfileFields label="主" modelOptions={modelOptions} onChange={(primary) => { if (primary) update({ primary }) }} profile={draft.primary} />
    <ExecutionProfileFields label="深度" modelOptions={modelOptions} onChange={(deep) => update({ deep })} optional profile={draft.deep} />
    <ExecutionProfileFields label="校验" modelOptions={modelOptions} onChange={(verifier) => update({ verifier })} optional profile={draft.verifier} />
    <section className="food-fallback-editor"><div className="food-fallback-editor__heading"><h3>技术回退</h3><Button variant="outline"
      onClick={() => update({ technical_fallbacks: [...draft.technical_fallbacks, defaultFallback()] })}
      type="button"
    >添加技术回退</Button></div>
    {draft.technical_fallbacks.length === 0 ? <p className="form-hint">没有技术回退模型。</p> : draft.technical_fallbacks.map((fallback, index) => <div className="food-fallback-editor__item" key={index}>
      <ExecutionProfileFields label={`技术回退 ${index + 1}`} modelOptions={modelOptions} onChange={(next) => {
        if (!next) return
        update({ technical_fallbacks: draft.technical_fallbacks.map((item, itemIndex) => itemIndex === index ? next : item) })
      }} profile={fallback} />
      <Button variant="outline" onClick={() => update({ technical_fallbacks: draft.technical_fallbacks.filter((_, itemIndex) => itemIndex !== index) })} type="button">移除此回退</Button>
    </div>)}</section>
    <div className="manage-actions"><Button aria-label={`保存${food.display_name}`} disabled={pending} onClick={() => { void save() }} type="button">{pending ? "保存中…" : "保存"}</Button><Button variant="outline" disabled={pending} onClick={onCancel} type="button">取消</Button></div>
  </div>
}

function defaultFallback(): ExecutionProfile {
  return { model: "", reasoning_profile: "low", max_tokens: 1500, temperature: 0.7, tools: [], provider_options: {} }
}
