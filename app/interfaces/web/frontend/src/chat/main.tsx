import { useEffect, useRef, useState } from "react"
import type { Dispatch, FormEvent, ReactElement, SetStateAction } from "react"

import {
  ApiError,
  type ChatMessage,
  type ClientUser,
  type Conversation,
  type ElfieProfile,
  conversations,
  currentUser,
  elfies,
  logout,
  messages,
  profile,
  sendMessage
} from "../shared/api"
import { ChatSocket } from "../shared/chat_socket"
import type { ChatSocketEvent, ChatSocketStatus } from "../shared/chat_socket"
import { mountProductPage } from "../shared/react_mount"

type ChatState = {
  readonly conversations: readonly Conversation[]
  readonly elfies: readonly ElfieProfile[]
  readonly messages: readonly ChatMessage[]
  readonly profile: ElfieProfile | null
  readonly selectedId: string | null
  readonly socketNotice: string | null
  readonly socketStatus: ChatSocketStatus
  readonly unread: ReadonlyMap<string, number>
  readonly user: ClientUser
}

async function loadState(): Promise<ChatState> {
  const user = await currentUser()
  const [rows, ownedElfies] = await Promise.all([conversations(), elfies()])
  const selectedId = new URLSearchParams(window.location.search).get("elfie") ?? rows[0]?.elfie_id ?? ownedElfies[0]?.elfie_id ?? null
  return {
    user,
    conversations: rows,
    elfies: ownedElfies,
    messages: selectedId === null ? [] : await messages(selectedId),
    profile: null,
    selectedId,
    socketNotice: null,
    socketStatus: "offline",
    unread: new Map()
  }
}

function Avatar({ name }: { readonly name: string }): ReactElement {
  return <span className="avatar">{name.slice(0, 1) || "精"}</span>
}

function ChatPage(): ReactElement {
  const [state, setState] = useState<ChatState | null>(null)
  const [draft, setDraft] = useState("")
  const socket = useRef<ChatSocket | null>(null)

  useEffect(() => {
    void loadState().then(setState).catch(() => window.location.assign("/login?next=/chat"))
    return () => socket.current?.close()
  }, [])

  useEffect(() => {
    if (state === null || socket.current !== null) return
    socket.current = new ChatSocket({
      onEvent: (event) => void handleSocketEvent(event, setState),
      onStatus: (status) => setState((current) => current === null ? current : { ...current, socketStatus: status })
    })
    socket.current.connect()
  }, [state])

  if (state === null) return <main className="page" />
  const selected = state.elfies.find((elfie) => elfie.elfie_id === state.selectedId)
  const csrfToken = state.user.csrf_token ?? ""
  const selectElfie = async (elfieId: string, openProfile: boolean): Promise<void> => {
    const [history, detail] = await Promise.all([messages(elfieId), openProfile ? profile(elfieId) : Promise.resolve(null)])
    setState({ ...state, selectedId: elfieId, messages: history, profile: detail, unread: withoutUnread(state.unread, elfieId) })
  }
  const showProfile = async (): Promise<void> => {
    if (state.selectedId === null) return
    setState({ ...state, profile: await profile(state.selectedId) })
  }
  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (state.selectedId === null || draft.trim() === "") return
    const text = draft.trim()
    setDraft("")
    try {
      if (!socket.current?.send(state.selectedId, text)) {
        const message = await sendMessage(state.selectedId, text, csrfToken)
        const rows = await conversations()
        setState({ ...state, messages: [...state.messages, message], conversations: rows })
      }
    } catch (error: unknown) {
      setState({ ...state, socketNotice: error instanceof ApiError ? error.message : "消息没有送达" })
    }
  }
  const leave = async (): Promise<void> => {
    await logout(csrfToken)
    window.location.assign("/login")
  }

  return <main className="page"><section className="panel workspace">
    <aside className="sidebar"><div className="sidebar-header"><strong>ElfieNest</strong><a className="button button--quiet" href="/manage">{state.user.role === "owner" ? "管理" : "设置"}</a></div>
      <p className="section-label">聊天记录</p><div className="sidebar-list">{state.conversations.map((row) => <SelectionRow active={row.elfie_id === state.selectedId} key={row.elfie_id} label={`${row.last_message_preview || "还没有消息"}${unreadLabel(state, row.elfie_id)}`} name={row.name} onClick={() => void selectElfie(row.elfie_id, false)} />)}</div>
      <p className="section-label">我的精灵</p><div className="sidebar-list">{state.elfies.map((elfie) => <SelectionRow active={elfie.elfie_id === state.selectedId} key={elfie.elfie_id} label={`${elfie.species_id} · ${elfie.embodiment.state}${unreadLabel(state, elfie.elfie_id)}`} name={elfie.name} onClick={() => void selectElfie(elfie.elfie_id, true)} />)}</div>
      <div className="sidebar-bottom"><small className="connection-state">{socketLabel(state.socketStatus)}</small><button className="button button--quiet" onClick={() => void leave()} type="button">退出登录</button></div>
    </aside>
    <section className="conversation"><div className="topline"><h1>{selected?.name ?? "选择一只精灵"}</h1><button className="button button--quiet" disabled={selected === undefined} onClick={() => void showProfile()} type="button">资料</button></div>
      <section className="message-list">{state.selectedId === null ? <p className="empty">先选择一只属于你的精灵。</p> : state.messages.map((message) => <MessageRow key={message.id} message={message} />)}{state.socketNotice === null ? null : <p className="notice notice--error">{state.socketNotice}</p>}</section>
      <form className="composer" onSubmit={(event) => void submit(event)}><textarea disabled={selected === undefined} onChange={(event) => setDraft(event.target.value)} placeholder={selected === undefined ? "请选择精灵" : `对 ${selected.name} 说点什么…`} value={draft} /><button className="button" disabled={selected === undefined || csrfToken === ""} type="submit">发送</button></form>
    </section>
    <aside className="detail">{state.profile === null ? <p className="empty">打开资料，查看外貌、人格和具身状态。</p> : <ProfileCard profile={state.profile} />}</aside>
  </section></main>
}

