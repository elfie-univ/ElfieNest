import { Button } from "@/components/ui/button"
import { useEffect, useState, type FormEvent } from "react"

import {
  addProviderModel,
  deleteProviderModel,
  refreshProviderModels,
  updateProviderModel,
  type ProviderConnection,
  type ProviderModel,
  type ProviderModelDraft,
} from "../api/owner-providers"
import { ApiError } from "../api/http"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { TextField } from "./TextField"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table"

type Props = {
  readonly connection: ProviderConnection | null
  readonly csrfToken: string
  readonly onChanged: () => Promise<void>
  readonly onOpenChange: (open: boolean) => void
  readonly open: boolean
}

export function ProviderModelsDialog({
  connection,
  csrfToken,
  onChanged,
  onOpenChange,
  open,
}: Props) {
  const [adding, setAdding] = useState(false)
  const [editingModel, setEditingModel] = useState<ProviderModel | null>(null)
  const [advanced, setAdvanced] = useState(false)
  const [modelId, setModelId] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [contextWindow, setContextWindow] = useState("")
  const [maxOutput, setMaxOutput] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setAdding(false)
    setEditingModel(null)
    setAdvanced(false)
    setModelId("")
    setDisplayName("")
    setContextWindow("")
    setMaxOutput("")
    setError(null)
    setNotice(connection?.model_refresh?.message ?? null)
  }, [connection, open])

  if (!connection) return null

  const refresh = async (): Promise<void> => {
    setPending(true)
    try {
      const result = await refreshProviderModels(connection.connection_id, csrfToken)
      setNotice(result?.message ?? "模型清单已更新。")
      setError(null)
      if (result?.status === "failed") setAdding(true)
      await onChanged()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "模型清单读取失败")
      setAdding(true)
    } finally {
      setPending(false)
    }
  }

  const saveModel = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    const draft: ProviderModelDraft = {
      id: modelId.trim(),
      display_name: displayName.trim() || modelId.trim(),
      ...(contextWindow ? { context_window_tokens: Number(contextWindow) } : {}),
      ...(maxOutput ? { max_output_tokens: Number(maxOutput) } : {}),
    }
    setPending(true)
    try {
      if (editingModel) {
        await updateProviderModel(
          connection.connection_id,
          editingModel.id,
          {
            display_name: displayName.trim() || modelId.trim(),
            ...(draft.context_window_tokens ? { context_window_tokens: draft.context_window_tokens } : {}),
            ...(draft.max_output_tokens ? { max_output_tokens: draft.max_output_tokens } : {}),
          },
          csrfToken,
        )
      } else {
        await addProviderModel(connection.connection_id, draft, csrfToken)
      }
      setModelId("")
      setDisplayName("")
      setContextWindow("")
      setMaxOutput("")
      setAdding(false)
      setEditingModel(null)
      setNotice(editingModel ? "模型信息已更新。" : "手工模型已添加。")
      setError(null)
      await onChanged()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "模型信息没有保存")
    } finally {
      setPending(false)
    }
  }

  const beginEdit = (model: ProviderModel): void => {
    setEditingModel(model)
    setAdding(true)
    setAdvanced(Boolean(model.context_window_tokens || model.max_output_tokens))
    setModelId(model.id)
    setDisplayName(model.display_name)
    setContextWindow(model.context_window_tokens?.toString() ?? "")
    setMaxOutput(model.max_output_tokens?.toString() ?? "")
  }

  const toggleModelEditor = (): void => {
    if (adding) {
      setAdding(false)
      setEditingModel(null)
      return
    }
    setEditingModel(null)
    setModelId("")
    setDisplayName("")
    setContextWindow("")
    setMaxOutput("")
    setAdvanced(false)
    setAdding(true)
  }

  const removeOrHide = async (modelIdToChange: string, source: string, hidden: boolean): Promise<void> => {
    setPending(true)
    try {
      if (source === "manual") {
        await deleteProviderModel(connection.connection_id, modelIdToChange, csrfToken)
      } else {
        await updateProviderModel(
          connection.connection_id,
          modelIdToChange,
          { hidden: !hidden },
          csrfToken,
        )
      }
      setNotice(source === "manual" ? "手工模型已删除。" : hidden ? "模型已恢复显示。" : "模型已隐藏。")
      setError(null)
      await onChanged()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "模型没有更新")
    } finally {
      setPending(false)
    }
  }

  return <ManageDialog
    contentClassName="provider-models-dialog"
    description="模型 ID 会原样发送给当前订阅；显示名称用于跨订阅识别同一模型。"
    onOpenChange={onOpenChange}
    open={open}
    title={`${connection.alias} 的模型`}
  >
    {error ? <Notice kind="error" message={error} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <div className="manage-actions">
      <Button disabled={pending} onClick={() => { void refresh() }} type="button" variant="outline">
        {pending ? "读取中…" : "重新读取模型"}
      </Button>
      <Button disabled={pending} onClick={toggleModelEditor} type="button">
        {adding ? "收起模型编辑" : "手工添加模型"}
      </Button>
    </div>
    {adding ? <form className="provider-manual-model-form" onSubmit={(event) => { void saveModel(event) }}>
      <TextField autoFocus={!editingModel} label="Model ID" onChange={setModelId} placeholder="服务端实际模型 ID" readOnly={editingModel !== null} required value={modelId} />
      <TextField label="显示名称" onChange={setDisplayName} placeholder="例如 GLM-5" value={displayName} />
      <Button onClick={() => setAdvanced((value) => !value)} type="button" variant="ghost">
        {advanced ? "收起高级参数" : "高级参数"}
      </Button>
      {advanced ? <div className="provider-manual-model-form__advanced">
        <TextField label="上下文窗口" min={1} onChange={setContextWindow} type="number" value={contextWindow} />
        <TextField label="最大输出 Token" min={1} onChange={setMaxOutput} type="number" value={maxOutput} />
      </div> : null}
      <div className="manage-actions">
        <Button disabled={pending} type="submit">{editingModel ? "保存模型" : "添加模型"}</Button>
        <Button disabled={pending} onClick={() => { setAdding(false); setEditingModel(null) }} type="button" variant="outline">取消</Button>
      </div>
    </form> : null}
    {connection.models.length === 0 ? <p className="empty-state">尚未发现模型，可以重新读取或手工添加。</p> : <div className="provider-model-table-wrap">
      <Table aria-label={`${connection.alias} 模型列表`}>
        <TableHeader><TableRow><TableHead>显示名称</TableHead><TableHead>Model ID</TableHead><TableHead>来源</TableHead><TableHead>限制</TableHead><TableHead>操作</TableHead></TableRow></TableHeader>
        <TableBody>{connection.models.map((model) => <TableRow key={model.id}>
          <TableHead scope="row">{model.display_name}{model.hidden ? <small>已隐藏</small> : null}</TableHead>
          <TableCell><code>{model.id}</code></TableCell>
          <TableCell>{sourceLabel(model.source)}</TableCell>
          <TableCell><small>上下文 {model.context_window_tokens ?? "未知"}</small><small>输出 {model.max_output_tokens ?? "未知"}</small></TableCell>
          <TableCell><div className="manage-actions">
            <Button aria-label={`编辑 ${model.display_name}`} disabled={pending} onClick={() => beginEdit(model)} type="button" variant="outline">编辑</Button>
            <Button
              aria-label={`${model.source === "manual" ? "删除" : model.hidden ? "恢复" : "隐藏"} ${model.display_name}`}
              disabled={pending}
              onClick={() => { void removeOrHide(model.id, model.source, model.hidden) }}
              type="button"
              variant="outline"
            >{model.source === "manual" ? "删除" : model.hidden ? "恢复" : "隐藏"}</Button>
          </div></TableCell>
        </TableRow>)}</TableBody>
      </Table>
    </div>}
  </ManageDialog>
}

function sourceLabel(source: string): string {
  if (source === "discovered") return "自动发现"
  if (source === "provider_catalog") return "内置目录"
  return "手工添加"
}
