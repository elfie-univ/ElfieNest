import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

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
  const senderName = message.sender === "user" ? "我" : "精"
  return (
    <article className={`message${message.sender === "user" ? " message--user" : ""}`}>
      <Avatar name={senderName} />
      <div className="bubble">{message.text}</div>
    </article>
  )
}

export function ChatConversationPane(props: ChatConversationPaneProps) {
  const {
    demoMode, draft, error, history, mobileDetail, notice, onBack, onDraftChange,
    onOpenDetail, onSubmit, selected, selectedId,
  } = props
  return (
    <section className={mobileDetail ? "conversation conversation--mobile-active" : "conversation"}>
      <div className="topline">
        <Button aria-label="返回聊天记录" className="mobile-back-button" onClick={onBack} size="icon-sm" type="button" variant="ghost"><Icon name="chevron-down" /></Button>
        <h1>{selected?.name ?? "选择一只精灵"}</h1>
        <Button variant="outline" disabled={selected === undefined} onClick={onOpenDetail} type="button">详情</Button>
      </div>
      <section className="message-list">
        {selectedId === null ? <p className="empty">先在“我的精灵”中领养或选择一只精灵。</p> : history.map((message) => <MessageBubble key={message.id} message={message} />)}
        {notice ? <Notice message={notice} /> : null}
        {error ? <Notice kind="error" message={error} /> : null}
      </section>
      <form className="composer" onSubmit={(event) => { event.preventDefault(); void onSubmit() }}>
        <Textarea disabled={selected === undefined || demoMode} onChange={(event) => onDraftChange(event.target.value)} placeholder={selected ? `对 ${selected.name} 说点什么…` : "请选择精灵"} value={draft} />
        <Button disabled={selected === undefined || !draft.trim() || demoMode} type="submit">发送</Button>
      </form>
    </section>
  )
}
