import { Button } from "@/components/ui/button"
import { useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import type {
  ProviderConnection,
  ProviderConnectionUpdate,
  ProviderProduct,
} from "../api/owner-providers"
import { describeApiError, resolveLocalizedError } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { TextField } from "./TextField"

type ProviderFormDialogProps = {
  readonly connection: ProviderConnection | null
  readonly onOpenChange: (open: boolean) => void
  readonly onSave: (draft: ProviderConnectionUpdate) => Promise<void>
  readonly open: boolean
  readonly product: ProviderProduct | null
}

export function ProviderFormDialog({
  connection,
  onOpenChange,
  onSave,
  open,
  product,
}: ProviderFormDialogProps) {
  const { i18n, t } = useTranslation("manage")
  const [alias, setAlias] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!product || !open) return
    setAlias(connection?.alias ?? "")
    setApiKey("")
    setError(null)
  }, [connection, open, product])

  if (!product) return null
  const method = product.connection_method
  const title = connection ? t("providerConnections.form.titleEdit", { name: product.name }) : t("providerConnections.form.titleConfigure", { name: product.name })
  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setError(null)
    setPending(true)
    try {
      await onSave({
        ...(alias.trim() ? { alias: alias.trim() } : {}),
        ...(!connection || apiKey ? { api_key: apiKey } : {}),
        ...(!connection ? { refresh_models: true, verify: false } : {}),
      })
    } catch (reason: unknown) {
      setError(resolveLocalizedError(describeApiError(reason, "manage.save"), currentLocale(i18n)) ?? t("providerConnections.errors.save"))
    } finally {
      setPending(false)
    }
  }

  return <ManageDialog
    contentClassName="provider-form-dialog"
    onOpenChange={onOpenChange}
    open={open}
    title={title}
  >
    {error ? <Notice kind="error" message={error} /> : null}
    <form className="provider-form" onSubmit={(event) => { void submit(event) }}>
      <TextField
        label={t("providerConnections.form.alias")}
        onChange={setAlias}
        placeholder={product.name}
        value={alias}
      />
      {method === "api_key" ? <TextField
        autoComplete="new-password"
        autoFocus
        label={t("providerConnections.form.apiKey")}
        onChange={setApiKey}
        required={!connection}
        type="password"
        value={apiKey}
      /> : null}
      {method === "oauth" ? <p className="provider-form__unavailable" role="status">
        {product.oauth_available ? t("providerConnections.form.oauthAvailable") : t("providerConnections.form.oauthUnavailable")}
      </p> : null}
      <div className="manage-actions">
        <Button disabled={pending || (method === "oauth" && !product.oauth_available)} type="submit">
          {pending ? t("providerConnections.actions.saving") : t("providerConnections.actions.save")}
        </Button>
        <Button variant="outline" disabled={pending} onClick={() => onOpenChange(false)} type="button">{t("providerConnections.actions.cancel")}</Button>
      </div>
    </form>
  </ManageDialog>
}
