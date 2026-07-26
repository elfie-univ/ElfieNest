import { useEffect, useState } from "react"

import { ApiError, ownerElfies, ownerUsers, type OwnerElfie, type OwnerElfieFilters, type OwnerUser } from "../api/client"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"

const INITIAL_FILTERS: OwnerElfieFilters = {}

type OwnerElfieOverviewProps = {
  readonly onCountChange: (count: number) => void
}

function filterValue(value: string): string | undefined {
  const normalized = value.trim()
  return normalized === "" ? undefined : normalized
}

export function OwnerElfieOverview({ onCountChange }: OwnerElfieOverviewProps) {
  const [users, setUsers] = useState<readonly OwnerUser[]>([])
  const [elfies, setElfies] = useState<readonly OwnerElfie[]>([])
  const [filters, setFilters] = useState<OwnerElfieFilters>(INITIAL_FILTERS)
  const [selected, setSelected] = useState<OwnerElfie | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = async (nextFilters: OwnerElfieFilters): Promise<void> => {
    try {
      const [loadedUsers, loadedElfies] = await Promise.all([ownerUsers(), ownerElfies(nextFilters)])
      setUsers(loadedUsers)
      setElfies(loadedElfies)
      onCountChange(loadedElfies.length)
      setSelected((current) => loadedElfies.find((entry) => entry.elfie_id === current?.elfie_id) ?? null)
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "精灵总览加载失败")
    }
  }

  useEffect(() => { void load(filters) }, [filters])
  const update = (key: keyof OwnerElfieFilters, value: string): void => {
    setFilters((current) => ({ ...current, [key]: filterValue(value) }))
  }

  return <section className="manage-card manage-card--wide">
    <div className="manage-head"><div><h2>全部精灵</h2><p>仅查看全局公开摘要；这里没有聊天、领养、归属分配或私有档案编辑。</p></div><button className="button button--quiet" onClick={() => { void load(filters) }} type="button">刷新</button></div>
    <div className="manager-filters">
      <label>所属用户<SelectField ariaLabel="按用户筛选精灵" onValueChange={(value) => update("ownerUserId", value)} options={[{ label: "全部用户", value: "" }, ...users.map((user) => ({ label: user.username, value: String(user.id) }))]} value={filters.ownerUserId ?? ""} /></label>
      <label>物种<input aria-label="按物种筛选精灵" onChange={(event) => update("speciesId", event.target.value)} placeholder="例如 fox" value={filters.speciesId ?? ""} /></label>
      <label>粮食<input aria-label="按粮食筛选精灵" onChange={(event) => update("foodKey", event.target.value)} placeholder="例如 daily" value={filters.foodKey ?? ""} /></label>
      <label>具身状态<input aria-label="按具身状态筛选精灵" onChange={(event) => update("embodimentState", event.target.value)} placeholder="例如 offline" value={filters.embodimentState ?? ""} /></label>
    </div>
    {error && <Notice kind="error" message={error} />}
    <div className="elfie-summary-grid">{elfies.length === 0 ? <p className="empty">没有符合筛选条件的精灵。</p> : elfies.map((elfie) => <button className="elfie-summary" key={elfie.elfie_id} onClick={() => setSelected(elfie)} type="button"><strong>{elfie.profile.name}</strong><span>{elfie.profile.species_id} · {elfie.owner.username}</span><small>{elfie.profile.embodiment.state} · {elfie.food_policy.default_food}</small></button>)}</div>
    {selected && <dl className="manager-detail"><div><dt>所属用户</dt><dd>{selected.owner.username}</dd></div><div><dt>3D 外观</dt><dd>{Object.entries(selected.profile.appearance).map(([key, value]) => `${key}: ${String(value)}`).join(" · ") || "尚无公开摘要"}</dd></div><div><dt>五大人格</dt><dd>{Object.entries(selected.profile.big_five).map(([key, value]) => `${key}: ${value}`).join(" · ") || "尚无公开摘要"}</dd></div><div><dt>精灵巢位置</dt><dd>{selected.profile.nest.room_name ?? "尚未进入精灵巢"} · {selected.profile.nest.bed_name ?? "未设置家位"}</dd></div></dl>}
  </section>
}
