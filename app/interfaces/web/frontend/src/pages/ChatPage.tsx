import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
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
import { AccountMenu } from "../components/AccountMenu"
import { Avatar } from "../components/Avatar"
import { ElfieProfilePanel } from "../components/ElfieProfilePanel"
import { Icon } from "../components/Icon"
import { MobileAccessDialog } from "../components/MobileAccessDialog"
import { Notice } from "../components/Notice"
import { MOCK_ELFIES } from "../components/owner-card-mock-data"
import { useSession } from "../stores/session"
import { usePresenceHeartbeat } from "../stores/heartbeat"

type ChatData = {
  readonly elfies: readonly ElfieProfile[]
  readonly conversations: readonly Conversation[]
}

type ChatPane = "chats" | "elfies"

function createDemoChatData(): ChatData {
  const demoElfies = MOCK_ELFIES.map((entry) => entry.profile)
  return {
    elfies: demoElfies,
    conversations: demoElfies.map((entry) => ({
      elfie_id: entry.elfie_id,
      name: entry.name,
      portrait_url: entry.portrait_url,
      last_message_preview: "演示聊天记录",
      last_message_at: null,
    })),
  }
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

function connectionCopy(status: ChatSocketStatus): string {
  return status === "online" ? "实时" : "离线备用"
}

export function ChatPage() {
  const { user, loading, refresh } = useSession()
  usePresenceHeartbeat(user)
  const socket = useRef<ChatSocket | null>(null)
  const [data, setData] = useState<ChatData | null>(null)
  const [activePane, setActivePane] = useState<ChatPane>("chats")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [history, setHistory] = useState<readonly ChatMessage[]>([])
  const [selectedProfile, setSelectedProfile] = useState<ElfieProfile | null>(null)
  const [status, setStatus] = useState<ChatSocketStatus>("offline")
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [demoMode, setDemoMode] = useState(false)
  const [draft, setDraft] = useState("")
  const [showAdoption, setShowAdoption] = useState(false)
  const [showMobileAccess, setShowMobileAccess] = useState(false)

  useEffect(() => {
    if (user === null) return
    void Promise.all([elfies(), conversations()])
      .then(([ownedElfies, rows]) => {
        if (ownedElfies.length === 0 && rows.length === 0) {
          const demoData = createDemoChatData()
          setData(demoData)
          setSelectedId(demoData.elfies[0]?.elfie_id ?? null)
          setDemoMode(true)
          setError(null)
          setNotice("后端暂不可用，当前显示演示数据")
          return
        }
        setData({ elfies: ownedElfies, conversations: rows })
        const requested = new URLSearchParams(window.location.search).get("elfie")
        setSelectedId(requested ?? rows[0]?.elfie_id ?? ownedElfies[0]?.elfie_id ?? null)
        setDemoMode(false)
        setError(null)
        setNotice(null)
      })
      .catch(() => {
        const demoData = createDemoChatData()
        setData(demoData)
        setSelectedId(demoData.elfies[0]?.elfie_id ?? null)
        setDemoMode(true)
        setError(null)
        setNotice("后端暂不可用，当前显示演示数据")
      })
  }, [user])

  useEffect(() => {
    if (selectedId === null || demoMode) {
      setHistory([])
      return
    }
    void messages(selectedId)
      .then(setHistory)
      .catch((reason: unknown) => {
        setError(reason instanceof ApiError ? reason.message : "聊天记录加载失败")
      })
  }, [demoMode, selectedId])

  useEffect(() => {
    if (selectedId === null || activePane !== "elfies" || demoMode) return
    void profile(selectedId)
      .then(setSelectedProfile)
      .catch((reason: unknown) => {
        setError(reason instanceof ApiError ? reason.message : "精灵资料加载失败")
      })
  }, [activePane, demoMode, selectedId])

  useEffect(() => {
    if (user === null || demoMode) return undefined
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
  }, [demoMode, selectedId, user])

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
    setDemoMode(false)
    setNotice(null)
  }
  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (selectedId === null || !draft.trim() || demoMode) return
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
          <nav className="rail-nav">
            <Button aria-label="聊天记录" className={activePane === "chats" ? "rail-button rail-button--active" : "rail-button"} data-tooltip="聊天记录" onClick={() => setActivePane("chats")} size="icon" type="button" variant="ghost"><Icon name="messages-square" /></Button>
            <Button aria-label="我的精灵" className={activePane === "elfies" ? "rail-button rail-button--active" : "rail-button"} data-tooltip="我的精灵" onClick={() => setActivePane("elfies")} size="icon" type="button" variant="ghost"><Icon name="users" /></Button>
          </nav>
          <div className="rail-bottom">
            <div className="rail-quick-actions">
              {user.role === "owner" ? <Button asChild className="rail-button rail-button--manage" data-tooltip="进入管理" size="icon" variant="ghost"><a aria-label="进入管理" href="/manage"><Icon name="house" /></a></Button> : null}
              <Button aria-label="扫码用手机打开聊天" className="rail-button" data-tooltip="扫码用手机打开聊天" onClick={() => setShowMobileAccess(true)} size="icon" type="button" variant="ghost"><Icon name="qr-code" /></Button>
            </div>
            <AccountMenu compact onUpdated={refresh} user={user} />
          </div>
        </aside>

        <aside className="chat-list-pane">
          <header className="list-pane-head">
            <div>
              <h1>{activePane === "chats" ? "消息" : "精灵"}</h1>
            </div>
            <Button className="add-button" onClick={() => setShowAdoption(true)} size="icon-sm" type="button" variant="outline" aria-label="领养精灵"><Icon name="plus" /></Button>
          </header>
          <label className="search-box" aria-label="搜索">
            <Icon name="search" size={16} />
            <Input placeholder={activePane === "chats" ? "搜索聊天" : "搜索精灵"} />
          </label>
          {activePane === "chats" ? (
            <div className="chat-list">
              {data?.conversations.map((row) => (
                <Button className={row.elfie_id === selectedId ? "wechat-row wechat-row--active" : "wechat-row"} key={row.elfie_id} onClick={() => chooseChat(row.elfie_id)} type="button" variant="ghost">
                  <Avatar name={row.name} />
                  <span className="list-copy"><strong>{row.name}</strong><small>{row.last_message_preview || "还没有消息"}</small></span>
                </Button>
              ))}
              {data?.conversations.length === 0 ? <p className="empty">还没有聊天记录。</p> : null}
            </div>
          ) : (
            <div className="chat-list">
              {data?.elfies.map((entry) => (
                <Button className={entry.elfie_id === selectedId ? "wechat-row wechat-row--active" : "wechat-row"} key={entry.elfie_id} onClick={() => chooseElfie(entry.elfie_id)} type="button" variant="ghost">
                  <Avatar name={entry.name} />
                  <span className="list-copy"><strong>{entry.name}</strong><small>{entry.species_id} · {entry.embodiment.state}</small></span>
                </Button>
              ))}
              {data?.elfies.length === 0 ? <p className="empty">还没有精灵，点右上角的添加按钮领养。</p> : null}
            </div>
          )}
          <p className="connection-state">通道：{connectionCopy(status)}</p>
        </aside>

        {activePane === "chats" ? (
          <section className="conversation">
            <div className="topline">
              <h1>{selected?.name ?? "选择一只精灵"}</h1>
              <Button variant="outline" disabled={selected === undefined} onClick={openDetail} type="button">详情</Button>
            </div>
            <section className="message-list">
              {selectedId === null ? <p className="empty">先在“我的精灵”中领养或选择一只精灵。</p> : history.map((message) => <MessageBubble key={message.id} message={message} />)}
              {notice ? <Notice message={notice} /> : null}
              {error && <Notice kind="error" message={error} />}
            </section>
            <form className="composer" onSubmit={(event) => { void submit(event) }}>
              <Textarea disabled={selected === undefined || demoMode} onChange={(event) => setDraft(event.target.value)} placeholder={selected ? `对 ${selected.name} 说点什么…` : "请选择精灵"} value={draft} />
              <Button disabled={selected === undefined || !draft.trim() || demoMode} type="submit">发送</Button>
            </form>
          </section>
        ) : (
          <ElfieProfilePanel profile={detailProfile} />
        )}
      </section>
      {showAdoption ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="adoption-modal">
            <Button aria-label="关闭" className="modal-close" onClick={() => setShowAdoption(false)} size="icon" type="button" variant="ghost"><Icon name="x" /></Button>
            <AdoptionPanel csrfToken={user.csrf_token ?? ""} onAdopted={adoptionCompleted} />
          </div>
        </div>
      ) : null}
      {showMobileAccess ? <MobileAccessDialog onClose={() => setShowMobileAccess(false)} targetPath="/chat" /> : null}
    </main>
  )
}
