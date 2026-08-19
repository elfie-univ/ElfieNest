import { Button } from "@/components/ui/button"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  installOllama,
  ownerOllamaStatus,
  supportedOllamaModelCounts,
  startOllama,
  type OllamaStatus,
  type SupportedOllamaModelCounts,
} from "../api/owner-ollama"
import { setupModelCatalog } from "../api/setup"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { Notice } from "./Notice"
import { OllamaModelsDialog } from "./OllamaModelsDialog"

type Props = {
  readonly csrfToken: string
}

type OllamaState = OllamaStatus["state"]
type OllamaDisplayState = OllamaState | "loading" | "no_models" | "partial" | "pending" | "unavailable"

export function OwnerOllamaPanel({ csrfToken }: Props) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [status, setStatus] = useState<OllamaStatus | null>(null)
  const [supportedModelIds, setSupportedModelIds] = useState<readonly string[] | null>(null)
  const [supportedModelsLoaded, setSupportedModelsLoaded] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [pending, setPending] = useState<"install" | "start" | null>(null)
  const [error, setError] = useState<LocalizedErrorState>(null)

  const refresh = async (): Promise<void> => {
    try {
      setStatus(await ownerOllamaStatus())
      setError(null)
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.load"))
    }
  }

  useEffect(() => { void refresh() }, [])

  useEffect(() => {
    void setupModelCatalog()
      .then((models) => setSupportedModelIds(models.map((model) => model.model_id)))
      .catch(() => setSupportedModelIds(null))
      .finally(() => setSupportedModelsLoaded(true))
  }, [])

  useEffect(() => {
    if (status?.state !== "unknown" && status?.task?.state !== "running") return
    const timer = window.setInterval(() => { void refresh() }, 1000)
    return () => window.clearInterval(timer)
  }, [status?.state, status?.task?.state])

  const supportedCounts = status === null || supportedModelIds === null
    ? status?.model_counts ?? null
    : supportedOllamaModelCounts(status, supportedModelIds)
  const runAction = async (action: "install" | "start"): Promise<void> => {
    setPending(action)
    try {
      const next = action === "install"
        ? await installOllama(csrfToken)
        : await startOllama(csrfToken)
      setStatus(next)
      setError(null)
    } catch (reason: unknown) {
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(null)
    }
  }

  const state = status?.state ?? "absent"
  const task = status?.task
  const installing = task?.key === "install" && task.state === "running"
  const needsRepair = state === "repair_required"
  const action = "start"
  const canUseModels = status !== null && !["unknown", "absent", "deleted", "failed", "cancelled", "repair_required"].includes(state) && !installing
  const canInstall = status !== null && state !== "unknown" && !canUseModels && !needsRepair
  const displayedStatus = status === null || supportedModelIds === null || supportedCounts === null
    ? status
    : {
        ...status,
        installed_model_count: supportedCounts.installed,
        model_counts: supportedCounts,
        models: status.models.filter((model) => supportedModelIds.includes(model.id)),
      }
  const localDisplayState = ollamaDisplayState(status, supportedCounts, supportedModelsLoaded)
  const buttonLabel = state === "stopped"
    ? t("providerConnections.ollama.actions.start")
    : t("providerConnections.ollama.actions.restart")

  return <section aria-labelledby="ollama-provider-title" className="provider-section" role="region">
    <div className="provider-section__heading"><div><h3 id="ollama-provider-title">{t("providerConnections.ollama.title")}</h3></div></div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.load")} /> : null}
    <div className="provider-grid provider-grid--local">
      <article className={`provider-card provider-card--ollama provider-card--ollama-${localDisplayState}`}>
        <div className="provider-card__title"><h4>{t("providerConnections.ollama.name")}</h4><span className={`status-badge status-badge--${localDisplayState}`}>{ollamaStatusLabel(state, t, localDisplayState)}</span></div>
        <p aria-live="polite">{status && state !== "unknown" && supportedModelsLoaded && supportedCounts ? t("providerConnections.ollama.card.modelStats", { available: supportedCounts.available, total: supportedCounts.installed }) : t("providerConnections.ollama.card.loading")}</p>
        <div className="manage-actions">
          {installing ? <Button disabled type="button" variant="outline">{t("providerConnections.ollama.actions.installing", { progress: task.progress })}</Button> : null}
          {!installing && status !== null && needsRepair ? <Button disabled type="button" variant="outline">{t("providerConnections.ollama.actions.repairRequired")}</Button> : null}
          {!installing && canInstall ? <Button disabled={pending !== null} onClick={() => { void runAction("install") }} type="button" variant="outline">{pending === "install" ? t("providerConnections.ollama.actions.installing", { progress: 0 }) : t("providerConnections.ollama.actions.install")}</Button> : null}
          {canUseModels ? <Button disabled={pending !== null} onClick={() => setDialogOpen(true)} type="button" variant="outline">{t("providerConnections.actions.models")}</Button> : null}
          {canUseModels ? <Button disabled={pending !== null} onClick={() => { void runAction(action) }} type="button" variant="outline">{pending === "start" ? t("providerConnections.ollama.actions.starting") : buttonLabel}</Button> : null}
        </div>
      </article>
    </div>
    <OllamaModelsDialog csrfToken={csrfToken} onChanged={refresh} onOpenChange={setDialogOpen} open={dialogOpen} status={displayedStatus} />
  </section>
}

function ollamaStatusLabel(state: OllamaState, t: (key: string) => string, displayState: OllamaDisplayState = state): string {
  if (displayState === "loading") return t("providerConnections.ollama.status.loading")
  if (displayState === "no_models") return t("providerConnections.ollama.status.noModels")
  if (displayState === "partial") return t("providerConnections.ollama.status.partial")
  if (displayState === "pending") return t("providerConnections.ollama.status.pending")
  if (displayState === "unavailable") return t("providerConnections.ollama.status.unavailable")
  switch (state) {
    case "unknown": return t("providerConnections.ollama.status.loading")
    case "absent": return t("providerConnections.ollama.status.absent")
    case "healthy": return t("providerConnections.ollama.status.healthy")
    case "stopped": return t("providerConnections.ollama.status.stopped")
    case "deleted": return t("providerConnections.ollama.status.deleted")
    case "installing": return t("providerConnections.ollama.status.installing")
    case "failed": return t("providerConnections.ollama.status.failed")
    case "cancelled": return t("providerConnections.ollama.status.cancelled")
    case "repair_required": return t("providerConnections.ollama.status.repairRequired")
    default: return assertNever(state)
  }
}

function ollamaDisplayState(
  status: OllamaStatus | null,
  counts: SupportedOllamaModelCounts | null,
  supportedModelsLoaded: boolean,
): OllamaDisplayState {
  if (status === null || !supportedModelsLoaded || status.state === "unknown" || counts === null) return "loading"
  if (status.state !== "healthy") return status.state
  if (counts.installed === 0) return "no_models"
  if (counts.available > 0) return "healthy"
  if (counts.degraded > 0) return "partial"
  if (counts.pending > 0) return "pending"
  if (counts.unavailable > 0) return "unavailable"
  return "pending"
}

function assertNever(value: never): never {
  throw new Error(`Unexpected Ollama state: ${String(value)}`)
}
