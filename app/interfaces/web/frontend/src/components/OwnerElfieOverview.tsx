import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  adminElfies,
  elfieFoodPolicy,
  embodimentSessions,
  ownerRooms,
  ownerUsers,
  type OwnerUser,
} from "../api/client"
import { compareAccountListOrder } from "../api/roles"
import { describeApiError, resolveLocalizedError, type LocalizedErrorState } from "../i18n/errors"
import { compareLocalizedText, currentLocale } from "../i18n/format"
import { ElfieIdentityCard } from "./ElfieIdentityCard"
import { Notice } from "./Notice"
import { RefreshButton } from "./RefreshButton"
import { SelectField } from "./SelectField"
import { useToast } from "./ui/toast"
import { composeManagedElfies, type ManagedElfie } from "./managed-elfie"

const ALL_USERS = "all-users"
const ALL_SPECIES = "all-species"
const ALL_FOODS = "all-foods"
const ALL_STATES = "all-states"

type FilterSelection = {
  readonly ownerUserId: number | null
  readonly speciesId: string
  readonly foodKey: string
  readonly embodimentState: string
}

const INITIAL_SELECTION: FilterSelection = {
  ownerUserId: null,
  speciesId: ALL_SPECIES,
  foodKey: ALL_FOODS,
  embodimentState: ALL_STATES,
}

type OwnerElfieOverviewProps = {
  readonly csrfToken: string
  readonly onCountChange: (count: number) => void
}

function compareElfieId(left: ManagedElfie, right: ManagedElfie): number {
  return Number.parseInt(left.profile.elfie_id, 10) - Number.parseInt(right.profile.elfie_id, 10)
}

function matchesSelection(elfie: ManagedElfie, selection: FilterSelection): boolean {
  return (selection.ownerUserId === null || elfie.owner.user_id === selection.ownerUserId)
    && (selection.speciesId === ALL_SPECIES || elfie.profile.species_id === selection.speciesId)
    && (selection.foodKey === ALL_FOODS || elfie.foodPolicy.effective_main_food_id === selection.foodKey)
    && (selection.embodimentState === ALL_STATES || elfie.embodiment.state === selection.embodimentState)
}

