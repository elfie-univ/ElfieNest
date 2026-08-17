import { Button } from "@/components/ui/button"
import { ArrowRight } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"

import {
  createFood,
  editFood,
  previewFoodUpdate,
  previewNewFood,
  type FoodPackage,
  type FoodPreview,
} from "../api/admin/food-packages"
import type { ProviderConnection } from "../api/owner-providers"
import type { OllamaStatus } from "../api/owner-ollama"
import type { OwnerUser } from "../api/owner-users"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { FoodSourceSelect, FoodVisibilitySelect } from "./FoodScopeSelect"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { SelectField, type SelectFieldOption } from "./SelectField"
import { TextField } from "./TextField"

const NONE = "__none__"
const ROLES = ["primary", "reasoning", "vision", "tool", "fallback"] as const
type FoodRole = (typeof ROLES)[number]
type ScopePopover = "sources" | "visibility" | null

type FoodGenerationDialogProps = {
  readonly availableConnections: readonly ProviderConnection[]
  readonly connectionsLoading: boolean
  readonly csrfToken: string
  readonly food: FoodPackage | null
  readonly mode: "create" | "update"
  readonly modelOptions: readonly SelectFieldOption[]
  readonly ollamaStatus: OllamaStatus | null
  readonly onCreated: (food: FoodPackage) => Promise<void>
  readonly onOpenChange: (open: boolean) => void
  readonly onUpdated: (food: FoodPackage) => Promise<void>
  readonly users: readonly OwnerUser[]
}

