import { Check, ChevronDown } from "lucide-react"
import { Popover } from "radix-ui"
import { useEffect, useMemo, useState, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"

import type { FoodPackage } from "../api/admin/food-packages"

export type FoodScopeOption = {
  readonly value: string
  readonly label: string
}

type FoodSourceSelectProps = {
  readonly ariaLabel: string
  readonly disabled?: boolean
  readonly label: string
  readonly masterChecked: boolean | "indeterminate"
  readonly masterLabel: string
  readonly onMasterChange: (checked: boolean) => void
  readonly onOpenChange: (open: boolean) => void
  readonly onToggle: (value: string, checked: boolean) => void
  readonly open: boolean
  readonly options: readonly FoodScopeOption[]
  readonly selected: ReadonlySet<string>
  readonly summary: string
}

export function FoodSourceSelect({
  ariaLabel,
  disabled = false,
  label,
  masterChecked,
  masterLabel,
  onMasterChange,
  onOpenChange,
  onToggle,
  open,
  options,
  selected,
  summary,
}: FoodSourceSelectProps) {
  return <FoodScopePopover ariaLabel={ariaLabel} disabled={disabled} label={label} onOpenChange={onOpenChange} open={open} popoverClassName="food-scope-popover--source" summary={summary}>
    <div className="food-scope-popover__options" role="group" aria-label={ariaLabel}>
      <label className="food-scope-option food-scope-option--all">
        <Checkbox aria-label={masterLabel} checked={masterChecked} disabled={disabled} onCheckedChange={(checked) => onMasterChange(masterChecked === "indeterminate" ? false : checked === true)} />
        <span>{masterLabel}</span>
      </label>
      {options.map((option) => <label className="food-scope-option" key={option.value}>
        <Checkbox checked={selected.has(option.value)} disabled={disabled} onCheckedChange={(checked) => onToggle(option.value, checked === true)} />
        <span>{option.label}</span>
      </label>)}
    </div>
  </FoodScopePopover>
}

type FoodVisibilitySelectProps = {
  readonly ariaLabel: string
  readonly disabled?: boolean
  readonly globalLabel: string
  readonly label: string
  readonly mode: FoodPackage["visibility_mode"]
  readonly onModeChange: (mode: FoodPackage["visibility_mode"]) => void
  readonly onOpenChange: (open: boolean) => void
  readonly onToggleUser: (userId: number, checked: boolean) => void
  readonly open: boolean
  readonly selectedUserIds: ReadonlySet<number>
  readonly searchLabel: string
  readonly summary: string
  readonly emptySearchLabel: string
  readonly userLabel: string
  readonly users: readonly { readonly user_id: number; readonly label: string }[]
}

export function FoodVisibilitySelect({
  ariaLabel,
  disabled = false,
  globalLabel,
  label,
  mode,
  onModeChange,
  onOpenChange,
  onToggleUser,
  open,
  selectedUserIds,
  searchLabel,
  summary,
  emptySearchLabel,
  userLabel,
  users,
}: FoodVisibilitySelectProps) {
  const [searchQuery, setSearchQuery] = useState("")
  const filteredUsers = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase()
    return normalizedQuery.length === 0 ? users : users.filter((user) => user.label.toLowerCase().includes(normalizedQuery))
  }, [searchQuery, users])

  useEffect(() => {
    if (!open) setSearchQuery("")
  }, [open])

  return <FoodScopePopover ariaLabel={ariaLabel} disabled={disabled} label={label} onOpenChange={onOpenChange} open={open} summary={summary}>
    <div aria-label={ariaLabel} className="food-scope-popover__visibility" role="radiogroup">
      <button aria-checked={mode === "global"} className={`food-scope-mode${mode === "global" ? " food-scope-mode--selected" : ""}`} disabled={disabled} onClick={() => onModeChange("global")} role="radio" type="button">
        <span className="food-scope-mode__indicator" aria-hidden="true">{mode === "global" ? <Check size={14} /> : null}</span>
        {globalLabel}
      </button>
      <button aria-checked={mode === "users"} className={`food-scope-mode${mode === "users" ? " food-scope-mode--selected" : ""}`} disabled={disabled} onClick={() => onModeChange("users")} role="radio" type="button">
        <span className="food-scope-mode__indicator" aria-hidden="true">{mode === "users" ? <Check size={14} /> : null}</span>
        {userLabel}
      </button>
    </div>
    {mode === "users" ? <div className="food-scope-popover__users" role="group" aria-label={userLabel}>
      {users.length > 0 ? <>
        <Input aria-label={searchLabel} className="food-scope-user-search" onChange={(event) => setSearchQuery(event.target.value)} placeholder={searchLabel} value={searchQuery} />
        {filteredUsers.length > 0 ? filteredUsers.map((user) => <label className="food-scope-option" key={user.user_id}>
          <Checkbox checked={selectedUserIds.has(user.user_id)} disabled={disabled} onCheckedChange={(checked) => onToggleUser(user.user_id, checked === true)} />
          <span>{user.label}</span>
        </label>) : <p className="food-scope-popover__empty">{emptySearchLabel}</p>}
      </> : <p className="food-scope-popover__empty">{userLabel}</p>}
    </div> : null}
  </FoodScopePopover>
}

function FoodScopePopover({
  ariaLabel,
  children,
  disabled,
  label,
  onOpenChange,
  open,
  popoverClassName,
  summary,
}: {
  readonly ariaLabel: string
  readonly children: ReactNode
  readonly disabled: boolean
  readonly label: string
  readonly onOpenChange: (open: boolean) => void
  readonly open: boolean
  readonly popoverClassName?: string
  readonly summary: string
}) {
  return <Popover.Root onOpenChange={onOpenChange} open={open}>
    <Popover.Trigger asChild>
      <Button aria-label={label} className="food-scope-trigger" disabled={disabled} type="button" variant="outline">
        <span className="food-scope-trigger__summary">{summary}</span>
        <ChevronDown aria-hidden="true" size={16} />
      </Button>
    </Popover.Trigger>
    <Popover.Portal>
      <Popover.Content
        align="start"
        aria-label={ariaLabel}
        className={`food-scope-popover${popoverClassName ? ` ${popoverClassName}` : ""}`}
        collisionPadding={12}
        side="bottom"
        sideOffset={7}
      >
        {children}
      </Popover.Content>
    </Popover.Portal>
  </Popover.Root>
}
