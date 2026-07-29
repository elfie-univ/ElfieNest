import { Button } from "@/components/ui/button"
import { Plus, Trash2, Users } from "lucide-react"
import { Fragment, useEffect, useMemo, useRef, useState } from "react"

import {
  applyFoodUpdate,
  createFood,
  deleteFood,
  editFood,
  ownerFoods,
  previewFoodUpdate,
  rollbackFoods,
  updateFoodSettings,
  type FoodCatalog,
  type FoodPreview,
  type FoodRecipe,
} from "../api/owner-foods"
import {
  ownerProviderConnections,
  type ProviderConnection,
} from "../api/owner-providers"
import { ApiError } from "../api/http"
import { ConfirmDialog } from "./ConfirmDialog"
import { FoodPreviewDialog } from "./FoodPreviewDialog"
import { FoodRecipeEditor } from "./FoodRecipeEditor"
import { FoodRoleTable } from "./FoodRoleTable"
import { FoodVisibilityDialog } from "./FoodVisibilityDialog"
import { Notice } from "./Notice"
import { RefreshButton } from "./RefreshButton"
import type { SelectFieldOption } from "./SelectField"
import { SelectField } from "./SelectField"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table"

type PendingAction = "apply" | "create" | "delete" | "preview" | "rollback" | "save" | "settings" | null
const NO_FALLBACK = "__none__"

