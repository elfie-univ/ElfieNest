import { Fragment, useEffect, useMemo, useRef, useState } from "react"

import {
  applyFoodUpdate,
  editFood,
  ownerFoods,
  previewFoodUpdate,
  rollbackFoods,
  type FoodCatalog,
  type FoodPreview,
  type FoodRecipe,
} from "../api/owner-foods"
import { ownerProviders, type ProviderView } from "../api/owner-providers"
import { ApiError } from "../api/http"
import { ConfirmDialog } from "./ConfirmDialog"
import { FoodPreviewDialog } from "./FoodPreviewDialog"
import { FoodRecipeEditor } from "./FoodRecipeEditor"
import { FoodRoleTable } from "./FoodRoleTable"
import { Notice } from "./Notice"
import type { SelectOption } from "./SelectField"

type PendingAction = "apply" | "preview" | "rollback" | "save" | null

export function OwnerFoodPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [catalog, setCatalog] = useState<FoodCatalog | null>(null)
  const [providers, setProviders] = useState<readonly ProviderView[]>([])
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set())
  const [editing, setEditing] = useState<FoodRecipe | null>(null)
  const [preview, setPreview] = useState<FoodPreview | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [applyConfirm, setApplyConfirm] = useState(false)
  const [rollbackConfirm, setRollbackConfirm] = useState(false)
  const [pending, setPending] = useState<PendingAction>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [foodWarnings, setFoodWarnings] = useState<Readonly<Record<string, readonly string[]>>>({})
  const previewButtonRef = useRef<HTMLButtonElement | null>(null)

  const load = async (): Promise<void> => {
    try {
      const [nextCatalog, nextProviders] = await Promise.all([ownerFoods(), ownerProviders()])
      setCatalog(nextCatalog)
      setProviders(nextProviders)
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "粮食目录加载失败")
    }
  }
  useEffect(() => { void load() }, [])
  const foods = catalog ? Object.values(catalog.foods) : []
  const modelOptions = useMemo(() => collectModelOptions(providers), [providers])

  const generatePreview = async (): Promise<void> => {
    setPending("preview")
    try {
      const next = await previewFoodUpdate(csrfToken)
      setPreview(next)
      setPreviewOpen(true)
      setNotice("已生成更新预览；关闭预览不会写入。")
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "无法生成粮食预览")
    } finally {
      setPending(null)
    }
  }
  const apply = async (): Promise<void> => {
    if (!preview) return
    setPending("apply")
    try {
      setCatalog(await applyFoodUpdate(preview, csrfToken))
      setPreview(null)
      setApplyConfirm(false)
      setNotice("粮食更新已应用。")
      setError(null)
    } catch (reason: unknown) {
      setApplyConfirm(false)
      if (reason instanceof ApiError && reason.status === 409) {
        setPreview(null)
        setPreviewOpen(false)
        setError("粮食候选已过期，请重新生成预览。")
      } else {
        setError(reason instanceof ApiError ? reason.message : "粮食更新没有应用")
      }
    } finally {
      setPending(null)
    }
  }
  const saveFood = async (food: FoodRecipe): Promise<void> => {
    setPending("save")
    try {
      const result = await editFood(food.key, food, csrfToken)
      setFoodWarnings((current) => ({ ...current, [food.key]: result.warnings }))
      setEditing(null)
      setNotice(result.warnings.length > 0 ? `${food.display_name} 已保存，但仍有验证警告。` : `${food.display_name} 已保存。`)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "粮食配置没有保存")
      throw reason
    } finally {
      setPending(null)
    }
  }
  const rollback = async (): Promise<void> => {
    setPending("rollback")
    try {
      setCatalog(await rollbackFoods(csrfToken))
      setRollbackConfirm(false)
      setNotice("粮食目录已回滚。")
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "没有可回滚的粮食版本")
    } finally {
      setPending(null)
    }
  }

  return <section className="manage-card manage-card--wide food-page">
    <div className="manage-head"><p>展开查看每个执行角色；人工编辑只改当前粮食，自动生成必须先预览差异。</p><button className="button button--quiet" disabled={pending !== null} onClick={() => { void load() }} type="button">重新读取</button></div>
    {error ? <Notice kind="error" message={error} /> : null}
    {notice ? <Notice message={notice} /> : null}
    {foods.length === 0 ? <div className="manager-empty-state"><h3>尚无粮食策略</h3><p>先生成更新预览，检查模型角色差异后再确认应用。</p></div> : <div className="food-table-wrap"><table className="food-table"><thead><tr><th>粮食</th><th>主模型</th><th>验证状态</th><th>来源 / 更新时间</th><th>操作</th></tr></thead><tbody>{foods.map((food) => {
      const isExpanded = expanded.has(food.key)
      const warnings = foodWarnings[food.key] ?? []
      return <Fragment key={food.key}>
        <tr key={food.key}>
          <td><strong>{food.display_name}</strong><small>{food.description}</small></td>
          <td>{food.primary.model || "未配置"}<small>{food.primary.reasoning_profile} · {food.primary.max_tokens} tokens</small></td>
          <td><span className={`status-badge status-badge--${food.validation_status}`}>{validationLabel(food.validation_status)}</span>{warnings.map((warning) => <small className="food-warning" key={warning}>{warning}</small>)}</td>
          <td>{food.source === "manual" ? "手动配置" : "自动生成"}<small>{catalog?.generated_at ? new Date(catalog.generated_at).toLocaleString() : "未记录"}</small></td>
          <td><div className="manage-actions"><button aria-label={`${isExpanded ? "收起" : "展开"} ${food.display_name}`} className="button button--quiet" onClick={() => setExpanded((current) => toggleKey(current, food.key))} type="button">{isExpanded ? "收起" : "展开"}</button><button aria-label={`编辑 ${food.display_name}`} className="button button--quiet" onClick={() => setEditing(food)} type="button">编辑</button></div></td>
        </tr>
        {isExpanded ? <tr className="food-role-row" key={`${food.key}-roles`}><td colSpan={5}><FoodRoleTable food={food} /></td></tr> : null}
      </Fragment>
    })}</tbody></table></div>}
    <div className="manage-actions food-page__actions"><button className="button" disabled={pending !== null} onClick={() => { void generatePreview() }} ref={previewButtonRef} type="button">{pending === "preview" ? "生成中…" : "生成更新预览"}</button><button className="button button--quiet" disabled={pending !== null} onClick={() => setRollbackConfirm(true)} type="button">回滚最近版本</button></div>
    <FoodRecipeEditor food={editing} modelOptions={modelOptions} onOpenChange={(open) => { if (!open) setEditing(null) }} onSave={saveFood} open={editing !== null} />
    <FoodPreviewDialog onContinue={() => { setPreviewOpen(false); setApplyConfirm(true) }} onOpenChange={(open) => { setPreviewOpen(open); if (!open) window.requestAnimationFrame(() => previewButtonRef.current?.focus()) }} open={previewOpen} preview={preview} />
    <ConfirmDialog confirmLabel="确认应用" description="只应用刚才预览的候选版本；候选过期时会要求重新生成。" onConfirm={() => { void apply() }} onOpenChange={setApplyConfirm} open={applyConfirm} pending={pending === "apply"} title="应用粮食更新" />
    <ConfirmDialog confirmLabel="确认回滚" danger description="当前目录将替换为最近一次历史版本。" onConfirm={() => { void rollback() }} onOpenChange={setRollbackConfirm} open={rollbackConfirm} pending={pending === "rollback"} title="回滚粮食版本" />
  </section>
}

function toggleKey(current: ReadonlySet<string>, key: string): ReadonlySet<string> {
  const next = new Set(current)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  return next
}

function collectModelOptions(providers: readonly ProviderView[]): readonly SelectOption[] {
  return providers.filter((provider) => provider.configured).flatMap((provider) => provider.models.map((model) => ({
    label: `${provider.name} · ${model.display_name || model.id}`,
    value: model.id.includes("/") ? model.id : `${provider.provider_id}/${model.id}`,
  })))
}

function validationLabel(status: string): string {
  if (status === "passed") return "通过"
  if (status === "warning") return "有警告"
  if (status === "failed") return "失败"
  return "未验证"
}
