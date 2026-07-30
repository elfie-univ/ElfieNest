import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useTranslation } from "react-i18next"

import type { ChatSocketStatus } from "../../api/chat-socket"
import type { Conversation } from "../../api/client"
import type { ChatPane } from "../../pages/use-chat-view"
import { Avatar } from "../Avatar"
import { Icon } from "../Icon"
import { ElfieList } from "./ElfieList"
import type { ElfieListFilter, ElfieListItem } from "./elfie-list-model"

type ChatListPaneProps = {
  readonly activePane: ChatPane
  readonly conversations: readonly Conversation[]
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
  readonly status: ChatSocketStatus
  readonly viewerAccountId: string
}

export function ChatListPane(props: ChatListPaneProps) {
  const { t } = useTranslation("chat")
  const {
    activePane, conversations, elfieFilter, elfieItems, elfieQuery, hiddenOnMobile,
    onAdopt, onChat, onElfieFilterChange, onElfieProfile, onElfieQueryChange,
    selectedId, status, viewerAccountId,
  } = props
  return (
    <aside className={hiddenOnMobile ? "chat-list-pane chat-list-pane--mobile-hidden" : "chat-list-pane"}>
      <header className="list-pane-head">
        <h1>{activePane === "chats" ? t("list.messagesTitle") : t("list.elfiesTitle")}</h1>
        <Button className="add-button" onClick={onAdopt} size="icon-sm" type="button" variant="outline" aria-label={t("list.adopt")}><Icon name="plus" /></Button>
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
      {activePane === "chats" ? (
        <div className="chat-list">
          {conversations.map((row) => (
            <Button className={row.elfie_id === selectedId ? "wechat-row wechat-row--active" : "wechat-row"} key={row.elfie_id} onClick={() => onChat(row.elfie_id)} type="button" variant="ghost">
              <Avatar name={row.name} />
              <span className="list-copy"><strong>{row.name}</strong><small>{row.last_message_preview || t("list.noPreview")}</small></span>
            </Button>
          ))}
          {conversations.length === 0 ? <p className="empty">{t("list.empty")}</p> : null}
        </div>
      ) : (
        <ElfieList
          filter={elfieFilter}
          items={elfieItems}
          onChat={onChat}
          onFilterChange={onElfieFilterChange}
          onProfile={onElfieProfile}
          query={elfieQuery}
          selectedId={selectedId}
          viewerAccountId={viewerAccountId}
        />
      )}
      <p className="connection-state">{t("connection.label", { state: t(`connection.${status}`) })}</p>
    </aside>
  )
}
