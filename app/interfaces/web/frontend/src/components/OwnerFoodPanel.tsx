import { Button } from "@/components/ui/button"
import { Plus } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"

import {
  changeFoodLifecycle,
  deleteFood,
  editFood,
  ownerFoods,
  type FoodCatalog,
  type FoodPackage,
} from "../api/admin/food-packages"
import { ownerProviderConnections, type ProviderConnection } from "../api/owner-providers"
import { ownerOllamaStatus, type OllamaStatus } from "../api/owner-ollama"
import { ownerUsers, type OwnerUser } from "../api/owner-users"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { ConfirmDialog } from "./ConfirmDialog"
import { FoodGenerationDialog } from "./FoodGenerationDialog"
import { FoodOperationMenu, type FoodLifecycleAction } from "./FoodOperationMenu"
import { FoodRecipeEditor } from "./FoodRecipeEditor"
import { projectFoodDisplay, type FoodModelCell } from "./food-display"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { RefreshButton } from "./RefreshButton"
import type { SelectFieldOption } from "./SelectField"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table"
import { useToast } from "./ui/toast"

type GenerationState = { readonly food: FoodPackage | null; readonly mode: "create" | "update" }
const FOOD_ROLES = ["primary", "reasoning", "vision", "tool", "fallback"] as const

