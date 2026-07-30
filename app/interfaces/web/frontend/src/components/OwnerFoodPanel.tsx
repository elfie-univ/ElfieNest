import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Plus, Users } from "lucide-react"
import { Fragment, useEffect, useMemo, useState } from "react"

import {
  changeFoodLifecycle,
  createFood,
  deleteFood,
  editFood,
  ownerFoods,
  previewFoodUpdate,
  type FoodCatalog,
  type FoodPackage,
} from "../api/owner-foods"
import { ownerProviderConnections, type ProviderConnection } from "../api/owner-providers"
import { ApiError } from "../api/http"
import { ConfirmDialog } from "./ConfirmDialog"
import { FoodRecipeEditor } from "./FoodRecipeEditor"
import { FoodRoleTable } from "./FoodRoleTable"
import { FoodVisibilityDialog } from "./FoodVisibilityDialog"
import { ManageDialog } from "./ManageDialog"
import { Notice } from "./Notice"
import { RefreshButton } from "./RefreshButton"
import type { SelectFieldOption } from "./SelectField"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "./ui/table"

export function OwnerFoodPanel({ csrfToken }: { readonly csrfToken: string }) {
  const [catalog, setCatalog] = useState<FoodCatalog | null>(null)
  const [connections, setConnections] = useState<readonly ProviderConnection[]>([])
  const [editing, setEditing] = useState<FoodPackage | null>(null)
  const [visibility, setVisibility] = useState<FoodPackage | null>(null)
  const [generation, setGeneration] = useState<FoodPackage | null>(null)
  const [generationScope, setGenerationScope] = useState<ReadonlySet<string>>(new Set())
  const [allowRemote, setAllowRemote] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<FoodPackage | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = async (): Promise<void> => {
    try {
      const [foods, providers] = await Promise.all([ownerFoods(), ownerProviderConnections()])
      setCatalog(foods)
      setConnections(providers.filter((item) => item.enabled && !item.archived))
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "粮食目录加载失败")
    }
  }
  useEffect(() => { void load() }, [])
  const modelOptions = useMemo<readonly SelectFieldOption[]>(() => {
    if (!catalog) return []
    return catalog.eligible_models.map((model) => ({
      label: `${model.display_name}${model.local ? " · 本地" : ""}`,
      value: model.reference,
    }))
  }, [catalog])

  const save = async (food: FoodPackage): Promise<void> => {
    try {
      await editFood(food.key, {
        display_name: food.display_name,
        enabled: food.enabled,
        roles: food.roles,
      }, csrfToken)
      setEditing(null)
      setNotice(`${food.display_name} 已保存。`)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "粮食没有保存")
      throw reason
    }
  }
  const add = async (): Promise<void> => {
    setPending(true)
    try {
      const result = await createFood("新粮食套餐", csrfToken)
      setCatalog(result.catalog)
      setEditing(result.food)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "粮食创建失败")
    } finally { setPending(false) }
  }
  const generate = async (): Promise<void> => {
    if (!generation) return
    setPending(true)
    try {
      const preview = await previewFoodUpdate(
        generation.key,
        [...generationScope],
        generation.system_role === "emergency",
        allowRemote,
        csrfToken,
      )
      const candidate = {
        ...generation,
        display_name: preview.candidate.display_name,
        enabled: preview.candidate.enabled,
        roles: preview.candidate.roles,
      }
      setEditing(candidate)
      setGeneration(null)
      setNotice(`已生成 ${preview.changes.filter((item) => item.old_model !== item.new_model).length} 项差异；请人工确认后保存。${preview.warnings[0] ?? ""}`)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "自动生成失败")
    } finally { setPending(false) }
  }
  const lifecycle = async (food: FoodPackage, action: "enable" | "disable" | "archive" | "restore"): Promise<void> => {
    setPending(true)
    try {
      await changeFoodLifecycle(food.key, action, csrfToken)
      await load()
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "粮食状态没有更新")
    } finally { setPending(false) }
  }
  const remove = async (): Promise<void> => {
    if (!deleteTarget) return
    setPending(true)
    try {
      setCatalog(await deleteFood(deleteTarget.key, csrfToken))
      setDeleteTarget(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "粮食没有删除")
    } finally { setPending(false) }
  }

  return <section className="manage-card manage-card--wide food-page">
    <div className="manage-head">
      <div><h2>粮食套餐</h2><p>套餐只选择五种语义角色的模型；模型参数与验证事实由模型页面维护。</p></div>
      <div className="manage-actions"><Button disabled={pending} onClick={() => { void add() }} type="button"><Plus aria-hidden="true" />添加粮食</Button><RefreshButton disabled={pending} label="重新读取" onClick={() => { void load() }} /></div>
    </div>
    {error ? <Notice kind="error" message={error} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <Table aria-label="粮食套餐">
      <TableHeader><TableRow><TableHead>粮食</TableHead><TableHead>地域</TableHead><TableHead>主要模型</TableHead><TableHead>可见范围</TableHead><TableHead>状态</TableHead><TableHead>操作</TableHead></TableRow></TableHeader>
      <TableBody>{catalog?.packages.map((food) => <Fragment key={food.key}>
        <TableRow>
          <TableHead scope="row"><strong>{food.display_name}</strong><small>{food.system_role === "emergency" ? "系统保底粮" : food.system_role === "common" ? "系统常用粮" : "自定义粮食"}</small></TableHead>
          <TableCell>{localityLabel(food.locality)}</TableCell>
          <TableCell>{food.roles.primary?.model ?? "未配置"}<small>{food.roles.reasoning?.model ? `推理：${food.roles.reasoning.model}` : ""}</small></TableCell>
          <TableCell>{food.system_role ? "所有用户" : "指定用户"}</TableCell>
          <TableCell><span className={`status-badge status-badge--${food.health}`}>{food.health}</span></TableCell>
          <TableCell><div className="manage-actions">
            <Button onClick={() => setEditing(food)} type="button" variant="outline">编辑</Button>
            <Button onClick={() => { setGeneration(food); setGenerationScope(new Set(connections.map((item) => item.connection_id))); setAllowRemote(food.system_role !== "emergency") }} type="button" variant="outline">自动生成</Button>
            {!food.system_role ? <Button aria-label={`设置 ${food.display_name} 可见范围`} onClick={() => setVisibility(food)} title="可见范围" type="button" variant="outline"><Users aria-hidden="true" /></Button> : null}
            {food.archived
              ? <Button onClick={() => { void lifecycle(food, "restore") }} type="button" variant="outline">恢复</Button>
              : food.enabled
                ? <Button onClick={() => { void lifecycle(food, "disable") }} type="button" variant="outline">停用</Button>
                : <Button onClick={() => { void lifecycle(food, "enable") }} type="button" variant="outline">启用</Button>}
            {!food.system_role && !food.archived ? <Button onClick={() => { void lifecycle(food, "archive") }} type="button" variant="outline">归档</Button> : null}
            {!food.system_role && food.archived ? <Button onClick={() => setDeleteTarget(food)} type="button" variant="outline">删除</Button> : null}
          </div></TableCell>
        </TableRow>
        <TableRow><TableCell colSpan={6}>{editing?.key === food.key
          ? <FoodRecipeEditor food={editing} modelOptions={modelOptions} onCancel={() => setEditing(null)} onSave={save} />
          : <FoodRoleTable food={food} />}</TableCell></TableRow>
      </Fragment>)}</TableBody>
    </Table>
    {generation ? <ManageDialog description="选择一个、多个或全部已启用订阅。生成只使用最近验证通过的模型，并在保存前返回可编辑差异。" onOpenChange={(open) => { if (!open) setGeneration(null) }} open title={`自动生成 ${generation.display_name}`}>
      <div className="food-visibility-list">{connections.map((connection) => <label className="food-visibility-row" key={connection.connection_id}><Checkbox checked={generationScope.has(connection.connection_id)} onCheckedChange={(checked) => setGenerationScope((current) => toggle(current, connection.connection_id, checked === true))} /><span>{connection.alias}</span></label>)}</div>
      {generation.system_role === "emergency" ? <label className="food-visibility-row"><Checkbox checked={allowRemote} onCheckedChange={(checked) => setAllowRemote(checked === true)} /><span>允许远程模型（断网时可能不可用）</span></label> : null}
      <div className="manage-actions"><Button disabled={pending || generationScope.size === 0} onClick={() => { void generate() }} type="button">生成差异</Button><Button onClick={() => setGeneration(null)} type="button" variant="outline">取消</Button></div>
    </ManageDialog> : null}
    {visibility ? <FoodVisibilityDialog csrfToken={csrfToken} food={visibility} onClose={() => setVisibility(null)} onSaved={() => { setNotice("可见范围已保存。") }} /> : null}
    <ConfirmDialog confirmLabel="确认删除" danger description="只允许删除已归档且没有用户、精灵引用的自定义粮食。" onConfirm={() => { void remove() }} onOpenChange={(open) => { if (!open) setDeleteTarget(null) }} open={deleteTarget !== null} pending={pending} title="删除粮食" />
  </section>
}

function toggle(current: ReadonlySet<string>, key: string, enabled: boolean): ReadonlySet<string> {
  const next = new Set(current)
  if (enabled) next.add(key)
  else next.delete(key)
  return next
}

function localityLabel(value: string): string {
  return value === "local" ? "本地" : value === "remote" ? "远程" : value === "mixed" ? "混合" : "未配置"
}
