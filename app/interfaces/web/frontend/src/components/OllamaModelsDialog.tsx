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

  return <ManageDialog contentClassName="ollama-models-dialog" onOpenChange={onOpenChange} open={open} title={t("providerConnections.ollama.models.title")}>
    {error ? <Notice kind="error" message={error} /> : null}
    <div className="ollama-models-dialog__toolbar manage-actions"><span>{t("providerConnections.ollama.models.count", { count: status.installed_model_count })}</span></div>
    <div aria-label={t("providerConnections.ollama.models.listLabel")} className="ollama-model-list">
      {status.models.map((model) => {
        const modelState = ollamaModelState(model)
        return <div className={`ollama-model-row ollama-model-row--${modelState}`} key={model.id}>
          <div><strong>{model.id}</strong>{model.recommended ? <small>{t("providerConnections.ollama.models.recommended")}</small> : null}</div>
          {model.installed
            ? <span className={`status-badge status-badge--${ollamaModelBadge(modelState)}`}>{t(`providerConnections.ollama.models.status.${modelState}`)}</span>
            : <Button disabled={pendingModel !== null} onClick={() => { void downloadModel(model.id) }} type="button" variant="outline">{pendingModel === model.id ? t("providerConnections.ollama.actions.downloading") : t("providerConnections.ollama.actions.download")}</Button>}
        </div>
      })}
    </div>
  </ManageDialog>
}

type OllamaModelState = "available" | "degraded" | "pending" | "unavailable" | "not_installed"

function ollamaModelState(model: OllamaStatus["models"][number]): OllamaModelState {
  if (!model.installed) return "not_installed"
  if (model.availability_status === "available") return "available"
  if (model.availability_status === "degraded") return "degraded"
  if (model.availability_status === "unavailable") return "unavailable"
  if (model.available === true) return "available"
  return "pending"
}

function ollamaModelBadge(state: OllamaModelState): "passed" | "warning" | "failed" | "muted" {
  if (state === "available") return "passed"
  if (state === "degraded") return "warning"
  if (state === "unavailable") return "failed"
  return "muted"
}
