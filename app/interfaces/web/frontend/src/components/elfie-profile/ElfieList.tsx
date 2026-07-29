import { Button } from "@/components/ui/button"

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

const FILTERS = [
  { key: "all", label: "全部" },
  { key: "mine", label: "我的" },
  { key: "other", label: "其他" },
] as const

export function ElfieList({
  filter, items, onChat, onFilterChange, onProfile, query, selectedId, viewerAccountId,
}: ElfieListProps) {
  const result = filterElfieList(items, viewerAccountId, query, filter)
  return (
    <div className="elfie-list">
      <div aria-label="精灵范围" className="elfie-list__filters" role="group">
        {FILTERS.map((option) => (
          <Button
            aria-label={`${option.label} ${result.counts[option.key]}`}
            aria-pressed={filter === option.key}
            className="elfie-list__filter"
            key={option.key}
            onClick={() => onFilterChange(option.key)}
            size="sm"
            type="button"
            variant="ghost"
          >
            {option.label} <span>{result.counts[option.key]}</span>
          </Button>
        ))}
      </div>
      <div className="elfie-list__scroll">
        {result.groups.map((group) => (
          <section className="elfie-list__group" key={group.label}>
            <h2>{group.label}</h2>
            {group.items.map((item) => (
              <article className="elfie-list__row" key={item.profile.elfie_id}>
                <Button
                  aria-label={`查看 ${item.profile.name} 的个人档案`}
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
                  aria-label={`与 ${item.profile.name} 聊天`}
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
          <p className="elfie-list__empty" role="status">没有符合条件的精灵。请清除搜索或切换筛选。</p>
        ) : null}
      </div>
    </div>
  )
}
