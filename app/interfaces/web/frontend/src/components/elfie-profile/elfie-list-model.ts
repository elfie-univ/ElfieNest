import { isAdopterAccount } from "./projection"

export type ElfieListFilter = "all" | "mine" | "other"
export type ElfieListProfile = {
  readonly elfie_id: string
  readonly name: string
  readonly species_id: string
  readonly portrait_url: string
}
export type ElfieListItem = {
  readonly adopterAccountId: string
  readonly profile: ElfieListProfile
}
export type ElfieListGroup = {
  readonly label: "我的精灵" | "其他精灵"
  readonly items: readonly ElfieListItem[]
}
export type ElfieListResult = {
  readonly counts: Readonly<Record<ElfieListFilter, number>>
  readonly groups: readonly ElfieListGroup[]
  readonly visibleCount: number
}

export function filterElfieList(
  items: readonly ElfieListItem[],
  viewerAccountId: string,
  query: string,
  filter: ElfieListFilter,
): ElfieListResult {
  const mine = items.filter((item) => isAdopterAccount(viewerAccountId, item.adopterAccountId))
  const other = items.filter((item) => !isAdopterAccount(viewerAccountId, item.adopterAccountId))
  const normalizedQuery = query.trim().toLocaleLowerCase()
  const searchable = items.filter((item) => matchesQuery(item, normalizedQuery))
  const visible = searchable.filter((item) => matchesFilter(item, viewerAccountId, filter))
  const visibleMine = visible.filter((item) => isAdopterAccount(viewerAccountId, item.adopterAccountId))
  const visibleOther = visible.filter((item) => !isAdopterAccount(viewerAccountId, item.adopterAccountId))
  const groups: ElfieListGroup[] = []
  if (visibleMine.length > 0) groups.push({ label: "我的精灵", items: visibleMine })
  if (visibleOther.length > 0) groups.push({ label: "其他精灵", items: visibleOther })
  return {
    counts: { all: items.length, mine: mine.length, other: other.length },
    groups,
    visibleCount: visible.length,
  }
}

function matchesQuery(item: ElfieListItem, query: string): boolean {
  if (query === "") return true
  const profile = item.profile
  return [profile.name, profile.species_id, profile.elfie_id]
    .some((value) => value.toLocaleLowerCase().includes(query))
}

function matchesFilter(item: ElfieListItem, viewerAccountId: string, filter: ElfieListFilter): boolean {
  const mine = isAdopterAccount(viewerAccountId, item.adopterAccountId)
  switch (filter) {
    case "all": return true
    case "mine": return mine
    case "other": return !mine
    default: return assertNever(filter)
  }
}

function assertNever(value: never): never {
  throw new RangeError(`Unexpected Elfie list filter: ${String(value)}`)
}
