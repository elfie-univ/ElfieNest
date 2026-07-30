import { Button } from "@/components/ui/button"
import { useEffect, useState } from "react"

import {
  benchmarkProviderModels,
  ownerModelMatrix,
  validateAllProviderModels,
  type BenchmarkCombination,
  type ModelMatrix,
} from "../api/owner-providers"
import { ApiError } from "../api/client"
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
  const [matrix, setMatrix] = useState<ModelMatrix | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const load = async (): Promise<void> => {
    try {
      setMatrix(await ownerModelMatrix())
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "模型矩阵加载失败")
    }
  }
  useEffect(() => {
    if (open) void load()
  }, [open])

  const benchmarkCombinations = matrix ? collectBenchmarkCombinations(matrix) : []

  const validateAll = async (): Promise<void> => {
    setPending(true)
    try {
      const result = await validateAllProviderModels(csrfToken)
      setNotice(`验证完成，已生成完整报告 ${result.run_id}。`)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "全部验证失败")
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
      setNotice(`测速完成：${passed} 个成功，${result.results.length - passed} 个失败。`)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "模型测速失败")
    } finally {
      setPending(false)
    }
  }

  return <ManageDialog
    contentClassName="model-matrix-dialog"
    description="按模型查看各订阅连接的支持、验证和最近测速；未知价格不会估造。"
    onOpenChange={onOpenChange}
    open={open}
    title="支持模型与测速"
  >
    <div className="model-matrix-toolbar">
      <Button disabled={pending} onClick={() => { void validateAll() }} type="button">
        {pending ? "验证中…" : "验证全部"}
      </Button>
      <RefreshButton disabled={pending} label="重新读取" onClick={() => { void load() }} />
    </div>
    {error ? <Notice kind="error" message={error} /> : null}
    {notice ? <Notice message={notice} /> : null}
    {matrix && matrix.models.length === 0 ? <p className="empty-state">尚无已配置供应商声明的模型。</p> : null}
    {matrix && matrix.models.length > 0 ? <div className="model-matrix-scroll">
      <Table aria-label="模型供应商矩阵" className="model-matrix">
        <TableHeader><TableRow><TableHead scope="col">模型</TableHead>{matrix.connections.map((connection) => <TableHead key={connection.connection_id} scope="col">{connection.name}</TableHead>)}</TableRow></TableHeader>
        <TableBody>{matrix.models.map((model) => <TableRow key={model.model_key}>
          <TableHead scope="row">{model.display_name}</TableHead>
          {matrix.connections.map((connection) => {
            const cell = model.connections.find((item) => item.connection_id === connection.connection_id)
            const canBenchmark = Boolean(cell?.available && cell.model_id && connection.verification.status === "passed")
            if (!cell?.available) return <TableCell className="model-matrix__cell model-matrix__cell--unavailable" key={connection.connection_id}>不支持</TableCell>
            return <TableCell className="model-matrix__cell" key={connection.connection_id}>
              <div className="model-matrix__cell-content">
                <strong>{cell.verification_status === "passed" ? "✓ 可用" : cell.verification_status === "failed" ? "验证失败" : "未验证"}</strong>
                <span className={cell.latency_class ? `latency--${cell.latency_class}` : undefined}>{cell.latency_ms === null ? "未测速" : `${Math.round(cell.latency_ms)}ms`}</span>
                <small>价格：<span>{cell.price_estimate === null ? "未提供" : cell.price_estimate}</span></small>
                <Button
                  aria-label={`测速 ${connection.name} ${model.display_name}`}
                  disabled={pending || !canBenchmark}
                  onClick={() => { if (cell.model_id) void benchmark([{ connection_id: connection.connection_id, model_id: cell.model_id }], "这个模型组合尚不可测速。") }}
                  size="sm"
                  type="button"
                  variant="outline"
                >
                  测速
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
