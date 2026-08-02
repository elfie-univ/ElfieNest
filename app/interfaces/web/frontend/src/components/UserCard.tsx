import { useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { updateManagedUser, type OwnerUser } from "../api/client"
import { describeApiError, type LocalizedErrorState } from "../i18n/errors"
import { Avatar } from "./Avatar"
import { Icon } from "./Icon"
import { StatusIndicator } from "./StatusIndicator"

type UserCardProps = {
  readonly csrfToken: string
  readonly onError: (error: LocalizedErrorState) => void
  readonly onRemove: () => void
  readonly onReset: () => void
  readonly onSaved: () => Promise<void>
  readonly user: OwnerUser
}

function IdentityField({ label, value }: { readonly label: string; readonly value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>
}

function dateOnly(value: string): string {
  return value.split(/[ T]/)[0] ?? value
}

export function UserCard({ csrfToken, onError, onRemove, onReset, onSaved, user }: UserCardProps) {
  const { t } = useTranslation("manage")
  const [editing, setEditing] = useState(false)
  const [quota, setQuota] = useState(String(user.effective_elfie_limit))
  const [saving, setSaving] = useState(false)
  const isOwner = user.role === "owner"
  const displayName = user.display_name ?? user.account_id
  const protectedRemoval = isOwner || user.elfie_count > 0
  const presenceLabel = t(`users.values.${user.presence}`)
  const presenceTone = user.presence === "online" ? "active" : "inactive"
  const deleteReason = isOwner
    ? t("users.ownerReadOnly")
    : user.elfie_count > 0 ? t("users.delete.hasElfies") : null

  const save = async (): Promise<void> => {
    const nextQuota = Number.parseInt(quota, 10)
    if (!Number.isInteger(nextQuota) || nextQuota < 1) {
      onError(t("users.quotaValidation"))
      return
    }
    setSaving(true)
    try {
      await updateManagedUser(user.user_id, { elfie_quota_override: nextQuota }, csrfToken)
      setEditing(false)
      await onSaved()
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
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
    <Avatar imageUrl={user.avatar_url} name={displayName} />
    <div className="user-id-card__body">
      <StatusIndicator label={presenceLabel} tone={presenceTone} />
      <dl className="user-id-card__identity">
        <IdentityField label={t("users.fields.name")} value={displayName} />
        <IdentityField label={t("users.fields.account")} value={user.account_id} />
        <IdentityField label={t("users.fields.memberId")} value={String(user.user_id)} />
        <IdentityField label={t("users.fields.role")} value={user.role === "owner" ? t("users.values.owner") : t("users.values.member")} />
        <IdentityField label={t("users.fields.gender")} value={user.gender ?? t("users.values.notRegistered")} />
        <IdentityField label={t("users.fields.birthDate")} value={user.birth_date ?? t("users.values.notRegistered")} />
        <IdentityField label={t("users.fields.lastSeen")} value={user.last_seen_at ? dateOnly(user.last_seen_at) : t("users.values.notRegistered")} />
        <IdentityField label={t("users.fields.language")} value={user.language} />
        <IdentityField label={t("users.fields.joinedAt")} value={dateOnly(user.created_at)} />
        <IdentityField label={t("users.fields.elfieCount")} value={String(user.elfie_count)} />
        <div>
          <dt><label htmlFor={`quota-${user.user_id}`}>{t("users.fields.quota")}</label></dt>
          <dd>{editing
            ? <Input aria-label={t("users.fields.quota")} disabled={saving} id={`quota-${user.user_id}`} inputMode="numeric" min={1} onChange={(event) => setQuota(event.target.value)} type="number" value={quota} />
            : user.effective_elfie_limit}</dd>
        </div>
      </dl>
      <div className="user-id-card__actions">
        {editing
          ? <><Button aria-label={t("users.actions.saveFor", { accountId: user.account_id })} disabled={saving} onClick={() => { void save() }} type="button">{t("users.actions.save")}</Button><Button aria-label={t("users.actions.cancelFor", { accountId: user.account_id })} disabled={saving} onClick={cancel} type="button" variant="outline">{t("users.actions.cancel")}</Button></>
          : <Button aria-label={t("users.actions.editFor", { accountId: user.account_id })} disabled={isOwner} onClick={() => setEditing(true)} type="button" variant="outline"><Icon name="pencil" size={15} />{t("users.actions.edit")}</Button>}
        <Button aria-label={t("users.actions.resetFor", { accountId: user.account_id })} disabled={isOwner} onClick={onReset} type="button" variant="outline"><Icon name="lock-keyhole" size={15} />{t("users.actions.reset")}</Button>
        <Button aria-label={t("users.actions.deleteFor", { accountId: user.account_id })} aria-describedby={deleteReason ? `delete-reason-${user.user_id}` : undefined} disabled={protectedRemoval} onClick={onRemove} title={deleteReason ?? t("users.actions.delete")} type="button" variant="destructive"><Icon name="x" size={15} />{t("users.actions.delete")}</Button>
        {deleteReason ? <small id={`delete-reason-${user.user_id}`}>{deleteReason}</small> : null}
      </div>
    </div>
  </article></Card>
}
