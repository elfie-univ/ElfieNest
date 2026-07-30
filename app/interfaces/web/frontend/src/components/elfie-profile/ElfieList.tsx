import { Button } from "@/components/ui/button"
import { useTranslation } from "react-i18next"

import { Avatar } from "../Avatar"
import { Icon } from "../Icon"
import {
  filterElfieList,
  type ElfieListFilter,
  type ElfieListItem,
} from "./elfie-list-model"

type ElfieListProps = {
  readonly filter: ElfieListFilter
  readonly items: readonly ElfieListItem[]
  readonly onChat: (elfieId: string) => void
  readonly onFilterChange: (filter: ElfieListFilter) => void
  readonly onProfile: (elfieId: string) => void
  readonly query: string
  readonly selectedId: string | null
  readonly viewerAccountId: string
}

const FILTERS = ["all", "mine", "other"] as const

export function ElfieList({
  filter, items, onChat, onFilterChange, onProfile, query, selectedId, viewerAccountId,
}: ElfieListProps) {
  const { t } = useTranslation("chat")
  const result = filterElfieList(items, viewerAccountId, query, filter)
  return (
    <div className="elfie-list">
      <div aria-label={t("profile.list.scope")} className="elfie-list__filters" role="group">
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
      </div>
      <div className="elfie-list__scroll">
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
                    <small>{item.profile.species_id} · {item.profile.elfie_id}</small>
                  </span>
                </Button>
                <Button
                  aria-label={t("profile.list.chatWith", { name: item.profile.name })}
                  className="elfie-list__chat"
                  onClick={() => onChat(item.profile.elfie_id)}
                  size="icon-sm"
                  type="button"
                  variant="ghost"
                >
                  <Icon name="messages-square" size={17} />
                </Button>
              </article>
            ))}
          </section>
        ))}
        {result.visibleCount === 0 ? (
          <p className="elfie-list__empty" role="status">{t("profile.list.empty")}</p>
        ) : null}
      </div>
    </div>
  )
}
