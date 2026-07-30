import { Button } from "@/components/ui/button"
import { useTranslation } from "react-i18next"

import type { ExecutionProfile, FoodPreview, FoodRecipe } from "../api/owner-foods"
import { ManageDialog } from "./ManageDialog"

type FoodPreviewDialogProps = {
  readonly onContinue: () => void
  readonly onOpenChange: (open: boolean) => void
  readonly open: boolean
  readonly preview: FoodPreview | null
}

export function FoodPreviewDialog({ onContinue, onOpenChange, open, preview }: FoodPreviewDialogProps) {
  const { t } = useTranslation("manage")
  if (!preview) return null
  const foodKeys = Array.from(new Set([
    ...Object.keys(preview.current.foods),
    ...Object.keys(preview.candidate.foods),
  ]))
  return <ManageDialog
    contentClassName="food-preview-dialog"
    description={t("foods.dialogs.previewDescription")}
    onOpenChange={onOpenChange}
    open={open}
    title={t("foods.dialogs.previewTitle")}
  >
    <div className="food-diff-list">
      {foodKeys.length === 0 ? <p className="empty-state">{t("foods.empty.preview")}</p> : foodKeys.map((foodKey) => {
        const current = preview.current.foods[foodKey]
        const candidate = preview.candidate.foods[foodKey]
        return <article className="food-diff-card" key={foodKey}>
          <h3>{candidate?.display_name ?? current?.display_name ?? foodKey}</h3>
          <dl>{roleDiffs(current, candidate, t).map(([role, oldModel, newModel]) => <div key={role}><dt>{role}</dt><dd>{oldModel} → {newModel}</dd></div>)}</dl>
          {preview.changes.find((change) => change.food_key === foodKey)?.warnings.map((warning) => <p className="form-hint" key={warning}>{warning}</p>)}
        </article>
      })}
      {preview.warnings.map((warning) => <p className="form-hint" key={warning}>{warning}</p>)}
      <div className="manage-actions"><Button disabled={!preview.has_changes} onClick={onContinue} type="button">{t("foods.actions.continueApply")}</Button><Button variant="outline" onClick={() => onOpenChange(false)} type="button">{t("foods.actions.closePreview")}</Button></div>
    </div>
  </ManageDialog>
}

function roleDiffs(
  current: FoodRecipe | undefined,
  candidate: FoodRecipe | undefined,
  t: (key: string, options?: Readonly<Record<string, unknown>>) => string,
): readonly [string, string, string][] {
  const pairs: readonly [string, ExecutionProfile | null | undefined, ExecutionProfile | null | undefined][] = [
    [t("foods.roles.primary"), current?.primary, candidate?.primary],
    [t("foods.roles.deep"), current?.deep, candidate?.deep],
    [t("foods.roles.verifier"), current?.verifier, candidate?.verifier],
  ]
  const fallbackCount = Math.max(current?.technical_fallbacks.length ?? 0, candidate?.technical_fallbacks.length ?? 0)
  const fallbacks = Array.from({ length: fallbackCount }, (_, index) => [
    t("foods.roles.fallback", { number: index + 1 }),
    current?.technical_fallbacks[index],
    candidate?.technical_fallbacks[index],
  ] as const)
  return [...pairs, ...fallbacks]
    .filter(([, oldProfile, newProfile]) => (oldProfile?.model ?? t("foods.values.notConfigured")) !== (newProfile?.model ?? t("foods.values.notConfigured")))
    .map(([role, oldProfile, newProfile]) => [role, oldProfile?.model || t("foods.values.notConfigured"), newProfile?.model || t("foods.values.notConfigured")])
}
