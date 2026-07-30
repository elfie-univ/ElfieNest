import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  ownerElfies,
  ownerUsers,
  type OwnerElfie,
  type OwnerElfieFilters,
  type OwnerUser,
} from "../api/client"
import { resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { compareLocalizedText, currentLocale } from "../i18n/format"
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
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [users, setUsers] = useState<readonly OwnerUser[]>([])
  const [allElfies, setAllElfies] = useState<readonly OwnerElfie[]>([])
  const [elfies, setElfies] = useState<readonly OwnerElfie[]>([])
  const [selection, setSelection] = useState<FilterSelection>(INITIAL_SELECTION)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [mockMode, setMockMode] = useState(false)

  const showDemoData = (nextSelection: FilterSelection): void => {
    setUsers(MOCK_USERS)
    setAllElfies(MOCK_ELFIES)
    setElfies(filterMockElfies(nextSelection))
    setMockMode(true)
    onCountChange(MOCK_ELFIES.length)
    setError(null)
    setNotice(t("elfies.notices.demo"))
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
    } catch {
      showDemoData(nextSelection)
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
  const species = [...new Set(allElfies.map((elfie) => elfie.profile.species_id))].sort((left, right) => compareLocalizedText(left, right, locale))
  const foods = [...new Set(allElfies.map((elfie) => elfie.food_policy.default_food))].sort((left, right) => compareLocalizedText(left, right, locale))
  const states = [...new Set(allElfies.map((elfie) => elfie.profile.embodiment.state))].sort((left, right) => compareLocalizedText(left, right, locale))
  const orderedUsers = [...users].sort((left, right) => compareLocalizedText(left.username, right.username, locale))
  const orderedElfies = [...elfies].sort((left, right) => compareLocalizedText(left.profile.name, right.profile.name, locale))

  return <section className="manage-card manage-card--wide">
    <div className="manage-head">
      <div>
        <h2>{t("elfies.title")}</h2>
        <p>{t("elfies.description")}</p>
      </div>
      <RefreshButton label={t("users.actions.refresh")} onClick={() => { void load(selection) }} />
    </div>
    <div className="manage-filters">
      <SelectField
        label={t("elfies.filters.owner")}
        onValueChange={(value) => update("ownerAccountId", value)}
        options={[
          { label: t("elfies.filters.allUsers"), value: ALL_USERS },
          ...orderedUsers.map((user) => ({ label: user.username, value: user.account_id })),
        ]}
        value={selection.ownerAccountId}
      />
      <SelectField
        label={t("elfies.filters.species")}
        onValueChange={(value) => update("speciesId", value)}
        options={[
          { label: t("elfies.filters.allSpecies"), value: ALL_SPECIES },
          ...species.map((value) => ({ label: value, value })),
        ]}
        value={selection.speciesId}
      />
      <SelectField
        label={t("elfies.filters.food")}
        onValueChange={(value) => update("foodKey", value)}
        options={[
          { label: t("elfies.filters.allFoods"), value: ALL_FOODS },
          ...foods.map((value) => ({ label: value, value })),
        ]}
        value={selection.foodKey}
      />
      <SelectField
        label={t("elfies.filters.status")}
        onValueChange={(value) => update("embodimentState", value)}
        options={[
          { label: t("elfies.filters.allStates"), value: ALL_STATES },
          ...states.map((value) => ({ label: value, value })),
        ]}
        value={selection.embodimentState}
      />
    </div>
    {error ? <Notice kind="error" message={resolveLocalizedError(error, locale) ?? t("errors.save")} /> : null}
    {notice ? <Notice message={notice} /> : null}
    <div className="elfie-id-grid">
      {orderedElfies.length === 0
        ? <p className="empty">{t("elfies.empty")}</p>
        : orderedElfies.map((elfie) => <ElfieIdentityCard
          csrfToken={csrfToken}
          elfie={elfie}
          key={elfie.elfie_id}
          mockMode={mockMode}
          onError={setError}
          onSaved={async () => {
            setNotice(t("elfies.notices.foodSaved", { name: elfie.profile.name }))
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
