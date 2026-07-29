import { Button } from "@/components/ui/button"
import { useEffect, useState, type FormEvent } from "react"

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
    description="用于 OpenAI 兼容接口或自建网关；内部 ID 会由系统自动生成。"
    onOpenChange={onOpenChange}
    open={open}
    title="添加自定义连接"
  >
    <form className="provider-form" onSubmit={(event) => { void submit(event) }}>
      {error ? <Notice kind="error" message={error} /> : null}
      <TextField autoFocus label="显示名称" onChange={setAlias} placeholder="例如 京东 Coding Plan" required value={alias} />
      <TextField label="API Base URL" onChange={setApiBase} placeholder="https://host.example/v1" required type="url" value={apiBase} />
      {authType === "none" ? null : <TextField autoComplete="new-password" label="API 密钥" onChange={setApiKey} required type="password" value={apiKey} />}
      <SelectField label="API 协议" onValueChange={setApiMode} options={[
        { label: "OpenAI Chat Completions", value: "chat_completions" },
        { label: "Anthropic Messages", value: "anthropic_messages" },
        { label: "Ollama", value: "ollama" },
      ]} value={apiMode} />
      <SelectField label="认证方式" onValueChange={setAuthType} options={[
        { label: "Bearer", value: "bearer" },
        { label: "X-API-Key", value: "x-api-key" },
        { label: "无认证", value: "none" },
      ]} value={authType} />
      <div className="manage-actions">
        <Button disabled={pending} type="submit">{pending ? "保存并验证中…" : "验证并保存"}</Button>
        <Button variant="outline" disabled={pending} onClick={() => onOpenChange(false)} type="button">取消</Button>
      </div>
    </form>
  </ManageDialog>
}
