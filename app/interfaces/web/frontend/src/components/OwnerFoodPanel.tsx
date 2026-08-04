import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Plus, Users } from "lucide-react"
import { Fragment, useEffect, useMemo, useState } from "react"
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
import { ownerProviderConnections, type ProviderConnection } from "../api/owner-providers"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
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
  const [connections, setConnections] = useState<readonly ProviderConnection[]>([])
  const [editing, setEditing] = useState<FoodPackage | null>(null)
  const [visibility, setVisibility] = useState<FoodPackage | null>(null)
  const [generation, setGeneration] = useState<FoodPackage | null>(null)
  const [generationScope, setGenerationScope] = useState<ReadonlySet<string>>(new Set())
  const [allowRemote, setAllowRemote] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<FoodPackage | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = async (): Promise<void> => {
    try {
      const [foods, providers] = await Promise.all([ownerFoods(), ownerProviderConnections()])
      setCatalog(foods)
      setConnections(providers.filter((item) => item.enabled && !item.archived))
      setError(null)
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.load"))
    }
  }
  useEffect(() => { void load() }, [])
  const modelOptions = useMemo<readonly SelectFieldOption[]>(() => {
    if (!catalog) return []
    return catalog.eligible_models.map((model) => ({
      label: `${model.display_name}${model.local ? t("foodPackages.labels.localSuffix") : ""}`,
      value: model.reference,
    }))
  }, [catalog, t])

  const save = async (food: FoodPackage): Promise<void> => {
    try {
      await editFood(food.key, {
        display_name: food.display_name,
        enabled: food.enabled,
        roles: food.roles,
      }, csrfToken)
      setEditing(null)
      setNotice(t("foodPackages.notices.saved", { name: food.display_name }))
      await load()
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
      throw reason
    }
  }
  const add = async (): Promise<void> => {
    setPending(true)
    try {
      const result = await createFood(t("foodPackages.values.newName"), csrfToken)
      setCatalog(result.catalog)
      setEditing(result.food)
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally { setPending(false) }
  }
  const generate = async (): Promise<void> => {
    if (!generation) return
    setPending(true)
    try {
      const preview = await previewFoodUpdate(
        generation.key,
        [...generationScope],
        generation.system_role === "emergency",
        allowRemote,
        csrfToken,
      )
      const candidate = {
        ...generation,
        display_name: preview.candidate.display_name,
        enabled: preview.candidate.enabled,
        roles: preview.candidate.roles,
      }
      setEditing(candidate)
      setGeneration(null)
      setNotice(t("foodPackages.notices.generated", { count: preview.changes.filter((item) => item.old_model !== item.new_model).length, warning: preview.warnings[0] ?? "" }))
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally { setPending(false) }
  }
  const lifecycle = async (food: FoodPackage, action: "enable" | "disable" | "archive" | "restore"): Promise<void> => {
    setPending(true)
    try {
      await changeFoodLifecycle(food.key, action, csrfToken)
      await load()
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally { setPending(false) }
  }
  const remove = async (): Promise<void> => {
    if (!deleteTarget) return
    setPending(true)
    try {
      setCatalog(await deleteFood(deleteTarget.key, csrfToken))
      setDeleteTarget(null)
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.delete"))
    } finally { setPending(false) }
  }

  return <section className="manage-card manage-card--wide food-page">
    <div className="manage-head">
      <div className="manage-actions"><Button disabled={pending} onClick={() => { void add() }} type="button"><Plus aria-hidden="true" />{t("foodPackages.actions.add")}</Button><RefreshButton disabled={pending} label={t("foodPackages.actions.refresh")} onClick={() => { void load() }} /></div>
    </div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.load")} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <Table aria-label={t("foodPackages.title")}>
      <TableHeader><TableRow><TableHead>{t("foodPackages.columns.food")}</TableHead><TableHead>{t("foodPackages.columns.locality")}</TableHead><TableHead>{t("foodPackages.columns.primary")}</TableHead><TableHead>{t("foodPackages.columns.visibility")}</TableHead><TableHead>{t("foodPackages.columns.status")}</TableHead><TableHead>{t("foodPackages.columns.actions")}</TableHead></TableRow></TableHeader>
      <TableBody>{catalog?.packages.map((food) => <Fragment key={food.key}>
        <TableRow>
          <TableHead scope="row"><strong>{food.display_name}</strong><small>{t(food.system_role === "emergency" ? "foodPackages.systemRole.emergency" : food.system_role === "common" ? "foodPackages.systemRole.common" : "foodPackages.systemRole.custom")}</small></TableHead>
          <TableCell>{t(localityKey(food.locality))}</TableCell>
          <TableCell>{food.roles.primary?.model ?? t("foodPackages.values.notConfigured")}<small>{food.roles.reasoning?.model ? t("foodPackages.labels.reasoning", { model: food.roles.reasoning.model }) : ""}</small></TableCell>
          <TableCell>{t(food.system_role ? "foodPackages.values.allUsers" : "foodPackages.values.customUsers")}</TableCell>
          <TableCell><span className={`status-badge status-badge--${food.health}`}>{food.health}</span></TableCell>
          <TableCell><div className="manage-actions">
            <Button onClick={() => setEditing(food)} type="button" variant="outline">{t("foodPackages.actions.edit")}</Button>
            <Button onClick={() => { setGeneration(food); setGenerationScope(new Set(connections.map((item) => item.connection_id))); setAllowRemote(food.system_role !== "emergency") }} type="button" variant="outline">{t("foodPackages.actions.generate")}</Button>
            {!food.system_role ? <Button aria-label={t("foodPackages.labels.visibility", { name: food.display_name })} onClick={() => setVisibility(food)} title={t("foodPackages.columns.visibility")} type="button" variant="outline"><Users aria-hidden="true" /></Button> : null}
            {food.archived
              ? <Button onClick={() => { void lifecycle(food, "restore") }} type="button" variant="outline">{t("foodPackages.actions.restore")}</Button>
              : food.enabled
                ? <Button onClick={() => { void lifecycle(food, "disable") }} type="button" variant="outline">{t("foodPackages.actions.disable")}</Button>
                : <Button onClick={() => { void lifecycle(food, "enable") }} type="button" variant="outline">{t("foodPackages.actions.enable")}</Button>}
            {!food.system_role && !food.archived ? <Button onClick={() => { void lifecycle(food, "archive") }} type="button" variant="outline">{t("foodPackages.actions.archive")}</Button> : null}
            {!food.system_role && food.archived ? <Button onClick={() => setDeleteTarget(food)} type="button" variant="outline">{t("foodPackages.actions.delete")}</Button> : null}
          </div></TableCell>
        </TableRow>
        <TableRow><TableCell colSpan={6}>{editing?.key === food.key
          ? <FoodRecipeEditor food={editing} modelOptions={modelOptions} onCancel={() => setEditing(null)} onSave={save} />
          : <FoodRoleTable food={food} />}</TableCell></TableRow>
      </Fragment>)}</TableBody>
    </Table>
    {generation ? <ManageDialog onOpenChange={(open) => { if (!open) setGeneration(null) }} open title={t("foodPackages.generation.title", { name: generation.display_name })}>
      <div className="food-visibility-list">{connections.map((connection) => <label className="food-visibility-row" key={connection.connection_id}><Checkbox checked={generationScope.has(connection.connection_id)} onCheckedChange={(checked) => setGenerationScope((current) => toggle(current, connection.connection_id, checked === true))} /><span>{connection.alias}</span></label>)}</div>
      {generation.system_role === "emergency" ? <label className="food-visibility-row"><Checkbox checked={allowRemote} onCheckedChange={(checked) => setAllowRemote(checked === true)} /><span>{t("foodPackages.generation.allowRemote")}</span></label> : null}
      <div className="manage-actions"><Button disabled={pending || generationScope.size === 0} onClick={() => { void generate() }} type="button">{t("foodPackages.actions.generateDiff")}</Button><Button onClick={() => setGeneration(null)} type="button" variant="outline">{t("foodPackages.actions.cancel")}</Button></div>
    </ManageDialog> : null}
    {visibility ? <FoodVisibilityDialog csrfToken={csrfToken} food={visibility} onClose={() => setVisibility(null)} onSaved={() => { setNotice(t("foodPackages.notices.visibilitySaved")) }} /> : null}
    <ConfirmDialog confirmLabel={t("foodPackages.delete.confirm")} danger description={t("foodPackages.delete.description")} onConfirm={() => { void remove() }} onOpenChange={(open) => { if (!open) setDeleteTarget(null) }} open={deleteTarget !== null} pending={pending} title={t("foodPackages.delete.title")} />
  </section>
}

function toggle(current: ReadonlySet<string>, key: string, enabled: boolean): ReadonlySet<string> {
  const next = new Set(current)
  if (enabled) next.add(key)
  else next.delete(key)
  return next
}

function localityKey(value: string): "foodPackages.locality.local" | "foodPackages.locality.mixed" | "foodPackages.locality.remote" | "foodPackages.locality.unknown" {
  return value === "local" ? "foodPackages.locality.local" : value === "remote" ? "foodPackages.locality.remote" : value === "mixed" ? "foodPackages.locality.mixed" : "foodPackages.locality.unknown"
}
