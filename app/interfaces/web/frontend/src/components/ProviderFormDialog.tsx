import { useEffect, useState, type FormEvent } from "react"

import type { ProviderDraft, ProviderModelDraft, ProviderView } from "../api/owner-providers"
import { ManageDialog } from "./ManageDialog"
import { SelectField } from "./SelectField"
import { TextField } from "./TextField"

type ProviderFormDialogProps = {
  readonly onOpenChange: (open: boolean) => void
  readonly onSave: (draft: ProviderDraft) => Promise<void>
  readonly open: boolean
  readonly provider: ProviderView | null
}

type EditableModel = { readonly key: number; readonly id: string; readonly displayName: string }

function initialModels(provider: ProviderView): readonly EditableModel[] {
  const source = provider.models.length > 0
    ? provider.models
    : [{ id: "", display_name: "" } satisfies ProviderModelDraft]
  return source.map((model, index) => ({ key: index, id: model.id, displayName: model.display_name }))
}

export function ProviderFormDialog({ onOpenChange, onSave, open, provider }: ProviderFormDialogProps) {
  const [displayName, setDisplayName] = useState("")
  const [apiBase, setApiBase] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [testModel, setTestModel] = useState("")
  const [models, setModels] = useState<readonly EditableModel[]>([])
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!provider || !open) return
    setDisplayName(provider.display_name)
    setApiBase(provider.api_base)
    setApiKey("")
    setTestModel(provider.test_model)
    setModels(initialModels(provider))
  }, [open, provider])

  if (!provider) return null
  const method = provider.capabilities.connection_method
  const title = `${provider.configured ? "修改" : "配置"} ${provider.name}`
  const updateModel = (key: number, field: "id" | "displayName", value: string): void => {
    setModels((current) => current.map((model) => model.key === key ? { ...model, [field]: value } : model))
  }
  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    const draft: ProviderDraft = {
      display_name: displayName.trim(),
      api_base: apiBase.trim(),
      api_mode: provider.api_mode,
      auth_type: provider.auth_type,
      test_model: testModel.trim(),
      models: models
        .map((model) => ({ id: model.id.trim(), display_name: model.displayName.trim() || model.id.trim() }))
        .filter((model) => model.id.length > 0),
      ...(!provider.configured || apiKey ? { api_key: apiKey } : {}),
    }
    setPending(true)
    try {
      await onSave(draft)
    } finally {
      setPending(false)
    }
  }

  return <ManageDialog
    contentClassName="provider-form-dialog"
    description={method === "local" ? "连接本机模型服务并读取可用模型。" : "密钥只写入本机；读取时只返回是否已配置。"}
    onOpenChange={onOpenChange}
    open={open}
    title={title}
  >
    <form className="provider-form" onSubmit={(event) => { void submit(event) }}>
      <div className="provider-form__identity"><span>供应商 ID</span><code>{provider.provider_id}</code></div>
      {method === "oauth" && provider.capabilities.oauth_unavailable
        ? <p className="provider-form__unavailable" role="status">登录授权尚未接入；当前版本不会显示不可用的伪登录按钮。</p>
        : <>
          <TextField label="显示名称" onChange={setDisplayName} value={displayName} />
          <TextField
            hint={method === "local" ? "例如 http://localhost:11434" : "使用供应商默认地址；仅在网关或兼容接口场景修改。"}
            label="API Base URL"
            onChange={setApiBase}
            required
            type="url"
            value={apiBase}
          />
          {method === "api_key" ? <TextField
            autoComplete="new-password"
            hint={provider.configured ? "留空表示保留本机现有密钥。" : "仅写入本机配置，页面不会回显。"}
            label="API 密钥"
            onChange={setApiKey}
            required={!provider.configured}
            type="password"
            value={apiKey}
          /> : null}
          <SelectField
            ariaLabel="认证方式"
            disabled
            onValueChange={() => undefined}
            options={[
              { label: "无认证", value: "none" },
              { label: "Bearer", value: "bearer" },
              { label: "X-API-Key", value: "x-api-key" },
            ]}
            value={provider.auth_type}
          />
          <TextField hint="可选；用于单项连通性验证。" label="测试模型" onChange={setTestModel} value={testModel} />
          <fieldset className="provider-model-editor">
            <legend>手动模型</legend>
            {models.map((model) => <div className="provider-model-editor__row" key={model.key}>
              <TextField label="模型 ID" onChange={(value) => updateModel(model.key, "id", value)} value={model.id} />
              <TextField label="显示名称" onChange={(value) => updateModel(model.key, "displayName", value)} value={model.displayName} />
              <button
                aria-label={`删除模型 ${model.id || model.key + 1}`}
                className="button button--quiet"
                disabled={models.length === 1}
                onClick={() => setModels((current) => current.filter((item) => item.key !== model.key))}
                type="button"
              >删除</button>
            </div>)}
            <button
              className="button button--quiet"
              onClick={() => setModels((current) => [...current, { key: Math.max(-1, ...current.map((item) => item.key)) + 1, id: "", displayName: "" }])}
              type="button"
            >添加模型</button>
          </fieldset>
          <div className="manage-actions">
            <button className="button" disabled={pending} type="submit">{pending ? "保存中…" : "保存配置"}</button>
            <button className="button button--quiet" disabled={pending} onClick={() => onOpenChange(false)} type="button">取消</button>
          </div>
        </>}
    </form>
  </ManageDialog>
}
