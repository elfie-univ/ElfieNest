import { useEffect, useState } from "react"

import {
  ApiError,
  ownerElfies,
  ownerUsers,
  type OwnerElfie,
  type OwnerElfieFilters,
  type OwnerUser,
} from "../api/client"
import { ElfieFoodPolicyDialog } from "./ElfieFoodPolicyDialog"
import { ElfieIdentityCard } from "./ElfieIdentityCard"
import { Notice } from "./Notice"
import { SelectField } from "./SelectField"

const ALL_USERS = "all-users"
const ALL_SPECIES = "all-species"
const ALL_FOODS = "all-foods"
const ALL_STATES = "all-states"

type FilterSelection = {
  readonly ownerUserId: string
  readonly speciesId: string
  readonly foodKey: string
  readonly embodimentState: string
}

const INITIAL_SELECTION: FilterSelection = {
  ownerUserId: ALL_USERS,
  speciesId: ALL_SPECIES,
  foodKey: ALL_FOODS,
  embodimentState: ALL_STATES,
}

type OwnerElfieOverviewProps = {
  readonly csrfToken: string
  readonly onCountChange: (count: number) => void
}

function toApiFilters(selection: FilterSelection): OwnerElfieFilters {
  return {
    ...(selection.ownerUserId === ALL_USERS ? {} : { ownerUserId: selection.ownerUserId }),
    ...(selection.speciesId === ALL_SPECIES ? {} : { speciesId: selection.speciesId }),
    ...(selection.foodKey === ALL_FOODS ? {} : { foodKey: selection.foodKey }),
    ...(selection.embodimentState === ALL_STATES
      ? {}
      : { embodimentState: selection.embodimentState }),
  }
}

function hasFilters(filters: OwnerElfieFilters): boolean {
  return Object.values(filters).some((value) => value !== undefined)
}

export function OwnerElfieOverview({ csrfToken, onCountChange }: OwnerElfieOverviewProps) {
  const [users, setUsers] = useState<readonly OwnerUser[]>([])
  const [allElfies, setAllElfies] = useState<readonly OwnerElfie[]>([])
  const [elfies, setElfies] = useState<readonly OwnerElfie[]>([])
  const [selection, setSelection] = useState<FilterSelection>(INITIAL_SELECTION)
  const [editing, setEditing] = useState<OwnerElfie | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = async (nextSelection: FilterSelection): Promise<void> => {
    try {
      const filters = toApiFilters(nextSelection)
      const allPromise = ownerElfies({})
      const filteredPromise = hasFilters(filters) ? ownerElfies(filters) : allPromise
      const [loadedUsers, loadedAll, loadedElfies] = await Promise.all([
        ownerUsers(),
        allPromise,
        filteredPromise,
      ])
      setUsers(loadedUsers)
      setAllElfies(loadedAll)
      setElfies(loadedElfies)
      onCountChange(loadedAll.length)
      setError(null)
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "精灵总览加载失败")
    }
  }

  const reloadElfies = async (): Promise<void> => {
    const filters = toApiFilters(selection)
    const allPromise = ownerElfies({})
    const filteredPromise = hasFilters(filters) ? ownerElfies(filters) : allPromise
    const [loadedAll, loadedElfies] = await Promise.all([allPromise, filteredPromise])
    setAllElfies(loadedAll)
    setElfies(loadedElfies)
    onCountChange(loadedAll.length)
  }

  useEffect(() => {
    void load(selection)
  }, [selection])

  const update = (key: keyof FilterSelection, value: string): void => {
    setSelection((current) => ({ ...current, [key]: value }))
  }
  const species = [...new Set(allElfies.map((elfie) => elfie.profile.species_id))]
  const foods = [...new Set(allElfies.map((elfie) => elfie.food_policy.default_food))]
  const states = [...new Set(allElfies.map((elfie) => elfie.profile.embodiment.state))]

  return <section className="manage-card manage-card--wide">
    <div className="manage-head">
      <div>
        <h2>全部精灵</h2>
        <p>以可读身份证卡查看公开运营信息；只有粮食策略可由 Owner 在这里修改。</p>
      </div>
      <button className="button button--quiet" onClick={() => { void load(selection) }} type="button">
        刷新
      </button>
    </div>
    <div className="manager-filters">
      <label>所属用户<SelectField
        ariaLabel="按用户筛选精灵"
        onValueChange={(value) => update("ownerUserId", value)}
        options={[
          { label: "全部用户", value: ALL_USERS },
          ...users.map((user) => ({ label: user.username, value: String(user.id) })),
        ]}
        value={selection.ownerUserId}
      /></label>
      <label>物种<SelectField
        ariaLabel="按物种筛选精灵"
        onValueChange={(value) => update("speciesId", value)}
        options={[
          { label: "全部物种", value: ALL_SPECIES },
          ...species.map((value) => ({ label: value, value })),
        ]}
        value={selection.speciesId}
      /></label>
      <label>粮食<SelectField
        ariaLabel="按粮食筛选精灵"
        onValueChange={(value) => update("foodKey", value)}
        options={[
          { label: "全部粮食", value: ALL_FOODS },
          ...foods.map((value) => ({ label: value, value })),
        ]}
        value={selection.foodKey}
      /></label>
      <label>具身状态<SelectField
        ariaLabel="按具身状态筛选精灵"
        onValueChange={(value) => update("embodimentState", value)}
        options={[
          { label: "全部状态", value: ALL_STATES },
          ...states.map((value) => ({ label: value, value })),
        ]}
        value={selection.embodimentState}
      /></label>
    </div>
    {error ? <Notice kind="error" message={error} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <div className="elfie-id-grid">
      {elfies.length === 0
        ? <p className="empty">没有符合筛选条件的精灵。</p>
        : elfies.map((elfie) => <ElfieIdentityCard
          elfie={elfie}
          key={elfie.elfie_id}
          onEdit={() => setEditing(elfie)}
        />)}
    </div>
    {editing ? <ElfieFoodPolicyDialog
      csrfToken={csrfToken}
      elfie={editing}
      onClose={() => setEditing(null)}
      onSaved={async () => {
        setNotice(`${editing.profile.name} 的粮食策略已更新。`)
        setEditing(null)
        await reloadElfies()
      }}
    /> : null}
  </section>
}
