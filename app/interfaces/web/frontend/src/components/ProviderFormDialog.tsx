import { Button } from "@/components/ui/button"
import { useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import type {
  ProviderConnection,
  ProviderConnectionUpdate,
  ProviderProduct,
} from "../api/owner-providers"
import { ManageDialog } from "./ManageDialog"
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
  const { t } = useTranslation("manage")
  const [alias, setAlias] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!product || !open) return
    setAlias(connection?.alias ?? "")
    setApiKey("")
  }, [connection, open, product])

  if (!product) return null
  const method = product.connection_method
  const title = connection ? t("providerConnections.form.titleEdit", { name: product.name }) : t("providerConnections.form.titleConfigure", { name: product.name })
  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setPending(true)
    try {
      await onSave({
        ...(alias.trim() ? { alias: alias.trim() } : {}),
        ...(!connection || apiKey ? { api_key: apiKey } : {}),
        ...(!connection ? { refresh_models: true, verify: true } : {}),
      })
    } finally {
      setPending(false)
    }
  }

  return <ManageDialog
    contentClassName="provider-form-dialog"
    description={method === "local"
      ? t("providerConnections.form.localDescription")
      : t("providerConnections.form.remoteDescription")}
    onOpenChange={onOpenChange}
    open={open}
    title={title}
  >
    <form className="provider-form" onSubmit={(event) => { void submit(event) }}>
      <TextField
        hint={t("providerConnections.form.aliasHint")}
        label={t("providerConnections.form.alias")}
        onChange={setAlias}
        placeholder={product.name}
        value={alias}
      />
      {method === "api_key" ? <TextField
        autoComplete="new-password"
        autoFocus
        hint={connection ? t("providerConnections.form.apiKeyExistingHint") : t("providerConnections.form.apiKeyNewHint")}
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
          {pending ? t("providerConnections.actions.savingAndVerifying") : connection ? t("providerConnections.actions.save") : t("providerConnections.actions.saveAndVerify")}
        </Button>
        <Button variant="outline" disabled={pending} onClick={() => onOpenChange(false)} type="button">{t("providerConnections.actions.cancel")}</Button>
      </div>
    </form>
  </ManageDialog>
}
