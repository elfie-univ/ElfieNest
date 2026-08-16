import { Button } from "@/components/ui/button"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import type { FoodPackage } from "../api/admin/food-packages"
import type { OwnerUser } from "../api/owner-users"
import { FoodVisibilitySelect } from "./FoodScopeSelect"
import { SelectField, type SelectFieldOption } from "./SelectField"
import { TextField } from "./TextField"

const NONE = "__none__"

export function FoodRecipeEditor({ food, modelOptions, onCancel, onSave, users }: {
  readonly food: FoodPackage
  readonly modelOptions: readonly SelectFieldOption[]
  readonly onCancel: () => void
  readonly onSave: (food: FoodPackage) => Promise<void>
  readonly users: readonly OwnerUser[]
}) {
  const { t } = useTranslation("manage")
  const [draft, setDraft] = useState(food)
  const [scopeOpen, setScopeOpen] = useState(false)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    setDraft(food)
    setScopeOpen(false)
  }, [food])

  const options = useMemo(() => [{ label: t("foodPackages.recipe.none"), value: NONE }, ...modelOptions], [modelOptions, t])
  const userOptions = useMemo(
    () => users.map((user) => ({ user_id: user.user_id, label: user.display_name ?? user.account_id })),
    [users],
  )
  const visibilitySummary = draft.visibility_mode === "global"
    ? t("foodPackages.visibilityStates.global")
    : draft.visible_user_ids.length === 0
      ? t("foodPackages.visibilityStates.none")
      : draft.visible_user_ids.length === userOptions.length
        ? t("foodPackages.visibilityStates.allCurrent", { count: draft.visible_user_ids.length })
        : t("foodPackages.visibilityStates.selectedCount", { count: draft.visible_user_ids.length })

  const setRole = (role: "primary" | "reasoning" | "vision" | "tool" | "fallback", value: string): void => {
    setDraft((current) => ({
      ...current,
      roles: { ...current.roles, [role]: value === NONE ? null : { model: value } },
    }))
  }
  const toggleRequiredRole = (role: "reasoning" | "vision" | "tool", enabled: boolean): void => {
    setDraft((current) => {
      const required = new Set(current.required_roles ?? [])
      if (enabled) required.add(role)
      else required.delete(role)
      return { ...current, required_roles: [...required].sort() }
    })
  }
  const submit = async (): Promise<void> => {
    if (draft.visibility_mode === "users" && draft.visible_user_ids.length === 0) return
    setPending(true)
    try {
      await onSave(draft)
    } finally {
      setPending(false)
    }
  }

  return <div className="food-recipe-editor">
    <TextField label={t("foodPackages.recipe.name")} onChange={(display_name) => setDraft((current) => ({ ...current, display_name }))} value={draft.display_name} />
    {([
      ["primary", t("foodPackages.roles.primary")],
      ["reasoning", t("foodPackages.roles.reasoning")],
      ["vision", t("foodPackages.roles.vision")],
      ["tool", t("foodPackages.roles.tool")],
      ["fallback", t("foodPackages.roles.fallback")],
    ] as const).map(([role, label]) => <SelectField
      key={role}
      label={label}
      onValueChange={(value) => setRole(role, value)}
      options={options}
      value={draft.roles[role]?.model ?? NONE}
    />)}
    <fieldset className="food-required-roles">
      <legend>{t("foodPackages.roles.requiredOptional")}</legend>
      {([
        ["reasoning", t("foodPackages.roles.reasoning")],
        ["vision", t("foodPackages.roles.vision")],
        ["tool", t("foodPackages.roles.tool")],
      ] as const).map(([role, label]) => <label key={role}>
        <input checked={(draft.required_roles ?? []).includes(role)} onChange={(event) => toggleRequiredRole(role, event.target.checked)} type="checkbox" />
        <span>{label}</span>
      </label>)}
    </fieldset>
    {!food.system_role ? <div className="food-recipe-visibility">
      <span className="food-generation-scope-row__label">{t("foodPackages.columns.visibility")}</span>
      <FoodVisibilitySelect
        ariaLabel={t("foodPackages.columns.visibility")}
        disabled={pending}
        globalLabel={t("foodPackages.visibilityModes.global")}
        label={t("foodPackages.columns.visibility")}
        mode={draft.visibility_mode}
        onModeChange={(mode) => setDraft((current) => ({ ...current, visibility_mode: mode, visible_user_ids: mode === "global" ? [] : current.visible_user_ids }))}
        onOpenChange={setScopeOpen}
        onToggleUser={(userId, checked) => setDraft((current) => ({ ...current, visible_user_ids: toggleUser(current.visible_user_ids, userId, checked) }))}
        open={scopeOpen}
        selectedUserIds={new Set(draft.visible_user_ids)}
        searchLabel={t("foodPackages.visibilityModes.searchUsers")}
        summary={visibilitySummary}
        emptySearchLabel={t("foodPackages.visibilityModes.noUsersFound")}
        userLabel={t("foodPackages.visibilityModes.users")}
        users={userOptions}
      />
    </div> : null}
    <div className="manage-actions">
      <Button disabled={pending || !draft.roles.primary || (draft.visibility_mode === "users" && draft.visible_user_ids.length === 0)} onClick={() => { void submit() }} type="button">{t("foodPackages.actions.save")}</Button>
      <Button disabled={pending} onClick={onCancel} type="button" variant="outline">{t("foodPackages.actions.cancel")}</Button>
    </div>
  </div>
}

function toggleUser(current: readonly number[], userId: number, enabled: boolean): number[] {
  const next = new Set(current)
  if (enabled) next.add(userId)
  else next.delete(userId)
  return [...next].sort((left, right) => left - right)
}