export function OwnerFoodPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [catalog, setCatalog] = useState<FoodCatalog | null>(null)
  const [providers, setProviders] = useState<readonly ProviderConnection[]>([])
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set())
  const [editing, setEditing] = useState<FoodRecipe | null>(null)
  const [visibilityFood, setVisibilityFood] = useState<FoodRecipe | null>(null)
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
      const [nextCatalog, nextProviders] = await Promise.all([ownerFoods(), ownerProviderConnections()])
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
  const foodOptions = foods.map((food) => ({
    label: `${food.display_name}${food.local_only ? " · 本地" : ""}`,
    value: food.key,
  }))

  const createPackage = async (): Promise<void> => {
    const model = firstModelReference(providers)
    if (!model) {
      setError("请先配置至少一个可用模型。")
      return
    }
    setPending("create")
    try {
      const result = await createFood({
        display_name: "新粮食套餐",
        description: "",
        primary: defaultProfile(model),
      }, csrfToken)
      setCatalog(result.catalog)
      setEditing(result.food)
      setExpanded((current) => addKey(current, result.food.key))
      setNotice("新套餐已创建，请继续完善名称和模型角色。")
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "粮食套餐创建失败")
    } finally {
      setPending(null)
    }
  }
  const saveSettings = async (defaultFood: string, fallbackFood: string): Promise<void> => {
    setPending("settings")
    try {
      const result = await updateFoodSettings(defaultFood, fallbackFood, csrfToken)
      setCatalog(result.catalog)
      setNotice(result.warnings[0] ?? "全局粮食选择已保存。")
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "全局粮食选择没有保存")
    } finally {
      setPending(null)
    }
  }
  const removeFood = async (food: FoodRecipe): Promise<void> => {
    setPending("delete")
    try {
      setCatalog(await deleteFood(food.key, csrfToken))
      setEditing((current) => current?.key === food.key ? null : current)
      setNotice(`${food.display_name} 已删除。`)
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "粮食套餐没有删除")
    } finally {
      setPending(null)
    }
  }

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

  return <section aria-label="粮食策略管理" className="manage-card manage-card--wide food-page">
    <div className="manage-head">
      <p>展开查看每个执行角色；人工编辑只改当前粮食，自动生成必须先预览差异。</p>
      <div aria-label="粮食页面动作" className="manage-actions food-page__header-actions" role="group">
        <RefreshButton disabled={pending !== null} label="重新读取" onClick={() => { void load() }} />
        <Button disabled={pending !== null} onClick={() => { void createPackage() }} type="button"><Plus aria-hidden="true" />新建套餐</Button>
        <Button disabled={pending !== null} onClick={() => { void generatePreview() }} ref={previewButtonRef} type="button">{pending === "preview" ? "生成中…" : "生成更新预览"}</Button>
        <Button variant="outline" disabled={pending !== null} onClick={() => setRollbackConfirm(true)} type="button">回滚最近版本</Button>
      </div>
    </div>
    {error ? <Notice kind="error" message={error} /> : null}
    {notice ? <Notice message={notice} /> : null}
    {catalog && foods.length > 0 ? <div className="food-global-settings">
      <SelectField disabled={pending !== null} label="默认粮" onValueChange={(value) => { void saveSettings(value, catalog.fallback_food) }} options={foodOptions} value={catalog.default_food} />
      <SelectField disabled={pending !== null} label="保底粮" onValueChange={(value) => { void saveSettings(catalog.default_food, value === NO_FALLBACK ? "" : value) }} options={[{ label: "不设置", value: NO_FALLBACK }, ...foodOptions]} value={catalog.fallback_food || NO_FALLBACK} />
    </div> : null}
    {foods.length === 0 ? <div className="manage-empty-state"><h3>尚无粮食策略</h3><p>先生成更新预览，检查模型角色差异后再确认应用。</p></div> : <div className="food-table-wrap"><Table aria-label="粮食策略" className="food-table"><TableHeader><TableRow><TableHead scope="col">粮食</TableHead><TableHead scope="col">主模型</TableHead><TableHead scope="col">验证状态</TableHead><TableHead scope="col">来源 / 更新时间</TableHead><TableHead scope="col">操作</TableHead></TableRow></TableHeader><TableBody>{foods.map((food) => {
      const isExpanded = expanded.has(food.key)
      const warnings = foodWarnings[food.key] ?? []
      return <Fragment key={food.key}>
        <TableRow key={food.key}>
          <TableHead scope="row"><strong>{food.display_name}</strong><small>{food.description}</small></TableHead>
          <TableCell>{food.primary.model || "未配置"}<small>{food.primary.reasoning_profile} · {food.primary.max_tokens} tokens</small></TableCell>
          <TableCell><span className={`status-badge status-badge--${food.validation_status}`}>{validationLabel(food.validation_status)}</span>{warnings.map((warning) => <small className="food-warning" key={warning}>{warning}</small>)}</TableCell>
          <TableCell>{food.source === "manual" ? "手动配置" : "自动生成"}<small>{food.local_only ? "全本地" : "含远程模型"} · {catalog?.generated_at ? new Date(catalog.generated_at).toLocaleString() : "未记录"}</small></TableCell>
          <TableCell><div className="manage-actions"><Button variant="outline" aria-label={`${isExpanded ? "收起" : "展开"} ${food.display_name}`} onClick={() => setExpanded((current) => toggleKey(current, food.key))} type="button">{isExpanded ? "收起" : "展开"}</Button><Button variant="outline" aria-label={`编辑 ${food.display_name}`} onClick={() => { setEditing(food); setExpanded((current) => addKey(current, food.key)) }} type="button">编辑</Button><Button variant="outline" aria-label={`分配 ${food.display_name}`} onClick={() => setVisibilityFood(food)} title="分配给用户" type="button"><Users aria-hidden="true" /></Button><Button variant="outline" aria-label={`删除 ${food.display_name}`} disabled={pending !== null || food.key === catalog?.default_food || food.key === catalog?.fallback_food} onClick={() => { void removeFood(food) }} title="删除套餐" type="button"><Trash2 aria-hidden="true" /></Button></div></TableCell>
        </TableRow>
        {isExpanded ? <TableRow className="food-role-row" key={`${food.key}-roles`}><TableCell colSpan={5}>{editing?.key === food.key
          ? <FoodRecipeEditor food={editing} modelOptions={modelOptions} onCancel={() => setEditing(null)} onSave={saveFood} />
          : <FoodRoleTable food={food} />}</TableCell></TableRow> : null}
      </Fragment>
    })}</TableBody></Table></div>}
    <FoodPreviewDialog onContinue={() => { setPreviewOpen(false); setApplyConfirm(true) }} onOpenChange={(open) => { setPreviewOpen(open); if (!open) window.requestAnimationFrame(() => previewButtonRef.current?.focus()) }} open={previewOpen} preview={preview} />
    {visibilityFood ? <FoodVisibilityDialog csrfToken={csrfToken} food={visibilityFood} onClose={() => setVisibilityFood(null)} onSaved={() => setNotice(`${visibilityFood.display_name} 的用户范围已保存。`)} /> : null}
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

function addKey(current: ReadonlySet<string>, key: string): ReadonlySet<string> {
  const next = new Set(current)
  next.add(key)
  return next
}

function collectModelOptions(providers: readonly ProviderConnection[]): readonly SelectFieldOption[] {
  return providers.filter((provider) => provider.enabled && provider.models.some((model) => !model.hidden)).map((provider) => ({
    label: provider.alias,
    options: provider.models.filter((model) => !model.hidden).map((model) => ({
      group: provider.alias,
      label: `${provider.alias} · ${model.display_name || model.id}`,
      value: `${provider.connection_id}/${model.id}`,
    })),
  }))
}

function validationLabel(status: string): string {
  if (status === "passed") return "通过"
  if (status === "warning") return "有警告"
  if (status === "failed") return "失败"
  return "未验证"
}

function firstModelReference(providers: readonly ProviderConnection[]): string | null {
  for (const provider of providers) {
    const firstModel = provider.models.find((model) => !model.hidden)
    if (!provider.enabled || !firstModel) continue
    return `${provider.connection_id}/${firstModel.id}`
  }
  return null
}

function defaultProfile(model: string) {
  return {
    model,
    reasoning_profile: "balanced",
    max_tokens: 1500,
    temperature: 0.7,
    provider_options: {},
  }
}
