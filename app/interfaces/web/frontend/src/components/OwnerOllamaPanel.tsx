import { Button } from "@/components/ui/button"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  installOllama,
  ownerOllamaStatus,
  startOllama,
  type OllamaStatus,
} from "../api/owner-ollama"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { Notice } from "./Notice"
import { OllamaModelsDialog } from "./OllamaModelsDialog"

type Props = {
  readonly csrfToken: string
}

type OllamaState = OllamaStatus["state"]

export function OwnerOllamaPanel({ csrfToken }: Props) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [status, setStatus] = useState<OllamaStatus | null>(null)
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
    if (status?.task?.state !== "running") return
    const timer = window.setInterval(() => { void refresh() }, 1000)
    return () => window.clearInterval(timer)
  }, [status?.task?.state])

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
  const canUseModels = status !== null && !["absent", "deleted", "failed", "cancelled", "repair_required"].includes(state) && !installing
  const buttonLabel = state === "stopped"
    ? t("providerConnections.ollama.actions.start")
    : t("providerConnections.ollama.actions.restart")

  return <section aria-labelledby="ollama-provider-title" className="provider-section" role="region">
    <div className="provider-section__heading"><div><h3 id="ollama-provider-title">{t("providerConnections.ollama.title")}</h3><p>{t("providerConnections.ollama.description")}</p></div></div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.load")} /> : null}
    <div className="provider-grid provider-grid--local">
      <article className={`provider-card provider-card--ollama provider-card--ollama-${state}`}>
        <div className="provider-card__title"><h4>{t("providerConnections.ollama.name")}</h4><span className={`status-badge status-badge--${state}`}>{ollamaStatusLabel(state, t)}</span></div>
        <p>{status ? t("providerConnections.ollama.card.availableModels", { count: status.installed_model_count }) : t("providerConnections.ollama.card.loading")}</p>
        <div className="manage-actions">
          {installing ? <Button disabled type="button" variant="outline">{t("providerConnections.ollama.actions.installing", { progress: task.progress })}</Button> : null}
          {!installing && status !== null && needsRepair ? <Button disabled type="button" variant="outline">{t("providerConnections.ollama.actions.repairRequired")}</Button> : null}
          {!installing && status !== null && !canUseModels && !needsRepair ? <Button disabled={pending !== null} onClick={() => { void runAction("install") }} type="button" variant="outline">{pending === "install" ? t("providerConnections.ollama.actions.installing", { progress: 0 }) : t("providerConnections.ollama.actions.install")}</Button> : null}
          {canUseModels ? <Button disabled={pending !== null} onClick={() => setDialogOpen(true)} type="button" variant="outline">{t("providerConnections.actions.models")}</Button> : null}
          {canUseModels ? <Button disabled={pending !== null} onClick={() => { void runAction(action) }} type="button" variant="outline">{pending === "start" ? t("providerConnections.ollama.actions.starting") : buttonLabel}</Button> : null}
        </div>
      </article>
    </div>
    <OllamaModelsDialog csrfToken={csrfToken} onChanged={refresh} onOpenChange={setDialogOpen} open={dialogOpen} status={status} />
  </section>
}

function ollamaStatusLabel(state: OllamaState, t: (key: string) => string): string {
  switch (state) {
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

function assertNever(value: never): never {
  throw new Error(`Unexpected Ollama state: ${String(value)}`)
}
