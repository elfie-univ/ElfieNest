import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { createManagedUser, deleteManagedUser, ownerUsers, resetManagedUserPassword, updateManagedUser, type OwnerUser } from "../api/client"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { compareLocalizedText, currentLocale } from "../i18n/format"
import { Avatar } from "./Avatar"
import { ConfirmDialog } from "./ConfirmDialog"
import { Icon } from "./Icon"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { RefreshButton } from "./RefreshButton"
import { StatusIndicator } from "./StatusIndicator"
import { TextField } from "./TextField"
import { MOCK_USERS } from "./owner-card-mock-data"

export function ManageUsersPanel({ csrfToken }: { readonly csrfToken: string }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [users, setUsers] = useState<readonly OwnerUser[]>([])
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<OwnerUser | null>(null)
  const [resetting, setResetting] = useState<OwnerUser | null>(null)
  const [deletePending, setDeletePending] = useState(false)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [mockMode, setMockMode] = useState(false)
  const showDemoData = (reason?: unknown): void => {
    setUsers([...MOCK_USERS].sort((left, right) => compareLocalizedText(left.display_name, right.display_name, locale)))
    setMockMode(true)
    setError(null)
    setNotice(t("users.notices.demo"))
  }
  const load = async (): Promise<void> => {
    try {
      const loadedUsers = await ownerUsers()
      if (loadedUsers.length === 0) {
        showDemoData()
        return
      }
      setUsers([...loadedUsers].sort((left, right) => compareLocalizedText(left.display_name, right.display_name, locale)))
      setMockMode(false)
      setError(null)
      setNotice(null)
    } catch (reason: unknown) {
      showDemoData(reason)
    }
  }
  useEffect(() => { void load() }, [])
  const remove = async (entry: OwnerUser): Promise<void> => {
    setDeletePending(true)
    try {
      await deleteManagedUser(entry.account_id, csrfToken)
      setDeleting(null); setNotice(t("users.notices.removed")); await load()
    } catch (reason: unknown) { setError(describeApiError(reason, "manage.delete")) }
    finally { setDeletePending(false) }
  }
  const resetPassword = async (entry: OwnerUser): Promise<void> => {
    try {
      await resetManagedUserPassword(entry.account_id, csrfToken)
      setResetting(null)
      if (entry.role === "owner") {
        window.location.assign("/login")
        return
      }
      setNotice(t("users.notices.reset"))
    } catch (reason: unknown) { setError(describeApiError(reason, "manage.save")) }
  }
  return <section className="manage-card manage-card--wide">
    <div className="manage-head"><div><h2>{t("users.title")}</h2><p>{t("users.description")}</p></div><div className="manage-actions"><Button onClick={() => setCreating(true)} type="button"><Icon name="plus" size={16} />{t("users.actions.add")}</Button><RefreshButton label={t("users.actions.refresh")} onClick={() => { void load() }} /></div></div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} /> : null}{notice ? <Notice message={notice} /> : null}
    <div className="user-id-grid">{users.length === 0 ? <p className="empty">{t("users.empty")}</p> : users.map((entry) => <UserCard csrfToken={csrfToken} key={entry.account_id} mockMode={mockMode} onError={setError} onRemove={() => setDeleting(entry)} onReset={() => setResetting(entry)} onSaved={async () => { setNotice(t("users.notices.quotaSaved")); await load() }} user={entry} />)}</div>
    <CreateUserDialog csrfToken={csrfToken} onClose={() => setCreating(false)} onSaved={async () => { setCreating(false); setNotice(t("users.notices.created")); await load() }} open={creating} />
    <ConfirmDialog confirmLabel={t("users.actions.confirmDelete")} danger description={deleting ? t("users.delete.confirm", { name: deleting.display_name }) : t("users.delete.confirmGeneric")} onConfirm={() => { if (deleting) void remove(deleting) }} onOpenChange={(open) => { if (!open && !deletePending) setDeleting(null) }} open={deleting !== null} pending={deletePending} title={t("users.delete.title")} />
    <ConfirmDialog confirmLabel={t("users.actions.resetToDefault")} description={resetting ? t("users.reset.confirm", { name: resetting.display_name }) : t("users.reset.confirmGeneric")} onConfirm={() => { if (resetting) void resetPassword(resetting) }} onOpenChange={(open) => { if (!open) setResetting(null) }} open={resetting !== null} title={t("users.reset.title")} />
  </section>
}

