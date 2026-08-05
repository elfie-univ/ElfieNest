import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useTranslation } from "react-i18next"

import type { ChatMessage, ElfieProfile } from "../../api/client"
import { Avatar } from "../Avatar"
import { Icon } from "../Icon"
import { Notice } from "../Notice"

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
  return (
    <article className={`message${isUserMessage ? " message--user" : ""}`}>
      <Avatar imageUrl={isUserMessage ? userAvatarUrl : elfieAvatarUrl} name={senderName} />
      <div className="bubble">{message.text}</div>
    </article>
  )
}

export function ChatConversationPane(props: ChatConversationPaneProps) {
  const { t } = useTranslation("chat")
  const {
    draft, error, history, mobileDetail, onBack, onDraftChange, onOpenDetail,
    onSubmit, selected, selectedId, userAvatarUrl, userDisplayName,
  } = props
  return (
    <section className={mobileDetail ? "conversation conversation--mobile-active" : "conversation"}>
      <div className="topline">
        <Button aria-label={t("conversation.back")} className="mobile-back-button" onClick={onBack} size="icon-sm" type="button" variant="ghost"><Icon name="chevron-down" /></Button>
        <h1>{selected?.name ?? t("conversation.select")}</h1>
        <Button variant="outline" disabled={selected === undefined} onClick={onOpenDetail} type="button">{t("conversation.details")}</Button>
      </div>
      <section className="message-list">
        {selectedId === null ? <p className="empty">{t("conversation.empty")}</p> : history.map((message) => <MessageBubble
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
