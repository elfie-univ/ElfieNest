import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useTranslation } from "react-i18next"

import type { ChatMessage, ElfieProfile } from "../../api/client"
import { Avatar } from "../Avatar"
import { Icon } from "../Icon"
import { Notice } from "../Notice"

type ChatConversationPaneProps = {
  readonly demoMode: boolean
  readonly draft: string
  readonly error: string | null
  readonly history: readonly ChatMessage[]
  readonly mobileDetail: boolean
  readonly notice: string | null
  readonly onBack: () => void
  readonly onDraftChange: (draft: string) => void
  readonly onOpenDetail: () => void
  readonly onSubmit: () => Promise<void>
  readonly selected: ElfieProfile | undefined
  readonly selectedId: string | null
}

function MessageBubble({ message }: { readonly message: ChatMessage }) {
  const { t } = useTranslation("chat")
  const senderName = message.sender === "user" ? t("conversation.senderMe") : t("conversation.senderElfie")
  return (
    <article className={`message${message.sender === "user" ? " message--user" : ""}`}>
      <Avatar name={senderName} />
      <div className="bubble">{message.text}</div>
    </article>
  )
}

export function ChatConversationPane(props: ChatConversationPaneProps) {
  const { t } = useTranslation("chat")
  const {
    demoMode, draft, error, history, mobileDetail, notice, onBack, onDraftChange,
    onOpenDetail, onSubmit, selected, selectedId,
  } = props
  return (
    <section className={mobileDetail ? "conversation conversation--mobile-active" : "conversation"}>
      <div className="topline">
        <Button aria-label={t("conversation.back")} className="mobile-back-button" onClick={onBack} size="icon-sm" type="button" variant="ghost"><Icon name="chevron-down" /></Button>
        <h1>{selected?.name ?? t("conversation.select")}</h1>
        <Button variant="outline" disabled={selected === undefined} onClick={onOpenDetail} type="button">{t("conversation.details")}</Button>
      </div>
      <section className="message-list">
        {selectedId === null ? <p className="empty">{t("conversation.empty")}</p> : history.map((message) => <MessageBubble key={message.id} message={message} />)}
        {notice ? <Notice message={notice} /> : null}
        {error ? <Notice kind="error" message={error} /> : null}
      </section>
      <form className="composer" onSubmit={(event) => { event.preventDefault(); void onSubmit() }}>
        <Textarea disabled={selected === undefined || demoMode} onChange={(event) => onDraftChange(event.target.value)} placeholder={selected ? t("composer.withElfie", { elfieName: selected.name }) : t("composer.select")} value={draft} />
        <Button disabled={selected === undefined || !draft.trim() || demoMode} type="submit">{t("composer.send")}</Button>
      </form>
    </section>
  )
}
