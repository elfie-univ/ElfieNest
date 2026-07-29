import { Button } from "@/components/ui/button"
import { useEffect, useState, type FormEvent } from "react"

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
  const title = `${connection ? "修改" : "配置"} ${product.name}`
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
      ? "连接本机模型服务，保存后自动读取模型。"
      : "地址、协议与认证方式由内置目录维护；密钥只保存在本机。"}
    onOpenChange={onOpenChange}
    open={open}
    title={title}
  >
    <form className="provider-form" onSubmit={(event) => { void submit(event) }}>
      <TextField
        hint="可选；配置同一品牌的多个账号时，用别名区分。"
        label="订阅别名"
        onChange={setAlias}
        placeholder={product.name}
        value={alias}
      />
      {method === "api_key" ? <TextField
        autoComplete="new-password"
        autoFocus
        hint={connection ? "留空表示保留本机现有密钥。" : "保存后会自动验证并读取模型清单。"}
        label="API 密钥"
        onChange={setApiKey}
        required={!connection}
        type="password"
        value={apiKey}
      /> : null}
      {method === "oauth" ? <p className="provider-form__unavailable" role="status">
        {product.oauth_available ? "保存后将打开官方登录授权页面。" : "这个产品的登录授权尚未接入。"}
      </p> : null}
      <div className="manage-actions">
        <Button disabled={pending || (method === "oauth" && !product.oauth_available)} type="submit">
          {pending ? "保存并验证中…" : connection ? "保存配置" : "验证并保存"}
        </Button>
        <Button variant="outline" disabled={pending} onClick={() => onOpenChange(false)} type="button">取消</Button>
      </div>
    </form>
  </ManageDialog>
}
