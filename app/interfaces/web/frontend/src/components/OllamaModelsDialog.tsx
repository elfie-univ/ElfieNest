import { Button } from "@/components/ui/button"
import { useEffect, useState } from "react"
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
  const [pendingModel, setPendingModel] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) setError(null)
  }, [open])

  if (!status) return null

  const downloadModel = async (modelId: string): Promise<void> => {
    setPendingModel(modelId)
    try {
      await pullOllamaModels([modelId], csrfToken)
      setError(null)
      await onChanged()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : t("providerConnections.ollama.errors.download"))
    } finally {
      setPendingModel(null)
    }
  }

  return <ManageDialog contentClassName="ollama-models-dialog" description={t("providerConnections.ollama.models.description")} onOpenChange={onOpenChange} open={open} title={t("providerConnections.ollama.models.title")}>
    {error ? <Notice kind="error" message={error} /> : null}
    <div className="ollama-models-dialog__toolbar manage-actions"><span>{t("providerConnections.ollama.models.count", { count: status.installed_model_count })}</span></div>
    <div aria-label={t("providerConnections.ollama.models.listLabel")} className="ollama-model-list">
      {status.models.map((model) => <div className={model.installed ? "ollama-model-row ollama-model-row--installed" : "ollama-model-row"} key={model.id}>
        <div><strong>{model.id}</strong>{model.recommended ? <small>{t("providerConnections.ollama.models.recommended")}</small> : null}</div>
        {model.installed
          ? <span className="status-badge status-badge--passed">{t("providerConnections.ollama.models.downloaded")}</span>
          : <Button disabled={pendingModel !== null} onClick={() => { void downloadModel(model.id) }} type="button" variant="outline">{pendingModel === model.id ? t("providerConnections.ollama.actions.downloading") : t("providerConnections.ollama.actions.download")}</Button>}
      </div>)}
    </div>
  </ManageDialog>
}