function SelectionRow({ active, label, name, onClick }: { readonly active: boolean; readonly label: string; readonly name: string; readonly onClick: () => void }): ReactElement {
  return <button className={`list-row${active ? " list-row--active" : ""}`} onClick={onClick} type="button"><Avatar name={name} /><span className="list-copy"><strong>{name}</strong><small>{label}</small></span></button>
}

function MessageRow({ message }: { readonly message: ChatMessage }): ReactElement {
  return <article className={`message${message.sender === "user" ? " message--user" : ""}`}><Avatar name={message.sender === "user" ? "我" : "精"} /><div className="bubble">{message.text}</div></article>
}

function ProfileCard({ profile: current }: { readonly profile: ElfieProfile }): ReactElement {
  const appearance = Object.values(current.appearance).filter((value): value is string => typeof value === "string").join(" · ") || "待完善"
  return <><Avatar name={current.name} /><h2>{current.name}</h2><p>{current.species_id} · {current.embodiment.state}</p><div>{current.personality_tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div><dl>{Object.entries(current.big_five).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value.toFixed(2)}</dd></div>)}<div><dt>巢内位置</dt><dd>{current.nest.room_name ?? "未分配"}</dd></div><div><dt>外貌摘要</dt><dd>{appearance}</dd></div></dl><a className="button button--quiet" href="/runtime/godot">打开 3D 巢内预览</a></>
}

async function handleSocketEvent(event: ChatSocketEvent, setState: Dispatch<SetStateAction<ChatState | null>>): Promise<void> {
  if (event.event === "error") {
    setState((current) => current === null ? current : { ...current, socketNotice: event.detail })
    return
  }
  if (event.event !== "message") return
  const rows = await conversations()
  setState((current) => applySocketMessage(current, event.message, rows))
}

function applySocketMessage(state: ChatState | null, message: ChatMessage, rows: readonly Conversation[]): ChatState | null {
  if (state === null) return null
  if (message.elfie_id === state.selectedId) return { ...state, conversations: rows, messages: state.messages.some((row) => row.id === message.id) ? state.messages : [...state.messages, message] }
  const unread = new Map(state.unread)
  unread.set(message.elfie_id, (unread.get(message.elfie_id) ?? 0) + 1)
  return { ...state, conversations: rows, unread }
}

function withoutUnread(unread: ReadonlyMap<string, number>, elfieId: string): ReadonlyMap<string, number> {
  const next = new Map(unread)
  next.delete(elfieId)
  return next
}

function unreadLabel(state: ChatState, elfieId: string): string { const count = state.unread.get(elfieId) ?? 0; return count > 0 ? ` · ${count} 条新消息` : "" }
function socketLabel(status: ChatSocketStatus): string { return status === "online" ? "实时通道已连接" : status === "connecting" ? "正在连接实时通道…" : "实时通道离线，发送将使用安全 HTTP 备用通道" }

mountProductPage(<ChatPage />)
