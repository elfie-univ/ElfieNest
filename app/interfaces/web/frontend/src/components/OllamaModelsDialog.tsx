import { Button } from "@/components/ui/button"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { pullOllamaModels, type OllamaStatus } from "../api/owner-ollama"
import { ApiError } from "../api/http"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"

type Props = {
  readonly csrfToken: string
  readonly onChanged: () => Promise<void>
  readonly onOpenChange: (open: boolean) => void
  readonly open: boolean
  readonly status: OllamaStatus | null
}

export function OllamaModelsDialog({ csrfToken, onChanged, onOpenChange, open, status }: Props) {
  const { t } = useTranslation("manage")
  const [adding, setAdding] = useState(false)
  const [selected, setSelected] = useState<readonly string[]>([])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setAdding(false)
    setSelected([])
    setError(null)
  }, [open])

  const candidates = useMemo(() => status?.models.filter((model) => !model.installed) ?? [], [status?.models])

  if (!status) return null

  const toggleSelection = (modelId: string): void => {
    setSelected((current) => current.includes(modelId)
      ? current.filter((value) => value !== modelId)
      : [...current, modelId])
  }

  const downloadSelected = async (): Promise<void> => {
    if (selected.length === 0) return
    setPending(true)
    try {
      await pullOllamaModels(selected, csrfToken)
      setAdding(false)
      setSelected([])
      setError(null)
      await onChanged()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : t("providerConnections.ollama.errors.download"))
    } finally {
      setPending(false)
    }
  }

  return <ManageDialog contentClassName="ollama-models-dialog" description={t("providerConnections.ollama.models.description")} onOpenChange={onOpenChange} open={open} title={t("providerConnections.ollama.models.title")}>
    {error ? <Notice kind="error" message={error} /> : null}
    <div className="ollama-models-dialog__toolbar manage-actions">
      <span>{t("providerConnections.ollama.models.count", { count: status.installed_model_count })}</span>
      <Button disabled={pending} onClick={() => setAdding((value) => !value)} type="button" variant="outline">{adding ? t("providerConnections.ollama.actions.closeAdd") : t("providerConnections.ollama.actions.addModel")}</Button>
    </div>
    <div aria-label={t("providerConnections.ollama.models.listLabel")} className="ollama-model-list">
      {status.models.map((model) => <div className={model.installed ? "ollama-model-row ollama-model-row--installed" : "ollama-model-row"} key={model.id}>
        <div><strong>{model.display_name}</strong><code>{model.id}</code></div>
        <span className={model.installed ? "status-badge status-badge--passed" : "status-badge"}>{model.installed ? t("providerConnections.ollama.models.downloaded") : model.recommended ? `${t("providerConnections.ollama.models.recommended")} · ${t("providerConnections.ollama.models.available")}` : t("providerConnections.ollama.models.available")}</span>
      </div>)}
    </div>
    {adding ? <div aria-label={t("providerConnections.ollama.models.addLabel")} className="ollama-model-picker">
      {candidates.length === 0 ? <p className="empty-state">{t("providerConnections.ollama.models.noCandidates")}</p> : candidates.map((model) => <label className="ollama-model-option" key={model.id}><input aria-label={model.display_name} checked={selected.includes(model.id)} onChange={() => toggleSelection(model.id)} type="checkbox" /><span><strong>{model.display_name}</strong>{model.recommended ? <small>{t("providerConnections.ollama.models.recommended")}</small> : null}</span></label>)}
      <Button disabled={pending || selected.length === 0} onClick={() => { void downloadSelected() }} type="button">{pending ? t("providerConnections.ollama.actions.downloading") : t("providerConnections.ollama.actions.downloadSelected")}</Button>
    </div> : null}
  </ManageDialog>
}
