import { Button } from "@/components/ui/button"
import { useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import type { ProviderConnectionDraft } from "../api/owner-providers"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"
import { TextField } from "./TextField"

export type CustomProviderPreset = "openai" | "anthropic"

const PRESET_DEFAULTS = {
  anthropic: { apiMode: "anthropic_messages", authType: "x-api-key" },
  openai: { apiMode: "chat_completions", authType: "bearer" },
} as const satisfies Record<CustomProviderPreset, { readonly apiMode: string; readonly authType: string }>

type Props = {
  readonly onOpenChange: (open: boolean) => void
  readonly onSave: (draft: ProviderConnectionDraft) => Promise<void>
  readonly open: boolean
  readonly preset?: CustomProviderPreset
}

export function CustomProviderDialog({ onOpenChange, onSave, open, preset = "openai" }: Props) {
  const { t } = useTranslation("manage")
  const [alias, setAlias] = useState("")
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
    const defaults = PRESET_DEFAULTS[preset]
    setApiMode(defaults.apiMode)
    setAuthType(defaults.authType)
    setError(null)
  }, [open, preset])

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
      setError(reason instanceof Error ? reason.message : t("providerConnections.errors.save"))
    } finally {
      setPending(false)
    }
  }

  return <ManageDialog
    description={t(preset === "anthropic" ? "providerConnections.custom.anthropicDescription" : "providerConnections.custom.openaiDescription")}
    onOpenChange={onOpenChange}
    open={open}
    title={t(preset === "anthropic" ? "providerConnections.custom.anthropicTitle" : "providerConnections.custom.openaiTitle")}
  >
    <form className="provider-form" onSubmit={(event) => { void submit(event) }}>
      <TextField autoFocus label={t("providerConnections.custom.displayName")} onChange={setAlias} placeholder={t("providerConnections.custom.displayNamePlaceholder")} required value={alias} />
      <TextField label="API Base URL" onChange={setApiBase} placeholder="https://host.example/v1" required type="url" value={apiBase} />
      {authType === "none" ? null : <TextField autoComplete="new-password" label={t("providerConnections.custom.apiKey")} onChange={setApiKey} required type="password" value={apiKey} />}
      <SelectField label={t("providerConnections.custom.apiMode")} onValueChange={setApiMode} options={[
        { label: "OpenAI Chat Completions", value: "chat_completions" },
        { label: "Anthropic Messages", value: "anthropic_messages" },
        { label: "Ollama", value: "ollama" },
      ]} value={apiMode} />
      <SelectField label={t("providerConnections.custom.authType")} onValueChange={setAuthType} options={[
        { label: "Bearer", value: "bearer" },
        { label: "X-API-Key", value: "x-api-key" },
        { label: t("providerConnections.custom.noAuth"), value: "none" },
      ]} value={authType} />
      <div className="manage-actions">
        <Button disabled={pending} type="submit">{pending ? t("providerConnections.actions.savingAndVerifying") : t("providerConnections.actions.saveAndVerify")}</Button>
        <Button variant="outline" disabled={pending} onClick={() => onOpenChange(false)} type="button">{t("providerConnections.actions.cancel")}</Button>
      </div>
    </form>
  </ManageDialog>
}
