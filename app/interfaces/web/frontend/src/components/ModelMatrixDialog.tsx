import { useEffect, useState } from "react"

import {
  benchmarkProviderModels,
  ownerModelMatrix,
  type BenchmarkCombination,
  type ModelMatrix,
} from "../api/owner-providers"
import { ApiError } from "../api/client"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"

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

  const benchmark = async (): Promise<void> => {
    if (benchmarkCombinations.length === 0) {
      setNotice("暂无已验证通过且可测速的模型。")
      return
    }
    setPending(true)
    try {
      const result = await benchmarkProviderModels(benchmarkCombinations.slice(0, 12), csrfToken)
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
    description="按模型查看已配置供应商的支持、验证和最近测速；未知价格不会估造。"
    onOpenChange={onOpenChange}
    open={open}
    title="支持模型与测速"
  >
    <div className="model-matrix-toolbar">
      <button className="button" disabled={pending || benchmarkCombinations.length === 0} onClick={() => { void benchmark() }} type="button">
        {pending ? "测速中…" : "批量测速"}
      </button>
      <button className="button button--quiet" disabled={pending} onClick={() => { void load() }} type="button">重新读取</button>
    </div>
    {error ? <Notice kind="error" message={error} /> : null}
    {notice ? <Notice message={notice} /> : null}
    {matrix && matrix.models.length === 0 ? <p className="empty-state">尚无已配置供应商声明的模型。</p> : null}
    {matrix && matrix.models.length > 0 ? <div className="model-matrix-scroll">
      <table aria-label="模型供应商矩阵" className="model-matrix">
        <thead><tr><th scope="col">模型</th>{matrix.providers.map((provider) => <th key={provider.provider_id} scope="col">{provider.name}</th>)}</tr></thead>
        <tbody>{matrix.models.map((model) => <tr key={model.model_id}>
          <th scope="row">{model.display_name}</th>
          {matrix.providers.map((provider) => {
            const cell = model.providers.find((item) => item.provider_id === provider.provider_id)
            if (!cell?.available) return <td className="model-matrix__cell model-matrix__cell--unavailable" key={provider.provider_id}>不支持</td>
            return <td className="model-matrix__cell" key={provider.provider_id}>
              <strong>{cell.verification_status === "passed" ? "✓ 可用" : cell.verification_status === "failed" ? "验证失败" : "未验证"}</strong>
              <span className={cell.latency_class ? `latency--${cell.latency_class}` : undefined}>{cell.latency_ms === null ? "未测速" : `${Math.round(cell.latency_ms)}ms`}</span>
              <small>价格：<span>{cell.price_estimate === null ? "未提供" : cell.price_estimate}</span></small>
            </td>
          })}
        </tr>)}</tbody>
      </table>
    </div> : null}
  </ManageDialog>
}

function collectBenchmarkCombinations(matrix: ModelMatrix): BenchmarkCombination[] {
  const passedProviders = new Set(
    matrix.providers
      .filter((provider) => provider.verification.status === "passed")
      .map((provider) => provider.provider_id),
  )
  return matrix.models.flatMap((model) => model.providers
    .filter((cell) => cell.available && passedProviders.has(cell.provider_id))
    .map((cell) => ({ provider_id: cell.provider_id, model_id: model.model_id })))
}
