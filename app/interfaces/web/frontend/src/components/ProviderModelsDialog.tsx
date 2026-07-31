import { Button } from "@/components/ui/button"
import { useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

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
  const { t } = useTranslation("manage")
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
      setNotice(result?.message ?? t("providerModels.notices.refreshed"))
      setError(null)
      if (result?.status === "failed") setAdding(true)
      await onChanged()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : t("providerModels.errors.load"))
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
      setNotice(editingModel ? t("providerModels.notices.updated") : t("providerModels.notices.added"))
      setError(null)
      await onChanged()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : t("providerModels.errors.save"))
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
      setNotice(source === "manual" ? t("providerModels.notices.deleted") : hidden ? t("providerModels.notices.restored") : t("providerModels.notices.hidden"))
      setError(null)
      await onChanged()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : t("providerModels.errors.update"))
    } finally {
      setPending(false)
    }
  }

  return <ManageDialog
    contentClassName="provider-models-dialog"
    description={t("providerModels.description")}
    onOpenChange={onOpenChange}
    open={open}
    title={t("providerModels.labels.title", { name: connection.alias })}
  >
    {error ? <Notice kind="error" message={error} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <div className="manage-actions">
      <Button disabled={pending} onClick={() => { void refresh() }} type="button" variant="outline">
        {pending ? t("providerModels.actions.refreshing") : t("providerModels.actions.refresh")}
      </Button>
      <Button disabled={pending} onClick={toggleModelEditor} type="button">
        {adding ? t("providerModels.actions.collapseEditor") : t("providerModels.actions.addManual")}
      </Button>
    </div>
    {adding ? <form className="provider-manual-model-form" onSubmit={(event) => { void saveModel(event) }}>
      <TextField autoFocus={!editingModel} label="Model ID" onChange={setModelId} placeholder={t("providerModels.fields.modelIdPlaceholder")} readOnly={editingModel !== null} required value={modelId} />
      <TextField label={t("providerModels.fields.displayName")} onChange={setDisplayName} placeholder={t("providerModels.fields.displayNamePlaceholder")} value={displayName} />
      <Button onClick={() => setAdvanced((value) => !value)} type="button" variant="ghost">
        {advanced ? t("providerModels.actions.collapseAdvanced") : t("providerModels.actions.showAdvanced")}
      </Button>
      {advanced ? <div className="provider-manual-model-form__advanced">
        <TextField label={t("providerModels.fields.context")} min={1} onChange={setContextWindow} type="number" value={contextWindow} />
        <TextField label={t("providerModels.fields.maxOutput")} min={1} onChange={setMaxOutput} type="number" value={maxOutput} />
      </div> : null}
      <div className="manage-actions">
        <Button disabled={pending} type="submit">{editingModel ? t("providerModels.actions.save") : t("providerModels.actions.add")}</Button>
        <Button disabled={pending} onClick={() => { setAdding(false); setEditingModel(null) }} type="button" variant="outline">{t("providerModels.actions.cancel")}</Button>
      </div>
    </form> : null}
    {connection.models.length === 0 ? <p className="empty-state">{t("providerModels.empty")}</p> : <div className="provider-model-table-wrap">
      <Table aria-label={t("providerModels.labels.list", { name: connection.alias })}>
        <TableHeader><TableRow><TableHead>{t("providerModels.columns.displayName")}</TableHead><TableHead>Model ID</TableHead><TableHead>{t("providerModels.columns.source")}</TableHead><TableHead>{t("providerModels.columns.limits")}</TableHead><TableHead>{t("providerModels.columns.actions")}</TableHead></TableRow></TableHeader>
        <TableBody>{connection.models.map((model) => <TableRow key={model.id}>
          <TableHead scope="row">{model.display_name}{model.hidden ? <small>{t("providerModels.labels.hidden")}</small> : null}</TableHead>
          <TableCell><code>{model.id}</code></TableCell>
          <TableCell>{t(sourceKey(model.source))}</TableCell>
          <TableCell><small>{t("providerModels.labels.context", { value: model.context_window_tokens ?? t("providerModels.labels.unknown") })}</small><small>{t("providerModels.labels.output", { value: model.max_output_tokens ?? t("providerModels.labels.unknown") })}</small></TableCell>
          <TableCell><div className="manage-actions">
            <Button aria-label={`${t("providerModels.actions.edit")} ${model.display_name}`} disabled={pending} onClick={() => beginEdit(model)} type="button" variant="outline">{t("providerModels.actions.edit")}</Button>
            <Button
              aria-label={`${model.source === "manual" ? t("providerModels.actions.delete") : model.hidden ? t("providerModels.actions.restore") : t("providerModels.actions.hide")} ${model.display_name}`}
              disabled={pending}
              onClick={() => { void removeOrHide(model.id, model.source, model.hidden) }}
              type="button"
              variant="outline"
            >{model.source === "manual" ? t("providerModels.actions.delete") : model.hidden ? t("providerModels.actions.restore") : t("providerModels.actions.hide")}</Button>
          </div></TableCell>
        </TableRow>)}</TableBody>
      </Table>
    </div>}
  </ManageDialog>
}

function sourceKey(source: string): "providerModels.sources.bundled" | "providerModels.sources.manual" | "providerModels.sources.official" | "providerModels.sources.remote" {
  if (source === "official") return "providerModels.sources.official"
  if (source === "remote_catalog") return "providerModels.sources.remote"
  if (source === "bundled_catalog") return "providerModels.sources.bundled"
  return "providerModels.sources.manual"
}
