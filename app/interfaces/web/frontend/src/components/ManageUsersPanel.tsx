import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import {
  deleteManagedUser,
  ownerUsers,
  resetManagedUserPassword,
  type OwnerUser,
} from "../api/client"
import { canManageRole, compareAccountListOrder, isManagerRole, MAX_ACCOUNTS, MAX_ADMINS, type AccountRole } from "../api/roles"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { compareLocalizedText, currentLocale } from "../i18n/format"
import { ConfirmDialog } from "./ConfirmDialog"
import { CreateUserDialog } from "./CreateUserDialog"
import { Icon } from "./Icon"
import { Notice } from "./Notice"
import { RefreshButton } from "./RefreshButton"
import { SelectField } from "./SelectField"
import { TemporaryPasswordDialog } from "./TemporaryPasswordDialog"
import { UserCard } from "./UserCard"

const ALL_ROLES = "all-roles" as const
type RoleFilter = AccountRole | typeof ALL_ROLES

function parseRoleFilter(value: string): RoleFilter {
  switch (value) {
    case ALL_ROLES:
    case "owner":
    case "admin":
    case "user":
      return value
    default:
      return ALL_ROLES
  }
}

export function ManageUsersPanel({ actorRole, csrfToken }: { readonly actorRole: AccountRole; readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [users, setUsers] = useState<readonly OwnerUser[] | null>(null)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<OwnerUser | null>(null)
  const [resetting, setResetting] = useState<OwnerUser | null>(null)
  const [deletePending, setDeletePending] = useState(false)
  const [resetPending, setResetPending] = useState(false)
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null)
  const [roleFilter, setRoleFilter] = useState<RoleFilter>(ALL_ROLES)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const adminCount = users?.filter((entry) => entry.role === "admin").length ?? 0
  const totalCapacityReached = users !== null && users.length >= MAX_ACCOUNTS
  const adminCapacityReached = adminCount >= MAX_ADMINS
  const visibleUsers = users?.filter((entry) => roleFilter === ALL_ROLES || entry.role === roleFilter) ?? []

  const load = useCallback(async (): Promise<void> => {
    setUsers(null)
    try {
      const loadedUsers = await ownerUsers()
      setUsers([...loadedUsers].sort(compareAccountListOrder))
      setError(null)
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setUsers([])
      setError(t("users.errors.load"))
    }
  }, [locale, t])

  useEffect(() => { void load() }, [load])

  const remove = async (): Promise<void> => {
    if (deleting === null || !canManageRole(actorRole, deleting.role)) return
    setDeletePending(true)
    try {
      await deleteManagedUser(deleting.user_id, csrfToken)
      setDeleting(null)
      setNotice(t("users.notices.removed"))
      await load()
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.delete"))
    } finally {
      setDeletePending(false)
    }
  }

  const resetPassword = async (): Promise<void> => {
    if (resetting === null || !canManageRole(actorRole, resetting.role)) return
    setResetPending(true)
    try {
      const result = await resetManagedUserPassword(resetting.user_id, csrfToken)
      setResetting(null)
      setTemporaryPassword(result.temporary_password)
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setResetPending(false)
    }
  }

  return <section className="manage-card manage-card--wide">
    <div className="manage-head">
      <div><h2>{t("users.title")}</h2><p>{t("users.description")}</p></div>
      <div className="manage-actions">
        <Button disabled={!isManagerRole(actorRole) || users === null || totalCapacityReached} onClick={() => setCreating(true)} title={totalCapacityReached ? t("users.capacity.totalReached") : undefined} type="button"><Icon name="plus" size={16} />{t("users.actions.add")}</Button>
        <RefreshButton label={t("users.actions.refresh")} onClick={() => { void load() }} />
      </div>
    </div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("users.errors.load")} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <div className="manage-filters manage-filters--users">
      <SelectField
        disabled={users === null}
        label={t("users.filters.role")}
        onValueChange={(value) => setRoleFilter(parseRoleFilter(value))}
        options={[
          { label: t("users.filters.allRoles"), value: ALL_ROLES },
          { label: t("users.values.owner"), value: "owner" },
          { label: t("users.values.admin"), value: "admin" },
          { label: t("users.values.user"), value: "user" },
        ]}
        value={roleFilter}
      />
    </div>
    <div className="user-id-grid">
      {users === null ? <p className="empty">{t("users.loading")}</p> : null}
      {users?.length === 0 && error === null ? <p className="empty">{t("users.empty")}</p> : null}
      {users !== null && users.length > 0 && visibleUsers.length === 0 && error === null ? <p className="empty">{t("users.emptyFiltered")}</p> : null}
      {visibleUsers.map((entry) => <UserCard
        csrfToken={csrfToken}
        key={entry.user_id}
        onError={setError}
        onRemove={() => setDeleting(entry)}
        onReset={() => setResetting(entry)}
        onSaved={async () => { setNotice(t("users.notices.quotaSaved")); await load() }}
        actorRole={actorRole}
        user={entry}
      />)}
    </div>
    <CreateUserDialog actorRole={actorRole} adminCapacityReached={adminCapacityReached} csrfToken={csrfToken} onClose={() => setCreating(false)} onSaved={async () => { setCreating(false); setNotice(t("users.notices.created")); await load() }} open={creating} />
    <ConfirmDialog confirmLabel={t("users.actions.confirmDelete")} danger description={deleting ? t("users.delete.confirm", { name: deleting.display_name ?? deleting.account_id }) : t("users.delete.confirmGeneric")} onConfirm={() => { void remove() }} onOpenChange={(open) => { if (!open && !deletePending) setDeleting(null) }} open={deleting !== null} pending={deletePending} title={t("users.delete.title")} />
    <ConfirmDialog confirmLabel={t("users.actions.confirmReset")} description={resetting ? t("users.reset.confirm", { name: resetting.display_name ?? resetting.account_id }) : t("users.reset.confirmGeneric")} onConfirm={() => { void resetPassword() }} onOpenChange={(open) => { if (!open && !resetPending) setResetting(null) }} open={resetting !== null} pending={resetPending} title={t("users.reset.title")} />
    <TemporaryPasswordDialog onClose={() => setTemporaryPassword(null)} password={temporaryPassword} />
  </section>
}
