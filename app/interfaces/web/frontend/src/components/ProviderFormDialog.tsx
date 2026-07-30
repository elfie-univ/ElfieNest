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

type EditableModel = { readonly key: number; readonly id: string; readonly displayName: string }

function initialModels(provider: ProviderView): readonly EditableModel[] {
  const source = provider.models.length > 0
    ? provider.models
    : [{ id: "", display_name: "" } satisfies ProviderModelDraft]
  return source.map((model, index) => ({ key: index, id: model.id, displayName: model.display_name }))
}

export function ProviderFormDialog({ onOpenChange, onSave, open, provider }: ProviderFormDialogProps) {
  const { t } = useTranslation("manage")
  const [displayName, setDisplayName] = useState("")
  const [apiBase, setApiBase] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!product || !open) return
    setAlias(connection?.alias ?? "")
    setApiKey("")
  }, [connection, open, product])

  if (!provider) return null
  const method = provider.capabilities.connection_method
  const title = t(provider.configured ? "providers.form.titleEdit" : "providers.form.titleConfigure", { name: provider.name })
  const updateModel = (key: number, field: "id" | "displayName", value: string): void => {
    setModels((current) => current.map((model) => model.key === key ? { ...model, [field]: value } : model))
  }
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
    description={t(method === "local" ? "providers.form.descriptionLocal" : "providers.form.descriptionRemote")}
    onOpenChange={onOpenChange}
    open={open}
    title={title}
  >
    <form className="provider-form" onSubmit={(event) => { void submit(event) }}>
      <div className="provider-form__identity"><span>{t("providers.form.providerId")}</span><code>{provider.provider_id}</code></div>
      {method === "oauth" && provider.capabilities.oauth_unavailable
        ? <p className="provider-form__unavailable" role="status">{t("providers.form.oauthUnavailable")}</p>
        : <>
          <TextField label={t("providers.form.displayName")} onChange={setDisplayName} value={displayName} />
          <TextField
            hint={t(method === "local" ? "providers.form.apiBaseLocalHint" : "providers.form.apiBaseHint")}
            label="API Base URL"
            onChange={setApiBase}
            required
            type="url"
            value={apiBase}
          />
          {method === "api_key" ? <TextField
            autoComplete="new-password"
            hint={t(provider.configured ? "providers.form.apiKeyConfiguredHint" : "providers.form.apiKeyNewHint")}
            label={t("providers.form.apiKey")}
            onChange={setApiKey}
            required={!provider.configured}
            type="password"
            value={apiKey}
          /> : null}
          <SelectField
            disabled
            label={t("providers.form.authType")}
            onValueChange={() => undefined}
            options={[
              { label: t("providers.custom.noAuth"), value: "none" },
              { label: "Bearer", value: "bearer" },
              { label: "X-API-Key", value: "x-api-key" },
            ]}
            value={provider.auth_type}
          />
          <TextField hint={t("providers.form.testModelHint")} label={t("providers.form.testModel")} onChange={setTestModel} value={testModel} />
          <fieldset className="provider-model-editor">
            <legend>{t("providers.form.models")}</legend>
            {models.map((model, index) => <div className="provider-model-editor__row" key={model.key}>
              <TextField label={t("providers.form.modelId", { number: index + 1 })} onChange={(value) => updateModel(model.key, "id", value)} value={model.id} />
              <TextField label={t("providers.form.modelDisplayName", { number: index + 1 })} onChange={(value) => updateModel(model.key, "displayName", value)} value={model.displayName} />
              <Button variant="outline"
                aria-label={t("providers.form.removeModel", { name: model.id || model.key + 1 })}
                disabled={models.length === 1}
                onClick={() => setModels((current) => current.filter((item) => item.key !== model.key))}
                type="button"
              >{t("providers.actions.delete")}</Button>
            </div>)}
            <Button variant="outline"
              onClick={() => setModels((current) => [...current, { key: Math.max(-1, ...current.map((item) => item.key)) + 1, id: "", displayName: "" }])}
              type="button"
            >{t("providers.form.addModel")}</Button>
          </fieldset>
          <div className="manage-actions">
            <Button disabled={pending} type="submit">{pending ? t("providers.actions.saving") : t("providers.actions.save")}</Button>
            <Button variant="outline" disabled={pending} onClick={() => onOpenChange(false)} type="button">{t("providers.actions.cancel")}</Button>
          </div>
        </>}
    </form>
  </ManageDialog>
}
