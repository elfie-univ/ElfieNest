import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useCallback, useLayoutEffect, useRef } from "react"
import { useTranslation } from "react-i18next"

import type { ElfieProfile } from "../../api/client"
import type { ChatMessage } from "../../api/communication"
import { Avatar } from "../Avatar"
import { Icon } from "../Icon"
import { Notice } from "../Notice"
import { presentChatText } from "./chat-data"

type ChatConversationPaneProps = {
  readonly draft: string
  readonly error: string | null
  readonly history: readonly ChatMessage[]
  readonly mobileDetail: boolean
  readonly onBack: () => void
  readonly onDraftChange: (draft: string) => void
  readonly onOpenDetail: () => void
  readonly onSubmit: () => Promise<void>
  readonly selected: ElfieProfile | undefined
  readonly selectedId: string | null
  readonly userAvatarUrl?: string | null | undefined
  readonly userDisplayName: string
}

function MessageBubble({ message, userAvatarUrl, userDisplayName, elfieAvatarUrl }: {
  readonly elfieAvatarUrl?: string | null | undefined
  readonly message: ChatMessage
  readonly userAvatarUrl?: string | null | undefined
  readonly userDisplayName: string
}) {
  const { t } = useTranslation("chat")
  const isUserMessage = message.sender === "user"
  const senderName = isUserMessage ? userDisplayName : t("conversation.senderElfie")
  const visibleText = isUserMessage ? message.text : presentChatText(message.text)
  if (!visibleText) return null
  return (
    <article className={`message${isUserMessage ? " message--user" : ""}`}>
      <Avatar imageUrl={isUserMessage ? userAvatarUrl : elfieAvatarUrl} name={senderName} />
      <div className="bubble">{visibleText}</div>
    </article>
  )
}

export function ChatConversationPane(props: ChatConversationPaneProps) {
  const { t } = useTranslation("chat")
  const {
    draft, error, history, mobileDetail, onBack, onDraftChange, onOpenDetail,
    onSubmit, selected, selectedId, userAvatarUrl, userDisplayName,
  } = props
  const messageListRef = useRef<HTMLElement | null>(null)
  const followBottomRef = useRef(true)
  const handleMessageListScroll = useCallback((): void => {
    const list = messageListRef.current
    if (list === null) return
    followBottomRef.current = list.scrollHeight - list.clientHeight - list.scrollTop <= 24
  }, [])

  useLayoutEffect(() => {
    const list = messageListRef.current
    if (list !== null && followBottomRef.current) list.scrollTop = list.scrollHeight - list.clientHeight
  }, [history.length])

  useLayoutEffect(() => {
    followBottomRef.current = true
    const list = messageListRef.current
    if (list !== null) list.scrollTop = list.scrollHeight - list.clientHeight
  }, [selectedId])

  if (selectedId === null) {
    return <section className="conversation conversation--empty"><p className="empty">{t("conversation.empty")}</p></section>
  }

  return (
    <section className={mobileDetail ? "conversation conversation--mobile-active" : "conversation"}>
      <div className="topline">
        <Button aria-label={t("conversation.back")} className="mobile-back-button" onClick={onBack} size="icon-sm" type="button" variant="ghost"><Icon name="chevron-down" /></Button>
        <h1>{selected?.name ?? t("conversation.select")}</h1>
        <Button variant="outline" disabled={selected === undefined} onClick={onOpenDetail} type="button">{t("conversation.details")}</Button>
      </div>
      <section className="message-list" onScroll={handleMessageListScroll} ref={messageListRef}>
        {history.map((message) => <MessageBubble
          elfieAvatarUrl={selected?.portrait_url}
          key={message.id}
          message={message}
          userAvatarUrl={userAvatarUrl}
          userDisplayName={userDisplayName}
        />)}
        {error ? <Notice kind="error" message={error} /> : null}
      </section>
      <form className="composer" onSubmit={(event) => { event.preventDefault(); void onSubmit() }}>
        <Textarea
          disabled={selected === undefined}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return
            event.preventDefault()
            void onSubmit()
          }}
          placeholder={selected ? t("composer.withElfie", { elfieName: selected.name }) : t("composer.select")}
          value={draft}
        />
        <Button disabled={selected === undefined || !draft.trim()} type="submit">{t("composer.send")}</Button>
      </form>
    </section>
  )
}
