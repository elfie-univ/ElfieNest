import { Button } from "@/components/ui/button"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  benchmarkProviderModels,
  ownerModelMatrix,
  validateAllProviderModels,
  type BenchmarkCombination,
  type ModelMatrix,
} from "../api/owner-providers"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { RefreshButton } from "./RefreshButton"

type ModelMatrixDialogProps = {
  readonly csrfToken: string
  readonly onOpenChange: (open: boolean) => void
  readonly open: boolean
}

export function ModelMatrixDialog({ csrfToken, onOpenChange, open }: ModelMatrixDialogProps) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [matrix, setMatrix] = useState<ModelMatrix | null>(null)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const load = useCallback(async (): Promise<void> => {
    try {
      setMatrix(await ownerModelMatrix())
      setError(null)
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.load"))
    }
  }, [])
  useEffect(() => {
    if (open) void load()
  }, [load, open])

  const benchmarkCombinations = matrix ? collectBenchmarkCombinations(matrix) : []

  const validateAll = async (): Promise<void> => {
    setPending(true)
    try {
      const result = await validateAllProviderModels(csrfToken)
      setNotice(t("modelMatrix.validationNotice", { runId: result.run_id }))
      await load()
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(false)
    }
  }

  const benchmark = async (
    combinations: readonly BenchmarkCombination[],
    emptyNotice: string,
  ): Promise<void> => {
    if (combinations.length === 0) {
      setNotice(emptyNotice)
      return
    }
    setPending(true)
    try {
      const result = await benchmarkProviderModels(combinations.slice(0, 12), csrfToken)
      const passed = result.results.filter((item) => item.status === "passed").length
      setNotice(t("modelMatrix.notice", { failed: result.results.length - passed, passed }))
      await load()
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setError(describeApiError(reason, "manage.save"))
    } finally {
      setPending(false)
    }
  }

  return <ManageDialog
    contentClassName="model-matrix-dialog"
    description={t("modelMatrix.description")}
    onOpenChange={onOpenChange}
    open={open}
    title={t("modelMatrix.title")}
  >
    <div className="model-matrix-toolbar">
      <Button disabled={pending || benchmarkCombinations.length === 0} onClick={() => { void benchmark(benchmarkCombinations, t("modelMatrix.emptyBenchmark")) }} type="button">
        {pending ? t("modelMatrix.actions.benchmarking") : t("modelMatrix.actions.benchmarkAll")}
      </Button>
      <RefreshButton disabled={pending} label={t("modelMatrix.actions.refresh")} onClick={() => { void load() }} />
    </div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} /> : null}
    {notice ? <Notice message={notice} /> : null}
    {matrix && matrix.models.length === 0 ? <p className="empty-state">{t("modelMatrix.empty")}</p> : null}
    {matrix && matrix.models.length > 0 ? <div className="model-matrix-scroll">
      <Table aria-label={t("modelMatrix.tableLabel")} className="model-matrix">
        <TableHeader><TableRow><TableHead scope="col">{t("modelMatrix.labels.model")}</TableHead>{matrix.connections.map((connection) => <TableHead key={connection.connection_id} scope="col">{connection.name}</TableHead>)}</TableRow></TableHeader>
        <TableBody>{matrix.models.map((model) => <TableRow key={model.model_key}>
          <TableHead scope="row">{model.display_name}</TableHead>
          {matrix.connections.map((connection) => {
            const cell = model.connections.find((item) => item.connection_id === connection.connection_id)
            const canBenchmark = Boolean(cell?.available && cell.model_id && connection.verification.status === "passed")
            if (!cell?.available) return <TableCell className="model-matrix__cell model-matrix__cell--unavailable" key={connection.connection_id}>{t("modelMatrix.labels.unavailable")}</TableCell>
            return <TableCell className="model-matrix__cell" key={connection.connection_id}>
              <div className="model-matrix__cell-content">
                <strong>{cell.verification_status === "passed" ? `✓ ${t("modelMatrix.labels.available")}` : cell.verification_status === "failed" ? t("modelMatrix.labels.failed") : t("modelMatrix.labels.never")}</strong>
                <span className={cell.latency_class ? `latency--${cell.latency_class}` : undefined}>{cell.latency_ms === null ? t("modelMatrix.labels.noBenchmark") : `${Math.round(cell.latency_ms)}ms`}</span>
                <small>{t("modelMatrix.labels.price")}: <span>{cell.price_estimate === null ? t("modelMatrix.labels.notProvided") : cell.price_estimate}</span></small>
                <Button
                  aria-label={t("modelMatrix.actions.benchmarkFor", { model: model.display_name, provider: connection.name })}
                  disabled={pending || !canBenchmark}
                  onClick={() => { if (cell.model_id) void benchmark([{ connection_id: connection.connection_id, model_id: cell.model_id }], t("modelMatrix.emptyCombination")) }}
                  size="sm"
                  type="button"
                  variant="outline"
                >
                  {t("modelMatrix.actions.benchmark")}
                </Button>
              </div>
            </TableCell>
          })}
        </TableRow>)}</TableBody>
      </Table>
    </div> : null}
  </ManageDialog>
}

function collectBenchmarkCombinations(matrix: ModelMatrix): BenchmarkCombination[] {
  const passedConnections = new Set(
    matrix.connections
      .filter((connection) => connection.verification.status === "passed")
      .map((connection) => connection.connection_id),
  )
  return matrix.models.flatMap((model) => model.connections
    .filter((cell) => cell.available && cell.model_id && passedConnections.has(cell.connection_id))
    .map((cell) => ({ connection_id: cell.connection_id, model_id: cell.model_id ?? "" })))
}