export function FoodGenerationDialog({ availableConnections, connectionsLoading, csrfToken, food, mode, modelOptions, ollamaStatus, onCreated, onOpenChange, onUpdated, users }: FoodGenerationDialogProps) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [displayName, setDisplayName] = useState(food?.display_name ?? "")
  const [scope, setScope] = useState<ReadonlySet<string>>(new Set())
  const [visibilityMode, setVisibilityMode] = useState<FoodPackage["visibility_mode"]>("global")
  const [selectedUsers, setSelectedUsers] = useState<ReadonlySet<number>>(new Set())
  const [preview, setPreview] = useState<FoodPreview | null>(null)
  const [draftRoles, setDraftRoles] = useState<FoodPackage["roles"]>(food?.roles ?? emptyRoles())
  const [openScope, setOpenScope] = useState<ScopePopover>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const localConnectionIds = useMemo(
    () => new Set(availableConnections.filter((connection) => connection.catalog_id === "ollama").map((connection) => connection.connection_id)),
    [availableConnections],
  )
  const usableLocal = ollamaStatus?.state === "healthy"
    && (ollamaStatus.models.length === 0 || ollamaStatus.models.some((model) => model.installed && model.available !== false))

  useEffect(() => {
    setDisplayName(food?.display_name ?? "")
    setScope(defaultScope(availableConnections, food, mode, localConnectionIds, usableLocal))
    setVisibilityMode(food && !food.system_role ? food.visibility_mode : "global")
    setSelectedUsers(new Set(food && !food.system_role ? food.visible_user_ids : []))
    setPreview(null)
    setDraftRoles(food?.roles ?? emptyRoles())
    setOpenScope(null)
    setError(null)
  }, [availableConnections, food, localConnectionIds, mode, usableLocal])

  const sourceOptions = useMemo(
    () => availableConnections.map((connection) => ({ value: connection.connection_id, label: connection.alias })),
    [availableConnections],
  )
  const userOptions = useMemo(
    () => users.map((user) => ({ user_id: user.user_id, label: user.display_name ?? user.account_id })),
    [users],
  )
  const modelSelectOptions = useMemo(
    () => [{ label: t("foodPackages.recipe.none"), value: NONE }, ...modelOptions],
    [modelOptions, t],
  )
  const sourceSummary = summarizeSources(scope, sourceOptions, connectionsLoading, t)
  const visibilitySummary = summarizeVisibility(visibilityMode, selectedUsers, userOptions, t)
  const sourceChecked = selectionState(scope.size, sourceOptions.length)

  const generate = async (): Promise<void> => {
    if (!displayName.trim() || scope.size === 0 || (visibilityMode === "users" && selectedUsers.size === 0)) return
    setPending(true)
    try {
      const hasLocal = [...scope].some((connectionId) => localConnectionIds.has(connectionId))
      const hasRemote = [...scope].some((connectionId) => !localConnectionIds.has(connectionId))
      const allowRemote = hasRemote
      const localFirst = hasLocal && (food?.system_role === "emergency" || !hasRemote)
      const result = mode === "create"
        ? await previewNewFood(displayName.trim(), [...scope], localFirst, allowRemote, visibilityMode, [...selectedUsers], csrfToken)
        : await previewFoodUpdate(food?.key ?? "", [...scope], localFirst, allowRemote, visibilityMode, [...selectedUsers], csrfToken)
      setPreview(result)
      setDraftRoles(result.candidate.roles)
      setError(null)
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(false)
    }
  }

  const save = async (enable: boolean = food?.enabled ?? true): Promise<void> => {
    if (!preview || !displayName.trim() || !draftRoles.primary || (visibilityMode === "users" && selectedUsers.size === 0)) return
    setPending(true)
    try {
      const draft = {
        display_name: mode === "create" || !food?.system_role ? displayName.trim() : food.display_name,
        enabled: enable,
        roles: draftRoles,
        visibility_mode: food?.system_role ? "global" as const : visibilityMode,
        visible_user_ids: food?.system_role ? [] : [...selectedUsers],
      }
      if (mode === "create") {
        const result = await createFood(draft, csrfToken)
        await onCreated(result.food)
      } else if (food) {
        const result = await editFood(food.key, draft, csrfToken)
        await onUpdated(result.food)
      }
      onOpenChange(false)
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(false)
    }
  }

  const setRole = (role: FoodRole, value: string): void => {
    setDraftRoles((current) => ({ ...current, [role]: value === NONE ? null : { model: value } }))
  }

  return <ManageDialog
    contentClassName="food-generation-dialog"
    description={t(mode === "create" ? "foodPackages.generation.createDescription" : "foodPackages.generation.description")}
    onOpenChange={onOpenChange}
    open
    title={t(mode === "create" ? "foodPackages.generation.createTitle" : "foodPackages.generation.title", { name: food?.display_name ?? "" })}
  >
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.load")} /> : null}
    {mode === "create" || !food?.system_role
      ? <TextField label={t("foodPackages.generation.name")} onChange={(value) => { setDisplayName(value); setPreview(null) }} value={displayName} />
      : null}
    <div className="food-generation-scopes">
      <div className="food-generation-scope-row">
        <span className="food-generation-scope-row__label">{t("foodPackages.generation.sources")}</span>
        <FoodSourceSelect
          ariaLabel={t("foodPackages.generation.sources")}
          disabled={pending || connectionsLoading || sourceOptions.length === 0}
          label={t("foodPackages.generation.sources")}
          masterChecked={sourceChecked}
          masterLabel={t("foodPackages.generation.allSources")}
          onMasterChange={(checked) => { setScope(new Set(checked ? sourceOptions.map((option) => option.value) : [])); setPreview(null) }}
          onOpenChange={(open) => setOpenScope((current) => open ? "sources" : current === "sources" ? null : current)}
          onToggle={(value, checked) => { setScope((current) => toggle(current, value, checked)); setPreview(null) }}
          open={openScope === "sources"}
          options={sourceOptions}
          selected={scope}
          summary={sourceSummary}
        />
      </div>
      {!food?.system_role ? <div className="food-generation-scope-row">
        <span className="food-generation-scope-row__label">{t("foodPackages.columns.visibility")}</span>
        <FoodVisibilitySelect
          ariaLabel={t("foodPackages.columns.visibility")}
          disabled={pending}
          globalLabel={t("foodPackages.visibilityModes.global")}
          label={t("foodPackages.columns.visibility")}
          mode={visibilityMode}
          onModeChange={(nextMode) => { setVisibilityMode(nextMode); if (nextMode === "global") setSelectedUsers(new Set()) }}
          onOpenChange={(open) => setOpenScope((current) => open ? "visibility" : current === "visibility" ? null : current)}
          onToggleUser={(userId, checked) => setSelectedUsers((current) => toggleNumber(current, userId, checked))}
          open={openScope === "visibility"}
          selectedUserIds={selectedUsers}
          searchLabel={t("foodPackages.visibilityModes.searchUsers")}
          summary={visibilitySummary}
          emptySearchLabel={t("foodPackages.visibilityModes.noUsersFound")}
          userLabel={t("foodPackages.visibilityModes.users")}
          users={userOptions}
        />
      </div> : null}
    </div>
    {preview ? <section className="food-generation-preview" aria-label={t("foodPackages.generation.previewTitle")}>
      <h3>{t("foodPackages.generation.previewTitle")}</h3>
      <div className="food-diff-scroll"><div className="food-diff-list">{ROLES.map((role) => {
        const change = preview.changes.find((item) => item.role === role)
        const oldModel = change?.old_model ?? food?.roles[role]?.model ?? null
        const currentModel = draftRoles[role]?.model ?? null
        const changed = oldModel !== currentModel
        const oldModelLabel = displayModel(oldModel, modelOptions, t("foodPackages.values.notConfigured"))
        return <div className={`food-diff-row${changed ? " food-diff-row--changed" : ""}`} key={role}>
          <strong>{t(`foodPackages.roles.${role}`)}</strong>
          <span title={oldModelLabel}>{oldModelLabel}</span>
          <ArrowRight aria-hidden="true" size={15} />
          <SelectField label={t(`foodPackages.roles.${role}`)} onValueChange={(value) => setRole(role, value)} options={modelSelectOptions} value={draftRoles[role]?.model ?? NONE} />
        </div>
      })}</div></div>
    </section> : null}
    <div className="manage-actions">
      {!preview
        ? <Button disabled={pending || connectionsLoading || !displayName.trim() || scope.size === 0 || (visibilityMode === "users" && selectedUsers.size === 0)} onClick={() => { void generate() }} type="button">{pending ? t("foodPackages.actions.generating") : t("foodPackages.actions.generatePreview")}</Button>
        : mode === "update" && food && !food.enabled
          ? <>
            <Button disabled={pending || !draftRoles.primary || (visibilityMode === "users" && selectedUsers.size === 0)} onClick={() => { void save(true) }} type="button">{pending ? t("foodPackages.actions.saving") : t("foodPackages.actions.applyAndEnable")}</Button>
            <Button disabled={pending || !draftRoles.primary || (visibilityMode === "users" && selectedUsers.size === 0)} onClick={() => { void save(false) }} type="button" variant="outline">{t("foodPackages.actions.saveKeepDisabled")}</Button>
          </>
          : <Button disabled={pending || !draftRoles.primary || (visibilityMode === "users" && selectedUsers.size === 0)} onClick={() => { void save() }} type="button">{pending ? t("foodPackages.actions.saving") : t(mode === "create" ? "foodPackages.actions.saveCreate" : "foodPackages.actions.applyUpdate")}</Button>}
      <Button disabled={pending} onClick={() => onOpenChange(false)} type="button" variant="outline">{t("foodPackages.actions.cancel")}</Button>
    </div>
  </ManageDialog>
}

