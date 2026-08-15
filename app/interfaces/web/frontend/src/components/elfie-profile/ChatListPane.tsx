import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useTranslation } from "react-i18next"

import type { Conversation } from "../../api/communication"
import type { ChatPane } from "../../pages/use-chat-view"
import { Avatar } from "../Avatar"
import { Icon } from "../Icon"
import { Notice } from "../Notice"
import { ElfieList } from "./ElfieList"
import type { ElfieListFilter, ElfieListItem } from "./elfie-list-model"

type ChatListPaneProps = {
  readonly activePane: ChatPane
  readonly conversations: readonly Conversation[]
  readonly error: string | null
  readonly elfieFilter: ElfieListFilter
  readonly elfieItems: readonly ElfieListItem[]
  readonly elfieQuery: string
  readonly hiddenOnMobile: boolean
  readonly onAdopt: () => void
  readonly onChat: (elfieId: string) => void
  readonly onElfieFilterChange: (filter: ElfieListFilter) => void
  readonly onElfieProfile: (elfieId: string) => void
  readonly onElfieQueryChange: (query: string) => void
  readonly selectedId: string | null
  readonly viewerAccountId: string
}

export function ChatListPane(props: ChatListPaneProps) {
  const { t } = useTranslation("chat")
  const {
    activePane, conversations, elfieFilter, elfieItems, elfieQuery, error, hiddenOnMobile,
    onAdopt, onChat, onElfieFilterChange, onElfieProfile, onElfieQueryChange,
    selectedId, viewerAccountId,
  } = props
  return (
    <aside className={hiddenOnMobile ? "chat-list-pane chat-list-pane--mobile-hidden" : "chat-list-pane"}>
      <header className="list-pane-head">
        <h1>{activePane === "chats" ? t("list.messagesTitle") : t("list.elfiesTitle")}</h1>
        <Button aria-label={t("list.adopt")} className="add-button" onClick={onAdopt} size="sm" type="button" variant="outline">
          <Icon name="plus" />
          <span className="add-button__label add-button__label--desktop">{t("list.adopt")}</span>
          <span className="add-button__label add-button__label--mobile">{t("list.adoptShort")}</span>
        </Button>
      </header>
      <label className="search-box" aria-label={t("list.searchLabel")}>
        <Icon name="search" size={16} />
        {activePane === "elfies" ? (
          <Input
            key="elfie-search"
            onChange={(event) => onElfieQueryChange(event.target.value)}
            placeholder={t("list.searchElfies")}
            value={elfieQuery}
          />
        ) : <Input key="chat-search" placeholder={t("list.searchChats")} />}
      </label>
      {error ? <Notice kind="error" message={error} /> : null}
      {activePane === "chats" ? (
        <div className={conversations.length === 0 ? "chat-list chat-list--empty" : "chat-list"}>
          {conversations.map((row) => (
            <Button className={row.elfie_id === selectedId ? "wechat-row wechat-row--active" : "wechat-row"} key={row.elfie_id} onClick={() => onChat(row.elfie_id)} type="button" variant="ghost">
              <Avatar imageUrl={row.portrait_url} name={row.name} />
              <span className="list-copy"><strong>{row.name}</strong><small>{row.last_message_preview || t("list.noPreview")}</small></span>
            </Button>
          ))}
          {conversations.length === 0 ? (
            <div className="empty-state empty-state--list" role="status">
              <h2>{t("list.emptyTitle")}</h2>
              <p>{t(elfieItems.length === 0 ? "list.emptyFirstDescription" : "list.emptyExistingDescription")}</p>
            </div>
          ) : null}
        </div>
      ) : (
        <ElfieList
          filter={elfieFilter}
          items={elfieItems}
          onFilterChange={onElfieFilterChange}
          onProfile={onElfieProfile}
          query={elfieQuery}
          selectedId={selectedId}
          viewerAccountId={viewerAccountId}
        />
      )}
    </aside>
  )
}
