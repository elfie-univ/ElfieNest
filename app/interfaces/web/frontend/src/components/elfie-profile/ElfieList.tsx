import { Button } from "@/components/ui/button"
import { useTranslation } from "react-i18next"

import { Avatar } from "../Avatar"
import {
  filterElfieList,
  type ElfieListFilter,
  type ElfieListItem,
} from "./elfie-list-model"

type ElfieListProps = {
  readonly filter: ElfieListFilter
  readonly items: readonly ElfieListItem[]
  readonly onFilterChange: (filter: ElfieListFilter) => void
  readonly onProfile: (elfieId: string) => void
  readonly query: string
  readonly selectedId: string | null
  readonly viewerAccountId: string
}

const FILTERS = ["all", "mine", "other"] as const

export function ElfieList({
  filter, items, onFilterChange, onProfile, query, selectedId, viewerAccountId,
}: ElfieListProps) {
  const { t } = useTranslation("chat")
  const result = filterElfieList(items, viewerAccountId, query, filter)
  const hasAnyElfies = items.length > 0
  return (
    <div className={hasAnyElfies ? "elfie-list" : "elfie-list elfie-list--empty"}>
      {hasAnyElfies ? <div aria-label={t("profile.list.scope")} className="elfie-list__filters" role="group">
        {FILTERS.map((option) => {
          const label = t(`profile.list.${option}`)
          return (
          <Button
            aria-label={t("profile.list.filterLabel", { count: result.counts[option], label })}
            aria-pressed={filter === option}
            className="elfie-list__filter"
            key={option}
            onClick={() => onFilterChange(option)}
            size="sm"
            type="button"
            variant="ghost"
          >
            {label} <span>{result.counts[option]}</span>
          </Button>
          )
        })}
      </div> : null}
      <div className={hasAnyElfies ? "elfie-list__scroll" : "elfie-list__scroll elfie-list__scroll--empty"}>
        {result.groups.map((group) => (
          <section className="elfie-list__group" key={group.kind}>
            <h2>{group.kind === "mine" ? t("profile.list.mineGroup") : t("profile.list.otherGroup")}</h2>
            {group.items.map((item) => (
              <article className="elfie-list__row" key={item.profile.elfie_id}>
                <Button
                  aria-label={t("profile.list.openProfile", { name: item.profile.name })}
                  className={item.profile.elfie_id === selectedId
                    ? "elfie-list__profile elfie-list__profile--active"
                    : "elfie-list__profile"}
                  onClick={() => onProfile(item.profile.elfie_id)}
                  type="button"
                  variant="ghost"
                >
                  <Avatar imageUrl={item.profile.portrait_url} name={item.profile.name} />
                  <span className="list-copy">
                    <strong>{item.profile.name}</strong>
                  </span>
                </Button>
              </article>
            ))}
          </section>
        ))}
        {result.visibleCount === 0 ? hasAnyElfies ? (
          <p className="elfie-list__empty" role="status">{t("profile.list.empty")}</p>
        ) : (
          <div className="empty-state empty-state--list" role="status">
            <h2>{t("profile.list.emptyFirstTitle")}</h2>
            <p>{t("profile.list.emptyFirstDescription")}</p>
          </div>
        ) : null}
      </div>
    </div>
  )
}
