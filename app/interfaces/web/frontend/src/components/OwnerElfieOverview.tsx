import { useEffect, useState } from "react"

import {
  ApiError,
  ownerElfies,
  ownerUsers,
  type OwnerElfie,
  type OwnerElfieFilters,
  type OwnerUser,
} from "../api/client"
import { ElfieIdentityCard } from "./ElfieIdentityCard"
import { Notice } from "./Notice"
import { RefreshButton } from "./RefreshButton"
import { SelectField } from "./SelectField"
import { MOCK_ELFIES, MOCK_USERS } from "./owner-card-mock-data"

const ALL_USERS = "all-users"
const ALL_SPECIES = "all-species"
const ALL_FOODS = "all-foods"
const ALL_STATES = "all-states"

type FilterSelection = {
  readonly ownerAccountId: string
  readonly speciesId: string
  readonly foodKey: string
  readonly embodimentState: string
}

const INITIAL_SELECTION: FilterSelection = {
  ownerAccountId: ALL_USERS,
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
    ...(selection.ownerAccountId === ALL_USERS ? {} : { ownerAccountId: selection.ownerAccountId }),
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
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [mockMode, setMockMode] = useState(false)

  const showDemoData = (nextSelection: FilterSelection, reason?: unknown): void => {
    setUsers(MOCK_USERS)
    setAllElfies(MOCK_ELFIES)
    setElfies(filterMockElfies(nextSelection))
    setMockMode(true)
    onCountChange(MOCK_ELFIES.length)
    setError(null)
    setNotice(reason instanceof ApiError ? `后端暂不可用，当前显示演示数据：${reason.message}` : "后端暂不可用，当前显示演示数据")
  }

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
      if (loadedAll.length === 0) {
        showDemoData(nextSelection)
        return
      }
      setUsers(loadedUsers)
      setAllElfies(loadedAll)
      setElfies(loadedElfies)
      setMockMode(false)
      onCountChange(loadedAll.length)
      setError(null)
      setNotice(null)
    } catch (reason: unknown) {
      showDemoData(nextSelection, reason)
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
        <p>以可读身份证卡查看<span className="manage-copy__phrase">公开运营信息</span>；只有粮食策略可由 <span className="manage-copy__phrase">Owner 在这里修改</span>。</p>
      </div>
      <RefreshButton label="刷新" onClick={() => { void load(selection) }} />
    </div>
    <div className="manage-filters">
      <SelectField
        label="所属用户"
        onValueChange={(value) => update("ownerAccountId", value)}
        options={[
          { label: "全部用户", value: ALL_USERS },
          ...users.map((user) => ({ label: user.username, value: user.account_id })),
        ]}
        value={selection.ownerAccountId}
      />
      <SelectField
        label="物种"
        onValueChange={(value) => update("speciesId", value)}
        options={[
          { label: "全部物种", value: ALL_SPECIES },
          ...species.map((value) => ({ label: value, value })),
        ]}
        value={selection.speciesId}
      />
      <SelectField
        label="粮食"
        onValueChange={(value) => update("foodKey", value)}
        options={[
          { label: "全部粮食", value: ALL_FOODS },
          ...foods.map((value) => ({ label: value, value })),
        ]}
        value={selection.foodKey}
      />
      <SelectField
        label="具身状态"
        onValueChange={(value) => update("embodimentState", value)}
        options={[
          { label: "全部状态", value: ALL_STATES },
          ...states.map((value) => ({ label: value, value })),
        ]}
        value={selection.embodimentState}
      />
    </div>
    {error ? <Notice kind="error" message={error} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <div className="elfie-id-grid">
      {elfies.length === 0
        ? <p className="empty">没有符合筛选条件的精灵。</p>
        : elfies.map((elfie) => <ElfieIdentityCard
          csrfToken={csrfToken}
          elfie={elfie}
          key={elfie.elfie_id}
          mockMode={mockMode}
          onError={setError}
          onSaved={async () => {
            setNotice(`${elfie.profile.name} 的粮食策略已更新。`)
            await reloadElfies()
          }}
        />)}
    </div>
  </section>
}

function filterMockElfies(selection: FilterSelection): readonly OwnerElfie[] {
  return MOCK_ELFIES.filter((elfie) =>
    (selection.ownerAccountId === ALL_USERS || elfie.owner.account_id === selection.ownerAccountId)
    && (selection.speciesId === ALL_SPECIES || elfie.profile.species_id === selection.speciesId)
    && (selection.foodKey === ALL_FOODS || elfie.food_policy.default_food === selection.foodKey)
    && (selection.embodimentState === ALL_STATES || elfie.profile.embodiment.state === selection.embodimentState),
  )
}
