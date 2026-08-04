import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

import {
  addProviderModel,
  refreshProviderModels,
  saveProviderModels,
  updateProviderModel,
  type ProviderConnection,
  type ProviderModel,
} from "../api/owner-providers"
import { ApiError } from "../api/http"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import {
  CapabilityCell,
  formatTokens,
  ModelVerification,
  parseNullableInteger,
  sourceKey,
  toEditableModel,
  toEditableModels,
  toModelDraft,
  type EditableModel,
} from "./ProviderModelsDialog.helpers"
import { RefreshButton } from "./RefreshButton"
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
  const [editing, setEditing] = useState(false)
  const [addingManual, setAddingManual] = useState(false)
  const [drafts, setDrafts] = useState<EditableModel[]>([])
  const [manualId, setManualId] = useState("")
  const [manualName, setManualName] = useState("")
  const [manualContext, setManualContext] = useState("")
  const [manualOutput, setManualOutput] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !connection) return
    setEditing(false)
    setAddingManual(false)
    setDrafts(toEditableModels(connection.models))
    setManualId("")
    setManualName("")
    setManualContext("")
    setManualOutput("")
    setError(null)
    setNotice(connection.model_refresh?.message ?? null)
  }, [connection, open])

  if (!connection) return null

  const refresh = async (): Promise<void> => {
    setPending(true)
    try {
      const result = await refreshProviderModels(connection.connection_id, csrfToken)
      setEditing(false)
      setAddingManual(false)
      setNotice(result?.message ?? t("providerModels.notices.refreshed"))
      setError(null)
      await onChanged()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : t("providerModels.errors.load"))
    } finally {
      setPending(false)
    }
  }

  const beginEditing = (): void => {
    setDrafts(toEditableModels(connection.models))
    setEditing(true)
    setAddingManual(false)
    setError(null)
  }

  const cancelEditing = (): void => {
    setDrafts(toEditableModels(connection.models))
    setEditing(false)
    setError(null)
  }

  const saveAll = async (): Promise<void> => {
    setPending(true)
    try {
      await saveProviderModels(connection.connection_id, drafts.map(toModelDraft), csrfToken)
      setEditing(false)
      setNotice(t("providerModels.notices.savedAll"))
      setError(null)
      await onChanged()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : t("providerModels.errors.save"))
    } finally {
      setPending(false)
    }
  }

  const saveManual = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    const id = manualId.trim()
    if (!id) return
    setPending(true)
    try {
      await addProviderModel(connection.connection_id, {
        id,
        display_name: manualName.trim() || id,
        ...(manualContext ? { context_window_tokens: Number(manualContext) } : {}),
        ...(manualOutput ? { max_output_tokens: Number(manualOutput) } : {}),
      }, csrfToken)
      setAddingManual(false)
      setManualId("")
      setManualName("")
      setManualContext("")
      setManualOutput("")
      setNotice(t("providerModels.notices.added"))
      setError(null)
      await onChanged()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : t("providerModels.errors.save"))
    } finally {
      setPending(false)
    }
  }

  const toggleEnabled = async (model: ProviderModel, currentHidden = model.hidden): Promise<void> => {
    if (editing) {
      updateDraft(model.id, { hidden: !currentHidden })
      return
    }
    setPending(true)
    try {
      await updateProviderModel(connection.connection_id, model.id, { hidden: !currentHidden }, csrfToken)
      setNotice(currentHidden ? t("providerModels.notices.enabled") : t("providerModels.notices.disabled"))
      setError(null)
      await onChanged()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : t("providerModels.errors.update"))
    } finally {
      setPending(false)
    }
  }

  const updateDraft = (modelId: string, changes: Partial<EditableModel>): void => {
    setDrafts((current) => current.map((draft) => draft.original_id === modelId ? { ...draft, ...changes } : draft))
  }

  return <ManageDialog
    contentClassName="provider-models-dialog"
    onOpenChange={onOpenChange}
    open={open}
    title={t("providerModels.labels.title", { name: connection.alias })}
  >
    {error ? <Notice kind="error" message={error} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <div className="provider-models-toolbar manage-actions">
      <RefreshButton disabled={pending} label={t("providerModels.actions.refresh")} onClick={() => { void refresh() }} />
      <Button disabled={pending} onClick={() => { setAddingManual((value) => !value); setEditing(false) }} type="button" variant="outline">{t("providerModels.actions.addManual")}</Button>
      {editing
        ? <>
          <Button disabled={pending} onClick={() => { void saveAll() }} type="button">{t("providerModels.actions.saveAll")}</Button>
          <Button disabled={pending} onClick={cancelEditing} type="button" variant="outline">{t("providerModels.actions.cancel")}</Button>
        </>
        : <Button disabled={pending} onClick={beginEditing} type="button" variant="outline">{t("providerModels.actions.editAll")}</Button>}
    </div>
    {addingManual ? <form className="provider-models-add-form" onSubmit={(event) => { void saveManual(event) }}>
      <Input aria-label={t("providerModels.fields.modelId")} onChange={(event) => setManualId(event.target.value)} placeholder={t("providerModels.fields.modelIdPlaceholder")} required value={manualId} />
      <Input aria-label={t("providerModels.fields.displayName")} onChange={(event) => setManualName(event.target.value)} placeholder={t("providerModels.fields.displayNamePlaceholder")} value={manualName} />
      <Input aria-label={t("providerModels.fields.context")} min={1} onChange={(event) => setManualContext(event.target.value)} placeholder={t("providerModels.fields.context")} type="number" value={manualContext} />
      <Input aria-label={t("providerModels.fields.maxOutput")} min={1} onChange={(event) => setManualOutput(event.target.value)} placeholder={t("providerModels.fields.maxOutput")} type="number" value={manualOutput} />
      <Button disabled={pending} type="submit">{t("providerModels.actions.add")}</Button>
    </form> : null}
    {connection.models.length === 0 ? <p className="empty-state">{t("providerModels.empty")}</p> : <div className="provider-model-table-wrap">
      <Table aria-label={t("providerModels.labels.list", { name: connection.alias })} className="provider-model-table">
        <TableHeader><TableRow>
          <TableHead>{t("providerModels.columns.displayName")}</TableHead>
          <TableHead>{t("providerModels.fields.modelId")}</TableHead>
          <TableHead>{t("providerModels.columns.source")}</TableHead>
          <TableHead>{t("providerModels.columns.limits")}</TableHead>
          <TableHead>{t("providerModels.columns.capabilities")}</TableHead>
          <TableHead>{t("providerModels.columns.status")}</TableHead>
          <TableHead>{t("providerModels.columns.actions")}</TableHead>
        </TableRow></TableHeader>
        <TableBody>{connection.models.map((model, index) => {
          const draft = drafts[index] ?? toEditableModel(model)
          const row = editing ? draft : toEditableModel(model)
          return <TableRow key={model.id}>
            <TableCell>{editing ? <Input aria-label={`${t("providerModels.fields.displayName")} ${model.display_name}`} onChange={(event) => updateDraft(model.id, { display_name: event.target.value })} value={row.display_name} /> : <strong>{model.display_name}</strong>}</TableCell>
            <TableCell>{editing && model.source === "manual" ? <Input aria-label={`Model ID ${model.display_name}`} onChange={(event) => updateDraft(model.id, { id: event.target.value })} value={row.id} /> : <code>{row.id}</code>}</TableCell>
            <TableCell>{t(sourceKey(model.source))}</TableCell>
            <TableCell>{editing
              ? <div className="provider-model-edit-limits"><Input aria-label={`${t("providerModels.fields.context")} ${model.display_name}`} min={1} onChange={(event) => updateDraft(model.id, { context_window_tokens: parseNullableInteger(event.target.value) })} type="number" value={row.context_window_tokens?.toString() ?? ""} /><Input aria-label={`${t("providerModels.fields.maxOutput")} ${model.display_name}`} min={1} onChange={(event) => updateDraft(model.id, { max_output_tokens: parseNullableInteger(event.target.value) })} type="number" value={row.max_output_tokens?.toString() ?? ""} /></div>
              : <span className="provider-model-limits">{formatTokens(model.context_window_tokens)} / {formatTokens(model.max_output_tokens)}</span>}</TableCell>
            <TableCell><div className="provider-model-capabilities">
              <CapabilityCell label={t("providerModels.labels.vision")} onChange={editing ? (value) => updateDraft(model.id, { supports_vision: value }) : undefined} value={editing ? row.supports_vision : model.supports_vision} />
              <span aria-hidden="true" className="provider-model-capability-separator">/</span>
              <CapabilityCell label={t("providerModels.labels.tools")} onChange={editing ? (value) => updateDraft(model.id, { supports_tools: value }) : undefined} value={editing ? row.supports_tools : model.supports_tools} />
              <span aria-hidden="true" className="provider-model-capability-separator">/</span>
              <CapabilityCell label={t("providerModels.labels.reasoning")} onChange={editing ? (value) => updateDraft(model.id, { supports_reasoning: value }) : undefined} value={editing ? row.supports_reasoning : model.supports_reasoning} />
            </div></TableCell>
            <TableCell><ModelVerification model={model} /></TableCell>
            <TableCell><Button disabled={pending} onClick={() => { void toggleEnabled(model, row.hidden) }} size="sm" type="button" variant="outline">{row.hidden ? t("providerModels.actions.enable") : t("providerModels.actions.disable")}</Button></TableCell>
          </TableRow>
        })}</TableBody>
      </Table>
    </div>}
  </ManageDialog>
}
