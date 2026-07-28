import { Button } from "@/components/ui/button"
import type { ExecutionProfile, FoodPreview, FoodRecipe } from "../api/owner-foods"
import { ManageDialog } from "./ManageDialog"

type FoodPreviewDialogProps = {
  readonly onContinue: () => void
  readonly onOpenChange: (open: boolean) => void
  readonly open: boolean
  readonly preview: FoodPreview | null
}

export function FoodPreviewDialog({ onContinue, onOpenChange, open, preview }: FoodPreviewDialogProps) {
  if (!preview) return null
  const foodKeys = Array.from(new Set([
    ...Object.keys(preview.current.foods),
    ...Object.keys(preview.candidate.foods),
  ]))
  return <ManageDialog
    contentClassName="food-preview-dialog"
    description="这里仅展示候选差异；关闭不会修改当前粮食目录。"
    onOpenChange={onOpenChange}
    open={open}
    title="粮食更新预览"
  >
    <div className="food-diff-list">
      {foodKeys.length === 0 ? <p className="empty-state">候选中没有粮食配置。</p> : foodKeys.map((foodKey) => {
        const current = preview.current.foods[foodKey]
        const candidate = preview.candidate.foods[foodKey]
        return <article className="food-diff-card" key={foodKey}>
          <h3>{candidate?.display_name ?? current?.display_name ?? foodKey}</h3>
          <dl>{roleDiffs(current, candidate).map(([role, oldModel, newModel]) => <div key={role}><dt>{role}</dt><dd>{oldModel} → {newModel}</dd></div>)}</dl>
          {preview.changes.find((change) => change.food_key === foodKey)?.warnings.map((warning) => <p className="form-hint" key={warning}>{warning}</p>)}
        </article>
      })}
      {preview.warnings.map((warning) => <p className="form-hint" key={warning}>{warning}</p>)}
      <div className="manage-actions"><Button disabled={!preview.has_changes} onClick={onContinue} type="button">继续应用</Button><Button variant="outline" onClick={() => onOpenChange(false)} type="button">关闭预览</Button></div>
    </div>
  </ManageDialog>
}

function roleDiffs(current: FoodRecipe | undefined, candidate: FoodRecipe | undefined): readonly [string, string, string][] {
  const pairs: readonly [string, ExecutionProfile | null | undefined, ExecutionProfile | null | undefined][] = [
    ["主模型", current?.primary, candidate?.primary],
    ["深度模型", current?.deep, candidate?.deep],
    ["校验模型", current?.verifier, candidate?.verifier],
  ]
  const fallbackCount = Math.max(current?.technical_fallbacks.length ?? 0, candidate?.technical_fallbacks.length ?? 0)
  const fallbacks = Array.from({ length: fallbackCount }, (_, index) => [
    `技术回退 ${index + 1}`,
    current?.technical_fallbacks[index],
    candidate?.technical_fallbacks[index],
  ] as const)
  return [...pairs, ...fallbacks]
    .filter(([, oldProfile, newProfile]) => (oldProfile?.model ?? "未配置") !== (newProfile?.model ?? "未配置"))
    .map(([role, oldProfile, newProfile]) => [role, oldProfile?.model || "未配置", newProfile?.model || "未配置"])
}