export function OwnerFoodPanel({ csrfToken }: { readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [catalog, setCatalog] = useState<FoodCatalog | null>(null)
  const [connections, setConnections] = useState<readonly ProviderConnection[]>([])
  const [connectionsLoading, setConnectionsLoading] = useState(true)
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus | null>(null)
  const [users, setUsers] = useState<readonly OwnerUser[]>([])
  const [generation, setGeneration] = useState<GenerationState | null>(null)
  const [editing, setEditing] = useState<FoodPackage | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<FoodPackage | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const { show } = useToast()

  const load = async (isActive: () => boolean = () => true): Promise<void> => {
    if (!isActive()) return
    setConnectionsLoading(true)
    try {
      const [foods, providers, allUsers] = await Promise.all([
        ownerFoods(),
        ownerProviderConnections(),
        ownerUsers(),
      ])
      if (!isActive()) return
      const ollamaResult = providers.some((connection) => connection.catalog_id === "ollama")
        ? (await Promise.allSettled([ownerOllamaStatus()]))[0]
        : undefined
      setCatalog(foods)
      setConnections(providers)
      setOllamaStatus(ollamaResult?.status === "fulfilled" ? ollamaResult.value : null)
      setUsers(allUsers.filter((user) => user.role === "user"))
      setError(null)
    } catch (reason: unknown) {
      if (!isActive()) return
      setError(describeApiError(reason, "manage.load"))
    } finally {
      if (isActive()) setConnectionsLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    void load(() => active)
    return () => { active = false }
  }, [])

  const availableConnections = useMemo(
    () => {
      const eligibleConnectionIds = new Set((catalog?.eligible_models ?? []).map((model) => model.reference.split("/", 1)[0]))
      return connections.filter((connection) => connection.enabled && !connection.archived && eligibleConnectionIds.has(connection.connection_id))
    },
    [catalog, connections],
  )
  const modelOptions = useMemo<readonly SelectFieldOption[]>(() => catalog?.eligible_models.map((model) => ({
    label: modelOptionLabel(model.reference, model.display_name, model.local, connections, t("foodPackages.labels.localSuffix")),
    value: model.reference,
  })) ?? [], [catalog, connections, t])
  const localConnectionIds = useMemo(
    () => availableConnections.filter((connection) => connection.catalog_id === "ollama").map((connection) => connection.connection_id),
    [availableConnections],
  )

  const manualSave = async (food: FoodPackage): Promise<void> => {
    setPending(true)
    try {
      await editFood(food.key, {
        display_name: food.display_name,
        enabled: food.enabled,
        roles: food.roles,
        visibility_mode: food.system_role ? "global" : food.visibility_mode,
        visible_user_ids: food.system_role ? [] : food.visible_user_ids,
      }, csrfToken)
      setEditing(null)
      show({ kind: "success", message: t("foodPackages.notices.saved", { name: food.display_name }) })
      await load()
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(false)
    }
  }

  const lifecycle = async (food: FoodPackage, action: FoodLifecycleAction): Promise<void> => {
    setPending(true)
    try {
      await changeFoodLifecycle(food.key, action, csrfToken)
      await load()
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(false)
    }
  }

  const remove = async (): Promise<void> => {
    if (!deleteTarget) return
    setPending(true)
    try {
      setCatalog(await deleteFood(deleteTarget.key, csrfToken))
      setDeleteTarget(null)
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.delete"))
    } finally {
      setPending(false)
    }
  }

  const openGeneration = (food: FoodPackage | null): void => {
    setGeneration({ mode: food ? "update" : "create", food })
  }

  return <section className="manage-card manage-card--wide food-page">
    <div className="manage-head">
      <div className="manage-actions">
        <Button disabled={pending} onClick={() => openGeneration(null)} type="button"><Plus aria-hidden="true" />{t("foodPackages.actions.add")}</Button>
        <RefreshButton disabled={pending} label={t("foodPackages.actions.refresh")} onClick={() => { void load() }} />
      </div>
    </div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.load")} /> : null}
    <Table aria-label={t("foodPackages.title")} className="food-table">
      <TableHeader>
        <TableRow>
          <TableHead className="food-col--first">{t("foodPackages.columns.food")}</TableHead>
          <TableHead>{t("foodPackages.columns.primary")}</TableHead>
          <TableHead>{t("foodPackages.columns.reasoning")}</TableHead>
          <TableHead>{t("foodPackages.columns.vision")}</TableHead>
          <TableHead>{t("foodPackages.columns.tool")}</TableHead>
          <TableHead>{t("foodPackages.columns.fallback")}</TableHead>
          <TableHead>{t("foodPackages.columns.visibility")}</TableHead>
          <TableHead className="food-col--last">{t("foodPackages.columns.actions")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {catalog?.packages.map((food) => {
          const projection = projectFoodDisplay(food, connections, users.length, ollamaStatus, localConnectionIds)
          return <TableRow className={food.archived ? "food-row--archived" : ""} key={food.key}>
            <TableCell className="food-col--first">
              <strong>{food.display_name}</strong>
              <div className="food-badges">
                {food.system_role ? <small className="food-system-badge">{t("foodPackages.labels.system")}</small> : null}
                {projection.isLocal ? <small className="food-local-badge">{t("foodPackages.labels.local")}</small> : null}
                <span className={`status-badge status-badge--${foodStatusClass(food)}`}>{foodStatusLabel(food, t)}</span>
              </div>
            </TableCell>
            {FOOD_ROLES.map((role) => <TableCell key={role}><FoodModelCellView archived={food.archived} cell={projection.models[role]} t={t} /></TableCell>)}
            <TableCell>{visibilityLabel(projection.visibility, t)}</TableCell>
            <TableCell className="food-col--last">
              <FoodOperationMenu
                archived={food.archived}
                busy={pending}
                enabled={food.enabled}
                system={food.system_role !== null}
                onDelete={() => setDeleteTarget(food)}
                onEdit={() => setEditing(food)}
                onGenerate={() => openGeneration(food)}
                onLifecycle={(action) => { void lifecycle(food, action) }}
              />
            </TableCell>
          </TableRow>
        })}
      </TableBody>
    </Table>
    {generation ? <FoodGenerationDialog
      availableConnections={availableConnections}
      connectionsLoading={connectionsLoading}
      csrfToken={csrfToken}
      food={generation.food}
      mode={generation.mode}
      modelOptions={modelOptions}
      ollamaStatus={ollamaStatus}
      onCreated={async (food) => { show({ kind: "success", message: t("foodPackages.notices.created", { name: food.display_name }) }); await load() }}
      onOpenChange={(open) => { if (!open) setGeneration(null) }}
      onUpdated={async (food) => { show({ kind: "success", message: t(food.enabled ? "foodPackages.notices.updatedEnabled" : "foodPackages.notices.updatedDisabled", { name: food.display_name }) }); await load() }}
      users={users}
    /> : null}
    {editing ? <ManageDialog
      contentClassName="food-recipe-dialog"
      description={t("foodPackages.recipe.description")}
      onOpenChange={(open) => { if (!open) setEditing(null) }}
      open
      title={t("foodPackages.recipe.title", { name: editing.display_name })}
    >
      <FoodRecipeEditor food={editing} modelOptions={modelOptions} onCancel={() => setEditing(null)} onSave={manualSave} users={users} />
    </ManageDialog> : null}
    <ConfirmDialog
      confirmLabel={t("foodPackages.delete.confirm")}
      danger
      description={t("foodPackages.delete.description")}
      onConfirm={() => { void remove() }}
      onOpenChange={(open) => { if (!open) setDeleteTarget(null) }}
      open={deleteTarget !== null}
      pending={pending}
      title={t("foodPackages.delete.title")}
    />
  </section>
}

function FoodModelCellView({ archived, cell, t }: { readonly archived: boolean; readonly cell: FoodModelCell; readonly t: TFunction<"manage"> }) {
  const label = cell.status === "unconfigured" ? t("foodPackages.values.notConfigured") : cell.label
  if (archived || cell.status === "unconfigured") {
    return <span className="food-model-cell food-model-cell--plain">{label}</span>
  }
  return <div className="food-model-cell">
    <span className={`food-model-cell__dot food-model-cell__dot--${cell.status}`} aria-hidden="true" />
    <span className="food-model-cell__label">{cell.label}</span>
    <small>{t(cell.local && cell.status === "available" ? "foodPackages.modelStatus.localAvailable" : `foodPackages.modelStatus.${cell.status}`)}{cell.latencyLabel ? ` · ${cell.latencyLabel}` : ""}</small>
  </div>
}

function foodStatusClass(food: FoodPackage): "disabled" | "archived" | "passed" | "warning" | "failed" | "unverified" {
  if (food.archived) return "archived"
  if (!food.enabled) return "disabled"
  if (food.health === "healthy") return "passed"
  if (food.health === "degraded") return "warning"
  if (food.health === "unavailable") return "failed"
  return "unverified"
}

function foodStatusLabel(food: FoodPackage, t: TFunction<"manage">): string {
  if (food.archived) return t("foodPackages.values.archived")
  if (!food.enabled) return t("foodPackages.values.stopped")
  if (food.health === "healthy") return t("foodPackages.values.healthy")
  if (food.health === "degraded") return t("foodPackages.values.degraded")
  if (food.health === "unavailable") return t("foodPackages.values.unavailable")
  return t("foodPackages.values.pending")
}

function visibilityLabel(
  visibility: ReturnType<typeof projectFoodDisplay>["visibility"],
  t: TFunction<"manage">,
): string {
  if (visibility.kind === "all") return t("foodPackages.values.allUsers")
  if (visibility.kind === "users") {
    return visibility.allCurrentUsers
      ? t("foodPackages.values.selectedCurrentUsers", { count: visibility.count })
      : t("foodPackages.values.selectedUsers", { count: visibility.count })
  }
  return t("foodPackages.values.visibilityError")
}

function modelOptionLabel(
  reference: string,
  displayName: string | null,
  local: boolean,
  connections: readonly ProviderConnection[],
  localSuffix: string,
): string {
  const separator = reference.indexOf("/")
  const connectionId = separator >= 0 ? reference.slice(0, separator) : ""
  const modelId = separator >= 0 ? reference.slice(separator + 1) : reference
  const connection = connections.find((item) => item.connection_id === connectionId)
  const model = connection?.models.find((item) => item.id === modelId)
  const label = connection && model
    ? `${connection.alias} / ${model.display_name}`
    : displayName ?? modelId
  return local ? `${label}${localSuffix}` : label
}