export function OwnerElfieOverview({ csrfToken, onCountChange }: OwnerElfieOverviewProps) {
  const { i18n, t } = useTranslation("manage")
  const locale = currentLocale(i18n)
  const [users, setUsers] = useState<readonly OwnerUser[] | null>(null)
  const [allElfies, setAllElfies] = useState<readonly ManagedElfie[] | null>(null)
  const [elfies, setElfies] = useState<readonly ManagedElfie[]>([])
  const [selection, setSelection] = useState<FilterSelection>(INITIAL_SELECTION)
  const [error, setError] = useState<LocalizedErrorState>(null)
  const { show } = useToast()
  const loadSequence = useRef(0)

  const load = async (nextSelection: FilterSelection): Promise<void> => {
    const sequence = loadSequence.current + 1
    loadSequence.current = sequence
    setUsers(null)
    setAllElfies(null)
    setElfies([])
    setError(null)
    onCountChange(0)
    try {
      const [loadedUsers, identities, sessions, rooms] = await Promise.all([
        ownerUsers(),
        adminElfies(),
        embodimentSessions(),
        ownerRooms(),
      ])
      const policies = await Promise.all(
        identities.map(async (elfie) => [
          elfie.profile.elfie_id,
          await elfieFoodPolicy(elfie.profile.elfie_id),
        ] as const),
      )
      const loadedAll = composeManagedElfies(
        identities,
        new Map(policies),
        sessions,
        rooms,
      )
      const loadedElfies = loadedAll.filter((elfie) => matchesSelection(elfie, nextSelection))
      if (sequence !== loadSequence.current) return
      setUsers(loadedUsers)
      setAllElfies(loadedAll)
      setElfies(loadedElfies)
      onCountChange(loadedAll.length)
      setError(null)
    } catch (reason: unknown) {
      if (sequence !== loadSequence.current) return
      if (!(reason instanceof Error)) throw reason
      setUsers([])
      setAllElfies([])
      setElfies([])
      onCountChange(0)
      setError(describeApiError(reason, "manage.load"))
    }
  }

  const reloadElfies = async (): Promise<void> => {
    try {
      const [identities, sessions, rooms] = await Promise.all([
        adminElfies(),
        embodimentSessions(),
        ownerRooms(),
      ])
      const policies = await Promise.all(
        identities.map(async (elfie) => [
          elfie.profile.elfie_id,
          await elfieFoodPolicy(elfie.profile.elfie_id),
        ] as const),
      )
      const loadedAll = composeManagedElfies(identities, new Map(policies), sessions, rooms)
      const loadedElfies = loadedAll.filter((elfie) => matchesSelection(elfie, selection))
      setAllElfies(loadedAll)
      setElfies(loadedElfies)
      onCountChange(loadedAll.length)
      setError(null)
    } catch (reason: unknown) {
      if (!(reason instanceof Error)) throw reason
      setAllElfies([])
      setElfies([])
      onCountChange(0)
      setError(describeApiError(reason, "manage.load"))
    }
  }

  useEffect(() => {
    void load(selection)
  }, [selection])

  const update = (key: Exclude<keyof FilterSelection, "ownerUserId">, value: string): void => {
    setSelection((current) => ({ ...current, [key]: value }))
  }
  const loadedElfies = allElfies ?? []
  const loadedUsers = users ?? []
  const species = [...new Set(loadedElfies.map((elfie) => elfie.profile.species_id))].sort((left, right) => compareLocalizedText(left, right, locale))
  const foods = [...new Set(loadedElfies.map((elfie) => elfie.foodPolicy.effective_main_food_id))].sort((left, right) => compareLocalizedText(left, right, locale))
  const states = [...new Set(loadedElfies.map((elfie) => elfie.embodiment.state))].sort((left, right) => compareLocalizedText(left, right, locale))
  const orderedUsers = [...loadedUsers].sort(compareAccountListOrder)
  const orderedElfies = [...elfies].sort(compareElfieId)
  const loading = users === null || allElfies === null
  const updateOwner = (value: string): void => {
    if (value === ALL_USERS) {
      setSelection((current) => ({ ...current, ownerUserId: null }))
      return
    }
    const selectedUser = orderedUsers.find((user) => String(user.user_id) === value)
    if (selectedUser !== undefined) {
      setSelection((current) => ({ ...current, ownerUserId: selectedUser.user_id }))
    }
  }

  return <section className="manage-card manage-card--wide manage-identity-panel">
    <div className="manage-head">
      <RefreshButton label={t("users.actions.refresh")} onClick={() => { void load(selection) }} />
    </div>
    <div className="manage-filters">
      <SelectField
        disabled={loading}
        label={t("elfies.filters.owner")}
        onValueChange={updateOwner}
        options={[
          { label: t("elfies.filters.allUsers"), value: ALL_USERS },
          ...orderedUsers.map((user) => ({ label: user.display_name ?? user.account_id, value: String(user.user_id) })),
        ]}
        value={selection.ownerUserId === null ? ALL_USERS : String(selection.ownerUserId)}
      />
      <SelectField
        disabled={loading}
        label={t("elfies.filters.species")}
        onValueChange={(value) => update("speciesId", value)}
        options={[
          { label: t("elfies.filters.allSpecies"), value: ALL_SPECIES },
          ...species.map((value) => ({ label: value, value })),
        ]}
        value={selection.speciesId}
      />
      <SelectField
        disabled={loading}
        label={t("elfies.filters.food")}
        onValueChange={(value) => update("foodKey", value)}
        options={[
          { label: t("elfies.filters.allFoods"), value: ALL_FOODS },
          ...foods.map((value) => ({ label: value, value })),
        ]}
        value={selection.foodKey}
      />
      <SelectField
        disabled={loading}
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
    <div className="elfie-id-grid">
      {loading ? <p className="empty">{t("rawData.loading")}</p> : null}
      {!loading && error === null && orderedElfies.length === 0 ? <p className="empty">{t("elfies.empty")}</p> : null}
      {!loading && error === null ? orderedElfies.map((elfie) => <ElfieIdentityCard
          csrfToken={csrfToken}
          elfie={elfie}
          key={elfie.profile.elfie_id}
          onError={setError}
          onSaved={async () => {
            show({ kind: "success", message: t("elfies.notices.foodSaved", { name: elfie.profile.name }) })
            await reloadElfies()
          }}
        />) : null}
    </div>
  </section>
}
