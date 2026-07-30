import { Button } from "@/components/ui/button"
import { useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import type { ProviderConnectionDraft } from "../api/owner-providers"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"
import { TextField } from "./TextField"

type Props = {
  readonly onOpenChange: (open: boolean) => void
  readonly onSave: (draft: ProviderConnectionDraft) => Promise<void>
  readonly open: boolean
}

export function CustomProviderDialog({ onOpenChange, onSave, open }: Props) {
  const { t } = useTranslation("manage")
  const [providerId, setProviderId] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [apiBase, setApiBase] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [apiMode, setApiMode] = useState("chat_completions")
  const [authType, setAuthType] = useState("bearer")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setAlias("")
    setApiBase("")
    setApiKey("")
    setApiMode("chat_completions")
    setAuthType("bearer")
    setError(null)
  }, [open])

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setError(null)
    setPending(true)
    try {
      await onSave({
        catalog_id: "custom_openai",
        alias: alias.trim(),
        api_base: apiBase.trim(),
        api_key: apiKey,
        api_mode: apiMode,
        auth_type: authType,
        refresh_models: true,
        verify: true,
      })
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "自定义连接没有添加")
    } finally {
      setPending(false)
    }
  }

  return <ManageDialog
    description={t("providers.custom.description")}
    onOpenChange={onOpenChange}
    open={open}
    title={t("providers.custom.title")}
  >
    <form className="provider-form" onSubmit={(event) => { void submit(event) }}>
      <TextField autoFocus label={t("providers.custom.id")} onChange={setProviderId} placeholder={t("providers.custom.idPlaceholder")} required value={providerId} />
      <TextField label={t("providers.custom.displayName")} onChange={setDisplayName} placeholder={t("providers.custom.displayNamePlaceholder")} required value={displayName} />
      <TextField label="API Base URL" onChange={setApiBase} placeholder="https://host.example/v1" required type="url" value={apiBase} />
      {authType === "none" ? null : <TextField autoComplete="new-password" label={t("providers.form.apiKey")} onChange={setApiKey} required type="password" value={apiKey} />}
      <SelectField label={t("providers.custom.apiMode")} onValueChange={setApiMode} options={[
        { label: "OpenAI Chat Completions", value: "chat_completions" },
        { label: "Anthropic Messages", value: "anthropic_messages" },
        { label: "Ollama", value: "ollama" },
      ]} value={apiMode} />
      <SelectField label={t("providers.custom.authType")} onValueChange={setAuthType} options={[
        { label: "Bearer", value: "bearer" },
        { label: "X-API-Key", value: "x-api-key" },
        { label: t("providers.custom.noAuth"), value: "none" },
      ]} value={authType} />
      <TextField hint={t("providers.custom.testModelHint")} label={t("providers.custom.testModel")} onChange={setTestModel} value={testModel} />
      <div className="manage-actions">
        <Button disabled={pending} type="submit">{pending ? t("providers.custom.adding") : t("providers.custom.add")}</Button>
        <Button variant="outline" disabled={pending} onClick={() => onOpenChange(false)} type="button">{t("providers.actions.cancel")}</Button>
      </div>
    </form>
  </ManageDialog>
}
