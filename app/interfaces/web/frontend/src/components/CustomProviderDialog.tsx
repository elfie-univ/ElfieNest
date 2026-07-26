import { useEffect, useState, type FormEvent } from "react"

import type { ProviderDraft } from "../api/owner-providers"
import { ManageDialog } from "./ManageDialog"
import { SelectField } from "./SelectField"
import { TextField } from "./TextField"

type Props = {
  readonly onOpenChange: (open: boolean) => void
  readonly onSave: (draft: ProviderDraft) => Promise<void>
  readonly open: boolean
}

export function CustomProviderDialog({ onOpenChange, onSave, open }: Props) {
  const [providerId, setProviderId] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [apiBase, setApiBase] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [apiMode, setApiMode] = useState("chat_completions")
  const [authType, setAuthType] = useState("bearer")
  const [testModel, setTestModel] = useState("")
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!open) return
    setProviderId("")
    setDisplayName("")
    setApiBase("")
    setApiKey("")
    setApiMode("chat_completions")
    setAuthType("bearer")
    setTestModel("")
  }, [open])

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    setPending(true)
    try {
      await onSave({
        provider_id: providerId.trim(),
        display_name: displayName.trim(),
        api_base: apiBase.trim(),
        api_key: apiKey,
        api_mode: apiMode,
        auth_type: authType,
        test_model: testModel.trim(),
      })
    } finally {
      setPending(false)
    }
  }

  return <ManageDialog
    description="用于 OpenAI 兼容或其他自建网关。ID 只能使用小写字母、数字和下划线。"
    onOpenChange={onOpenChange}
    open={open}
    title="添加自定义供应商"
  >
    <form className="provider-form" onSubmit={(event) => { void submit(event) }}>
      <TextField autoFocus label="供应商 ID" onChange={setProviderId} placeholder="例如 home_gateway" required value={providerId} />
      <TextField label="显示名称" onChange={setDisplayName} placeholder="例如 家庭模型网关" required value={displayName} />
      <TextField label="API Base URL" onChange={setApiBase} placeholder="https://host.example/v1" required type="url" value={apiBase} />
      {authType === "none" ? null : <TextField autoComplete="new-password" label="API 密钥" onChange={setApiKey} required type="password" value={apiKey} />}
      <SelectField ariaLabel="API 协议" onValueChange={setApiMode} options={[
        { label: "OpenAI Chat Completions", value: "chat_completions" },
        { label: "Anthropic Messages", value: "anthropic_messages" },
        { label: "Ollama", value: "ollama" },
      ]} value={apiMode} />
      <SelectField ariaLabel="认证方式" onValueChange={setAuthType} options={[
        { label: "Bearer", value: "bearer" },
        { label: "X-API-Key", value: "x-api-key" },
        { label: "无认证", value: "none" },
      ]} value={authType} />
      <TextField hint="可选；用于单项连通性验证。" label="测试模型" onChange={setTestModel} value={testModel} />
      <div className="manage-actions">
        <button className="button" disabled={pending} type="submit">{pending ? "保存中…" : "添加供应商"}</button>
        <button className="button button--quiet" disabled={pending} onClick={() => onOpenChange(false)} type="button">取消</button>
      </div>
    </form>
  </ManageDialog>
}