function emptyRoles(): FoodPackage["roles"] {
  return { primary: null, reasoning: null, vision: null, tool: null, fallback: null }
}

function defaultScope(
  connections: readonly ProviderConnection[],
  food: FoodPackage | null,
  mode: "create" | "update",
  localConnectionIds: ReadonlySet<string>,
  usableLocal: boolean,
): Set<string> {
  const connectionIds = connections.map((connection) => connection.connection_id)
  if (food?.system_role === "emergency") {
    return usableLocal
      ? new Set(connectionIds.filter((connectionId) => localConnectionIds.has(connectionId)))
      : new Set()
  }
  if (mode === "update" && food?.system_role === null) {
    const currentIds = new Set(
      Object.values(food.roles).flatMap((assignment) => assignment ? [assignment.model.split("/", 1)[0]] : []),
    )
    const currentAvailable = connectionIds.filter((connectionId) => currentIds.has(connectionId))
    if (currentAvailable.length > 0) return new Set(currentAvailable)
  }
  return new Set(connectionIds.filter((connectionId) => !localConnectionIds.has(connectionId)))
}

function displayModel(reference: string | null | undefined, options: readonly SelectFieldOption[], none: string): string {
  if (!reference) return none
  const option = options.find((item) => "value" in item && item.value === reference)
  return option && "value" in option ? option.label : reference
}

function selectionState(selectedCount: number, optionCount: number): boolean | "indeterminate" {
  if (selectedCount === 0 || optionCount === 0) return false
  return selectedCount === optionCount ? true : "indeterminate"
}

function summarizeSources(
  selected: ReadonlySet<string>,
  options: readonly { readonly value: string; readonly label: string }[],
  loading: boolean,
  t: TFunction<"manage">,
): string {
  if (loading) return t("foodPackages.sourceStates.loading")
  if (options.length === 0) return t("foodPackages.sourceStates.empty")
  if (selected.size === 0) return t("foodPackages.sourceStates.none")
  if (selected.size === options.length) return t("foodPackages.sourceStates.all", { count: options.length })
  const labels = options.filter((option) => selected.has(option.value)).map((option) => option.label)
  if (labels.length <= 2) return labels.join("、")
  return t("foodPackages.sourceStates.partial", { names: labels.slice(0, 2).join("、"), more: labels.length - 2 })
}

function summarizeVisibility(
  mode: FoodPackage["visibility_mode"],
  selected: ReadonlySet<number>,
  users: readonly { readonly user_id: number; readonly label: string }[],
  t: TFunction<"manage">,
): string {
  if (mode === "global") return t("foodPackages.visibilityStates.global")
  if (selected.size === 0) return t("foodPackages.visibilityStates.none")
  if (selected.size === users.length && users.length > 0) return t("foodPackages.visibilityStates.allCurrent", { count: selected.size })
  const labels = users.filter((user) => selected.has(user.user_id)).map((user) => user.label)
  if (labels.length === 1) return t("foodPackages.visibilityStates.one", { name: labels[0] ?? "" })
  if (labels.length === 2) return labels.join("、")
  return t("foodPackages.visibilityStates.partial", { names: labels.slice(0, 2).join("、"), more: labels.length - 2 })
}

function toggle(current: ReadonlySet<string>, value: string, enabled: boolean): ReadonlySet<string> {
  const next = new Set(current)
  if (enabled) next.add(value)
  else next.delete(value)
  return next
}

function toggleNumber(current: ReadonlySet<number>, value: number, enabled: boolean): ReadonlySet<number> {
  const next = new Set(current)
  if (enabled) next.add(value)
  else next.delete(value)
  return next
}
