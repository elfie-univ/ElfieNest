import { Button } from "@/components/ui/button"
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  changeFoodLifecycle,
  createFood,
  deleteFood,
  editFood,
  ownerFoods,
  previewFoodUpdate,
  type FoodCatalog,
  type FoodPackage,
} from "../api/owner-foods"
import { ownerProviders, type ProviderView } from "../api/owner-providers"
import { currentLocale, formatDateTime, formatNumber } from "../i18n/format"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { ApiError } from "../api/http"
import { ConfirmDialog } from "./ConfirmDialog"
import { FoodRecipeEditor } from "./FoodRecipeEditor"
import { FoodRoleTable } from "./FoodRoleTable"
import { FoodVisibilityDialog } from "./FoodVisibilityDialog"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { RefreshButton } from "./RefreshButton"
import type { SelectFieldOption } from "./SelectField"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "./ui/table"

export function OwnerFoodPanel({ csrfToken }: { readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [catalog, setCatalog] = useState<FoodCatalog | null>(null)
  const [providers, setProviders] = useState<readonly ProviderView[]>([])
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set())
  const [editing, setEditing] = useState<FoodRecipe | null>(null)
  const [preview, setPreview] = useState<FoodPreview | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [applyConfirm, setApplyConfirm] = useState(false)
  const [rollbackConfirm, setRollbackConfirm] = useState(false)
  const [pending, setPending] = useState<PendingAction>(null)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async (): Promise<void> => {
    try {
      const [foods, providers] = await Promise.all([ownerFoods(), ownerProviderConnections()])
      setCatalog(foods)
      setConnections(providers.filter((item) => item.enabled && !item.archived))
      setError(null)
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.load"))
    }
  }, [])
  useEffect(() => { void load() }, [load])
  const foods = catalog ? Object.values(catalog.foods) : []
  const modelOptions = useMemo(() => collectModelOptions(providers), [providers])

  const save = async (food: FoodPackage): Promise<void> => {
    try {
      const next = await previewFoodUpdate(csrfToken)
      setPreview(next)
      setPreviewOpen(true)
      setNotice(t("foods.notices.previewGenerated"))
      setError(null)
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(null)
    }
  }
  const apply = async (): Promise<void> => {
    if (!preview) return
    setPending("apply")
    try {
      setCatalog(await applyFoodUpdate(preview, csrfToken))
      setPreview(null)
      setApplyConfirm(false)
      setNotice(t("foods.notices.applied"))
      setError(null)
    } catch (reason: unknown) {
      setApplyConfirm(false)
      if (reason instanceof ApiError && reason.status === 409) {
        setPreview(null)
        setPreviewOpen(false)
        setError(t("foods.notices.expired"))
      } else {
        if (!(reason instanceof Error)) throw reason
        setError(describeApiError(reason, "manage.save"))
      }
    } finally {
      setPending(null)
    }
  }
  const saveFood = async (food: FoodRecipe): Promise<void> => {
    setPending("save")
    try {
      const result = await editFood(food.key, food, csrfToken)
      setFoodWarnings((current) => ({ ...current, [food.key]: result.warnings }))
      setEditing(null)
      setNotice(t(result.warnings.length > 0 ? "foods.notices.savedWithWarnings" : "foods.notices.saved", { name: food.display_name }))
      await load()
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
      throw reason
    }
  }
  const add = async (): Promise<void> => {
    setPending(true)
    try {
      setCatalog(await rollbackFoods(csrfToken))
      setRollbackConfirm(false)
      setNotice(t("foods.notices.rolledBack"))
      setError(null)
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(null)
    }
  }

  return <section aria-label={t("foods.title")} className="manage-card manage-card--wide food-page">
    <div className="manage-head">
      <p>{t("foods.description")}</p>
      <div aria-label={t("foods.labels.headerActions")} className="manage-actions food-page__header-actions" role="group">
        <RefreshButton disabled={pending !== null} label={t("foods.actions.refresh")} onClick={() => { void load() }} />
        <Button disabled={pending !== null} onClick={() => { void generatePreview() }} ref={previewButtonRef} type="button">{pending === "preview" ? t("foods.actions.generating") : t("foods.actions.generatePreview")}</Button>
        <Button variant="outline" disabled={pending !== null} onClick={() => setRollbackConfirm(true)} type="button">{t("foods.actions.rollback")}</Button>
      </div>
    </div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} /> : null}
    {notice ? <Notice message={notice} /> : null}
    {foods.length === 0 ? <div className="manage-empty-state"><h3>{t("foods.empty.title")}</h3><p>{t("foods.empty.description")}</p></div> : <div className="food-table-wrap"><Table aria-label={t("foods.labels.table")} className="food-table"><TableHeader><TableRow><TableHead scope="col">{t("foods.columns.food")}</TableHead><TableHead scope="col">{t("foods.columns.primaryModel")}</TableHead><TableHead scope="col">{t("foods.columns.validation")}</TableHead><TableHead scope="col">{t("foods.columns.sourceUpdated")}</TableHead><TableHead scope="col">{t("foods.columns.actions")}</TableHead></TableRow></TableHeader><TableBody>{foods.map((food) => {
      const isExpanded = expanded.has(food.key)
      const warnings = foodWarnings[food.key] ?? []
      return <Fragment key={food.key}>
        <TableRow key={food.key}>
          <TableHead scope="row"><strong>{food.display_name}</strong><small>{food.description}</small></TableHead>
          <TableCell>{food.primary.model || t("foods.values.notConfigured")}<small>{food.primary.reasoning_profile} · {formatNumber(food.primary.max_tokens, locale)} {t("foods.values.tokenUnit")}</small></TableCell>
          <TableCell><span className={`status-badge status-badge--${food.validation_status}`}>{validationLabel(food.validation_status, t)}</span>{warnings.map((warning) => <small className="food-warning" key={warning}>{warning}</small>)}</TableCell>
          <TableCell>{food.source === "manual" ? t("foods.values.manual") : t("foods.values.auto")}<small>{catalog?.generated_at ? formatDateTime(catalog.generated_at, locale) : t("foods.values.notConfigured")}</small></TableCell>
          <TableCell><div className="manage-actions"><Button variant="outline" aria-label={t(isExpanded ? "foods.actions.collapseFor" : "foods.actions.expandFor", { name: food.display_name })} onClick={() => setExpanded((current) => toggleKey(current, food.key))} type="button">{isExpanded ? t("foods.actions.collapse") : t("foods.actions.expand")}</Button><Button variant="outline" aria-label={t("foods.actions.editFor", { name: food.display_name })} onClick={() => { setEditing(food); setExpanded((current) => addKey(current, food.key)) }} type="button">{t("foods.actions.edit")}</Button></div></TableCell>
        </TableRow>
        {isExpanded ? <TableRow className="food-role-row" key={`${food.key}-roles`}><TableCell colSpan={5}>{editing?.key === food.key
          ? <FoodRecipeEditor food={editing} modelOptions={modelOptions} onCancel={() => setEditing(null)} onSave={saveFood} />
          : <FoodRoleTable food={food} />}</TableCell></TableRow> : null}
      </Fragment>
    })}</TableBody></Table></div>}
    <FoodPreviewDialog onContinue={() => { setPreviewOpen(false); setApplyConfirm(true) }} onOpenChange={(open) => { setPreviewOpen(open); if (!open) window.requestAnimationFrame(() => previewButtonRef.current?.focus()) }} open={previewOpen} preview={preview} />
    <ConfirmDialog confirmLabel={t("foods.actions.applyConfirm")} description={t("foods.dialogs.applyDescription")} onConfirm={() => { void apply() }} onOpenChange={setApplyConfirm} open={applyConfirm} pending={pending === "apply"} title={t("foods.dialogs.applyTitle")} />
    <ConfirmDialog confirmLabel={t("foods.actions.rollbackConfirm")} danger description={t("foods.dialogs.rollbackDescription")} onConfirm={() => { void rollback() }} onOpenChange={setRollbackConfirm} open={rollbackConfirm} pending={pending === "rollback"} title={t("foods.dialogs.rollbackTitle")} />
  </section>
}

function toggle(current: ReadonlySet<string>, key: string, enabled: boolean): ReadonlySet<string> {
  const next = new Set(current)
  if (enabled) next.add(key)
  else next.delete(key)
  return next
}

function addKey(current: ReadonlySet<string>, key: string): ReadonlySet<string> {
  const next = new Set(current)
  next.add(key)
  return next
}

function collectModelOptions(providers: readonly ProviderView[]): readonly SelectFieldOption[] {
  return providers.filter((provider) => provider.configured && provider.models.length > 0).map((provider) => ({
    label: provider.display_name || provider.name,
    options: provider.models.map((model) => ({
      group: provider.display_name || provider.name,
      label: `${provider.display_name || provider.name} · ${model.display_name || model.id}`,
      value: model.id.includes("/") ? model.id : `${provider.provider_id}/${model.id}`,
    })),
  }))
}

function validationLabel(status: string, t: (key: string) => string): string {
  if (status === "passed") return t("foods.validation.passed")
  if (status === "warning") return t("foods.validation.warning")
  if (status === "failed") return t("foods.validation.failed")
  return t("foods.validation.unknown")
}
