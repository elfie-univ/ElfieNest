import { useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { createManagedUser } from "../api/client"
import { type AccountRole, type ManagedCreationRole } from "../api/roles"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"
import { TextField } from "./TextField"

type CreateUserDialogProps = {
  readonly actorRole: AccountRole
  readonly adminCapacityReached: boolean
  readonly csrfToken: string
  readonly onClose: () => void
  readonly onSaved: () => Promise<void>
  readonly open: boolean
}

export function CreateUserDialog({ actorRole, adminCapacityReached, csrfToken, onClose, onSaved, open }: CreateUserDialogProps) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [accountId, setAccountId] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [password, setPassword] = useState("")
  const [role, setRole] = useState<ManagedCreationRole>("user")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<LocalizedErrorState>(null)

  const close = (): void => {
    setAccountId("")
    setDisplayName("")
    setPassword("")
    setRole("user")
    setError(null)
    onClose()
  }

  const save = async (): Promise<void> => {
    const normalizedAccountId = accountId.trim()
    if (!normalizedAccountId || password.trim().length < 6) {
      setError(t("users.create.required"))
      return
    }
    setPending(true)
    try {
      await createManagedUser(normalizedAccountId, displayName.trim() || null, password, role, csrfToken)
      close()
      await onSaved()
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(false)
    }
  }

  return <ManageDialog onOpenChange={(next) => { if (!next && !pending) close() }} open={open} title={t("users.create.title")}>
    <form className="manage-dialog__form" onSubmit={(event) => { event.preventDefault(); void save() }}>
      {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("users.errors.create")} /> : null}
      <TextField autoFocus label={t("users.create.accountId")} onChange={setAccountId} required value={accountId} />
      <TextField label={t("users.create.displayName")} onChange={setDisplayName} value={displayName} />
      {actorRole === "owner" ? <SelectField disabled={pending} label={t("users.create.role")} onValueChange={(value) => setRole(value === "admin" ? "admin" : "user")} options={[{ disabled: adminCapacityReached, label: t("users.values.admin"), value: "admin" }, { label: t("users.values.user"), value: "user" }]} value={role} /> : null}
      <TextField autoComplete="new-password" label={t("users.create.initialPassword")} minLength={6} onChange={setPassword} required type="password" value={password} />
      <div className="manage-actions"><Button disabled={pending} type="submit">{t("users.actions.create")}</Button><Button disabled={pending} onClick={close} type="button" variant="outline">{t("users.actions.cancel")}</Button></div>
    </form>
  </ManageDialog>
}