function UserCard({ csrfToken, mockMode, onError, onRemove, onReset, onSaved, user }: { readonly csrfToken: string; readonly mockMode: boolean; readonly onError: (error: LocalizedErrorState) => void; readonly onRemove: () => void; readonly onReset: () => void; readonly onSaved: () => Promise<void>; readonly user: OwnerUser }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [editing, setEditing] = useState(false)
  const [quota, setQuota] = useState(String(user.effective_elfie_limit))
  const [saving, setSaving] = useState(false)
  const protectedRemoval = user.role === "owner" || user.elfie_count > 0
  const presenceLabel = user.online_status === "online" ? t("users.values.online") : t("users.values.offline")
  const deleteReason = user.role === "owner" ? t("users.delete.ownerProtected") : user.elfie_count > 0 ? t("users.delete.hasElfies") : null
  const save = async (): Promise<void> => {
    const nextQuota = Number.parseInt(quota, 10)
    if (!Number.isInteger(nextQuota) || nextQuota < 1) {
      onError(t("users.quotaValidation"))
      return
    }
    setSaving(true)
    try {
      await updateManagedUser(user.account_id, { elfie_quota_override: nextQuota }, csrfToken)
      setEditing(false)
      await onSaved()
    } catch (reason: unknown) {
      onError(describeApiError(reason, "manage.save"))
    } finally {
      setSaving(false)
    }
  }
  const cancel = (): void => {
    setQuota(String(user.effective_elfie_limit))
    setEditing(false)
  }
  return <Card asChild><article className="user-id-card">
    <Avatar imageUrl={user.avatar_url} name={user.display_name} />
    <div className="user-id-card__body">
      <StatusIndicator label={presenceLabel} tone={user.online_status === "online" ? "active" : "inactive"} />
      <dl className="user-id-card__identity">
        <IdentityField label={t("users.fields.name")} value={user.display_name} />
        <IdentityField label={t("users.fields.gender")} value={user.gender ?? t("users.values.notRegistered")} />
        <IdentityField label={t("users.fields.account")} value={`@${user.account_id}`} />
        <IdentityField label={t("users.fields.birthDate")} value={user.birth_date ?? t("users.values.notRegistered")} />
        <IdentityField label={t("users.fields.role")} value={user.role === "owner" ? t("users.values.owner") : t("users.values.member")} />
        <IdentityField label={t("users.fields.joinedAt")} value={formatDateOnly(user.created_at)} />
        <IdentityField label={t("users.fields.elfieCount")} value={String(user.elfie_count)} />
        <div>
          <dt><label htmlFor={`quota-${user.account_id}`}>{t("users.fields.quota")}</label></dt>
          <dd>{editing
            ? <Input aria-label={t("users.fields.quota")} disabled={saving} id={`quota-${user.account_id}`} inputMode="numeric" min={1} onChange={(event) => setQuota(event.target.value)} type="number" value={quota} />
            : user.effective_elfie_limit}</dd>
        </div>
      </dl>
      <div className="user-id-card__actions">{editing
        ? <><Button aria-label={t("users.actions.saveFor", { accountId: user.account_id })} disabled={saving} onClick={() => { void save() }} type="button">{t("users.actions.save")}</Button><Button aria-label={t("users.actions.cancelFor", { accountId: user.account_id })} disabled={saving} onClick={cancel} type="button" variant="outline">{t("users.actions.cancel")}</Button></>
        : <Button aria-label={t("users.actions.editFor", { accountId: user.account_id })} disabled={mockMode} onClick={() => setEditing(true)} type="button" variant="outline"><Icon name="pencil" size={15} />{t("users.actions.edit")}</Button>}<Button aria-label={t("users.actions.resetFor", { accountId: user.account_id })} disabled={mockMode} onClick={onReset} type="button" variant="outline"><Icon name="lock-keyhole" size={15} />{t("users.actions.reset")}</Button><Button aria-label={t("users.actions.deleteFor", { accountId: user.account_id })} aria-describedby={deleteReason ? `delete-reason-${user.account_id}` : undefined} disabled={mockMode || protectedRemoval} onClick={onRemove} title={mockMode ? t("users.mock.readOnly") : deleteReason ?? t("users.actions.delete")} type="button" variant="destructive"><Icon name="x" size={15} />{t("users.actions.delete")}</Button>{mockMode ? <small>{t("users.mock.readOnlyDescription")}</small> : deleteReason ? <small id={`delete-reason-${user.account_id}`}>{deleteReason}</small> : null}</div>
    </div>
  </article></Card>
}

function IdentityField({ className, label, value }: {
  readonly className?: string
  readonly label: string
  readonly value: string
}) {
  return <div className={className}><dt>{label}</dt><dd>{value}</dd></div>
}

function formatDateOnly(value: string): string {
  return value.split(/[ T]/)[0] ?? value
}

function CreateUserDialog({ csrfToken, onClose, onSaved, open }: { readonly csrfToken: string; readonly onClose: () => void; readonly onSaved: () => Promise<void>; readonly open: boolean }) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<LocalizedErrorState>(null)
  const save = async (): Promise<void> => {
    if (!username.trim() || !password) { setError(t("users.create.required")); return }
    try { await createManagedUser(username.trim(), password, csrfToken); await onSaved() }
    catch (reason: unknown) { setError(describeApiError(reason, "manage.save")) }
  }
  return <ManageDialog description={t("users.create.description")} onOpenChange={(next) => { if (!next) onClose() }} open={open} title={t("users.create.title")}><form onSubmit={(event) => { event.preventDefault(); void save() }}>{error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} /> : null}<TextField autoFocus label={t("users.create.username")} onChange={setUsername} required value={username} /><TextField autoComplete="new-password" label={t("users.create.initialPassword")} onChange={setPassword} required type="password" value={password} /><div className="manage-actions"><Button type="submit">{t("users.actions.create")}</Button><Button onClick={onClose} type="button" variant="outline">{t("users.actions.cancel")}</Button></div></form></ManageDialog>
}
