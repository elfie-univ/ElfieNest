import { useEffect, useRef, useState, type FormEvent } from "react"

import { ChatSocket, type ChatSocketStatus } from "../api/chat-socket"
import {
  ApiError,
  conversations,
  elfies,
  messages,
  profile,
  sendMessage,
  type ChatMessage,
  type Conversation,
  type ElfieProfile,
} from "../api/client"
import { AdoptionPanel } from "../components/AdoptionPanel"
import { Avatar } from "../components/Avatar"
import { ElfieProfilePanel } from "../components/ElfieProfilePanel"
import { Notice } from "../components/Notice"
import { useSession } from "../stores/session"

type ChatData = {
  readonly elfies: readonly ElfieProfile[]
  readonly conversations: readonly Conversation[]
}

type ChatPane = "chats" | "elfies"

function MessageBubble({ message }: { readonly message: ChatMessage }) {
  const senderName = message.sender === "user" ? "我" : "精"
  return (
    <article className={`message${message.sender === "user" ? " message--user" : ""}`}>
      <Avatar name={senderName} />
      <div className="bubble">{message.text}</div>
    </article>
  )
}

function connectionCopy(status: ChatSocketStatus): string {
  return status === "online" ? "实时" : "离线备用"
}

export function ChatPage() {
  const { user, loading } = useSession()
  const socket = useRef<ChatSocket | null>(null)
  const [data, setData] = useState<ChatData | null>(null)
  const [activePane, setActivePane] = useState<ChatPane>("chats")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [history, setHistory] = useState<readonly ChatMessage[]>([])
  const [selectedProfile, setSelectedProfile] = useState<ElfieProfile | null>(null)
  const [status, setStatus] = useState<ChatSocketStatus>("offline")
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState("")
  const [showAdoption, setShowAdoption] = useState(false)

  useEffect(() => {
    if (user === null) return
    void Promise.all([elfies(), conversations()])
      .then(([ownedElfies, rows]) => {
        setData({ elfies: ownedElfies, conversations: rows })
        const requested = new URLSearchParams(window.location.search).get("elfie")
        setSelectedId(requested ?? rows[0]?.elfie_id ?? ownedElfies[0]?.elfie_id ?? null)
      })
      .catch((reason: unknown) => {
        setError(reason instanceof ApiError ? reason.message : "聊天资料加载失败")
      })
  }, [user])

  useEffect(() => {
    if (selectedId === null) {
      setHistory([])
      return
    }
    void messages(selectedId)
      .then(setHistory)
      .catch((reason: unknown) => {
        setError(reason instanceof ApiError ? reason.message : "聊天记录加载失败")
      })
  }, [selectedId])

  useEffect(() => {
    if (selectedId === null || activePane !== "elfies") return
    void profile(selectedId)
      .then(setSelectedProfile)
      .catch((reason: unknown) => {
        setError(reason instanceof ApiError ? reason.message : "精灵资料加载失败")
      })
  }, [activePane, selectedId])

  useEffect(() => {
    if (user === null) return undefined
    const realtime = new ChatSocket({
      onStatus: setStatus,
      onEvent: (event) => {
        if (event.event === "error") {
          setError(event.detail)
          return
        }
        if (event.event === "message" && event.message.elfie_id === selectedId) {
          setHistory((current) =>
            current.some((row) => row.id === event.message.id)
              ? current
              : [...current, event.message],
          )
        }
      },
    })
    socket.current = realtime
    realtime.connect()
    return () => realtime.close()
  }, [selectedId, user])

  if (loading) return <main className="page"><p className="empty">正在验证会话…</p></main>
  if (user === null) {
    window.location.assign("/login?next=/chat")
    return <main />
  }

  const selected = data?.elfies.find((entry) => entry.elfie_id === selectedId)
  const detailProfile = selectedProfile ?? selected ?? null
  const chooseChat = (elfieId: string): void => {
    setActivePane("chats")
    setSelectedId(elfieId)
  }
  const chooseElfie = (elfieId: string): void => {
    setActivePane("elfies")
    setSelectedId(elfieId)
  }
  const openDetail = (): void => {
    if (selectedId === null) return
    setActivePane("elfies")
  }
  const adoptionCompleted = async (elfieId: string): Promise<void> => {
    const [ownedElfies, rows, loadedProfile] = await Promise.all([
      elfies(),
      conversations(),
      profile(elfieId),
    ])
    setData({ elfies: ownedElfies, conversations: rows })
    setSelectedId(elfieId)
    setSelectedProfile(loadedProfile)
    setActivePane("elfies")
    setShowAdoption(false)
  }
  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (selectedId === null || !draft.trim()) return
    const text = draft.trim()
    setDraft("")
    try {
      if (!socket.current?.send(selectedId, text)) {
        const message = await sendMessage(selectedId, text, user.csrf_token ?? "")
        setHistory((current) => [...current, message])
      }
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "消息没有送达")
    }
  }

  return (
    <main className="app-page">
      <section className="chat-workbench">
        <aside className="app-rail" aria-label="ElfieNest 导航">
          <div className="rail-avatar"><Avatar name={user.username} /></div>
          <nav className="rail-nav">
            <button className={activePane === "chats" ? "rail-button rail-button--active" : "rail-button"} onClick={() => setActivePane("chats")} type="button" aria-label="聊天记录">💬</button>
            <button className={activePane === "elfies" ? "rail-button rail-button--active" : "rail-button"} onClick={() => setActivePane("elfies")} type="button" aria-label="我的精灵">🦊</button>
          </nav>
          <div className="rail-bottom">
            {user.role === "owner" ? <a className="rail-button rail-button--manager" href="/manage" aria-label="进入管理">管</a> : null}
            <button className="rail-button" type="button" aria-label="设置">☰</button>
          </div>
        </aside>

        <aside className="chat-list-pane">
          <header className="list-pane-head">
            <div>
              <p className="brand">{activePane === "chats" ? "聊天记录" : "我的精灵"}</p>
              <h1>{activePane === "chats" ? "消息" : "精灵"}</h1>
            </div>
            <button className="add-button" onClick={() => setShowAdoption(true)} type="button" aria-label="领养精灵">＋</button>
          </header>
          <label className="search-box" aria-label="搜索">
            <span>⌕</span>
            <input placeholder={activePane === "chats" ? "搜索聊天" : "搜索精灵"} />
          </label>
          {activePane === "chats" ? (
            <div className="chat-list">
              {data?.conversations.map((row) => (
                <button className={row.elfie_id === selectedId ? "wechat-row wechat-row--active" : "wechat-row"} key={row.elfie_id} onClick={() => chooseChat(row.elfie_id)} type="button">
                  <Avatar name={row.name} />
                  <span className="list-copy"><strong>{row.name}</strong><small>{row.last_message_preview || "还没有消息"}</small></span>
                </button>
              ))}
              {data?.conversations.length === 0 ? <p className="empty">还没有聊天记录。</p> : null}
            </div>
          ) : (
            <div className="chat-list">
              {data?.elfies.map((entry) => (
                <button className={entry.elfie_id === selectedId ? "wechat-row wechat-row--active" : "wechat-row"} key={entry.elfie_id} onClick={() => chooseElfie(entry.elfie_id)} type="button">
                  <Avatar name={entry.name} />
                  <span className="list-copy"><strong>{entry.name}</strong><small>{entry.species_id} · {entry.embodiment.state}</small></span>
                </button>
              ))}
              {data?.elfies.length === 0 ? <p className="empty">还没有精灵，点右上角 ＋ 领养。</p> : null}
            </div>
          )}
          <p className="connection-state">通道：{connectionCopy(status)}</p>
        </aside>

        {activePane === "chats" ? (
          <section className="conversation">
            <div className="topline">
              <h1>{selected?.name ?? "选择一只精灵"}</h1>
              <button className="button button--quiet" disabled={selected === undefined} onClick={openDetail} type="button">详情</button>
            </div>
            <section className="message-list">
              {selectedId === null ? <p className="empty">先在“我的精灵”中领养或选择一只精灵。</p> : history.map((message) => <MessageBubble key={message.id} message={message} />)}
              {error && <Notice kind="error" message={error} />}
            </section>
            <form className="composer" onSubmit={(event) => { void submit(event) }}>
              <textarea disabled={selected === undefined} onChange={(event) => setDraft(event.target.value)} placeholder={selected ? `对 ${selected.name} 说点什么…` : "请选择精灵"} value={draft} />
              <button className="button" disabled={selected === undefined || !draft.trim()} type="submit">发送</button>
            </form>
          </section>
        ) : (
          <ElfieProfilePanel profile={detailProfile} />
        )}
      </section>
      {showAdoption ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="adoption-modal">
            <button className="modal-close" onClick={() => setShowAdoption(false)} type="button" aria-label="关闭">×</button>
            <AdoptionPanel csrfToken={user.csrf_token ?? ""} onAdopted={adoptionCompleted} />
          </div>
        </div>
      ) : null}
    </main>
  )
}
