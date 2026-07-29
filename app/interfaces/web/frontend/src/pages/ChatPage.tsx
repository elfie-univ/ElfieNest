import { Button } from "@/components/ui/button"
import { useEffect, useRef, useState } from "react"

import { ChatSocket, type ChatSocketStatus } from "../api/chat-socket"
import {
  ApiError,
  conversations,
  elfies,
  messages,
  profile,
  sendMessage,
  type ChatMessage,
  type ElfieProfile,
} from "../api/client"
import { AdoptionPanel } from "../components/AdoptionPanel"
import { AccountMenu, AccountMenuPanel } from "../components/AccountMenu"
import { Avatar } from "../components/Avatar"
import { ElfieProfilePanel } from "../components/ElfieProfilePanel"
import { ChatConversationPane } from "../components/elfie-profile/ChatConversationPane"
import { ChatListPane } from "../components/elfie-profile/ChatListPane"
import { createDemoChatData, createElfieListItems, createOwnedChatData, type ChatData } from "../components/elfie-profile/chat-data"
import type { ElfieListFilter } from "../components/elfie-profile/elfie-list-model"
import { presentElfieProfile } from "../components/elfie-profile/profile-presentation"
import { Icon } from "../components/Icon"
import { MobileAccessDialog } from "../components/MobileAccessDialog"
import { useSession } from "../stores/session"
import { usePresenceHeartbeat } from "../stores/heartbeat"
import { useChatView } from "./use-chat-view"

type MobileSection = "chats" | "elfies" | "me"

export function ChatPage() {
  const { user, loading, refresh } = useSession()
  usePresenceHeartbeat(user)
  const { activePane, correct, go, mobileDetail, selectedId, state: viewState } = useChatView()
  const socket = useRef<ChatSocket | null>(null)
  const [data, setData] = useState<ChatData | null>(null)
  const [showMobileMe, setShowMobileMe] = useState(false)
  const [history, setHistory] = useState<readonly ChatMessage[]>([])
  const [selectedProfile, setSelectedProfile] = useState<ElfieProfile | null>(null)
  const [status, setStatus] = useState<ChatSocketStatus>("offline")
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [demoMode, setDemoMode] = useState(false)
  const [draft, setDraft] = useState("")
  const [showAdoption, setShowAdoption] = useState(false)
  const [showMobileAccess, setShowMobileAccess] = useState(false)
  const [elfieQuery, setElfieQuery] = useState("")
  const [elfieFilter, setElfieFilter] = useState<ElfieListFilter>("all")

  useEffect(() => {
    if (user === null) return
    void Promise.all([elfies(), conversations()])
      .then(([ownedElfies, rows]) => {
        if (ownedElfies.length === 0 && rows.length === 0) {
          const demoData = createDemoChatData()
          setData(demoData)
          setDemoMode(true)
          setError(null)
          setNotice("后端暂不可用，当前显示演示数据")
          return
        }
        setData(createOwnedChatData(ownedElfies, rows, user.account_id))
        setDemoMode(false)
        setError(null)
        setNotice(null)
      })
      .catch(() => {
        const demoData = createDemoChatData()
        setData(demoData)
        setDemoMode(true)
        setError(null)
        setNotice("后端暂不可用，当前显示演示数据")
      })
  }, [user])

  useEffect(() => {
    if (data === null || selectedId === null) return
    if (!data.elfies.some((entry) => entry.elfie_id === selectedId)) correct({ view: "elfies" })
  }, [correct, data, selectedId])

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
    setSelectedProfile(null)
    if (selectedId === null || viewState.view !== "profile" || demoMode) return
    void profile(selectedId)
      .then(setSelectedProfile)
      .catch((reason: unknown) => {
        setError(reason instanceof ApiError ? reason.message : "精灵资料加载失败")
      })
  }, [demoMode, selectedId, viewState.view])

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
  const mobileSection: MobileSection = showMobileMe ? "me" : activePane
  const chooseChat = (elfieId: string): void => {
    setShowMobileMe(false)
    go({ view: "conversation", elfie: elfieId })
  }
  const chooseElfie = (elfieId: string): void => {
    setShowMobileMe(false)
    go({ view: "profile", elfie: elfieId })
  }
  const openMobileSection = (section: MobileSection): void => {
    if (section === "me") {
      setShowMobileMe(true)
      return
    }
    setShowMobileMe(false)
    if (section === "elfies") {
      go({ view: "elfies" })
      return
    }
    const chatId = selectedId ?? data?.conversations[0]?.elfie_id ?? data?.elfies[0]?.elfie_id
    if (chatId !== undefined) go({ view: "conversation", elfie: chatId })
  }
  const adoptionCompleted = async (elfieId: string): Promise<void> => {
    const [ownedElfies, rows, loadedProfile] = await Promise.all([
      elfies(),
      conversations(),
      profile(elfieId),
    ])
    setData(createOwnedChatData(ownedElfies, rows, user.account_id))
    setSelectedProfile(loadedProfile)
    go({ view: "profile", elfie: elfieId })
    setShowAdoption(false)
    setDemoMode(false)
    setNotice(null)
  }
  const submit = async (): Promise<void> => {
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
    <main className="app-page chat-page">
      <section className="chat-workbench">
        <aside className="app-rail" aria-label="ElfieNest 导航">
          <nav className="rail-nav">
            <Button aria-label="聊天记录" className={activePane === "chats" ? "rail-button rail-button--active" : "rail-button"} data-tooltip="聊天记录" onClick={() => openMobileSection("chats")} size="icon" type="button" variant="ghost"><Icon name="messages-square" /></Button>
            <Button aria-label="我的精灵" className={activePane === "elfies" ? "rail-button rail-button--active" : "rail-button"} data-tooltip="我的精灵" onClick={() => openMobileSection("elfies")} size="icon" type="button" variant="ghost"><Icon name="users" /></Button>
          </nav>
          <div className="rail-bottom">
            <div className="rail-quick-actions">
              {user.role === "owner" ? <Button asChild className="rail-button rail-button--manage" data-tooltip="进入管理" size="icon" variant="ghost"><a aria-label="进入管理" href="/manage"><Icon name="house" /></a></Button> : null}
              <Button aria-label="扫码用手机打开聊天" className="rail-button rail-button--mobile-access" data-tooltip="扫码用手机打开聊天" onClick={() => setShowMobileAccess(true)} size="icon" type="button" variant="ghost"><Icon name="qr-code" /></Button>
            </div>
            <AccountMenu compact onUpdated={refresh} user={user} />
          </div>
        </aside>

        <ChatListPane
          activePane={activePane}
          conversations={data?.conversations ?? []}
          elfieFilter={elfieFilter}
          elfieItems={createElfieListItems(data)}
          elfieQuery={elfieQuery}
          hiddenOnMobile={mobileSection === "me" || mobileDetail}
          onAdopt={() => setShowAdoption(true)}
          onChat={chooseChat}
          onElfieFilterChange={setElfieFilter}
          onElfieProfile={chooseElfie}
          onElfieQueryChange={setElfieQuery}
          selectedId={selectedId}
          status={status}
          viewerAccountId={user.account_id}
        />

        {mobileSection === "me" ? (
          <section className="mobile-me-pane">
            <AccountMenuPanel onClose={() => openMobileSection("chats")} onUpdated={refresh} user={user} />
          </section>
        ) : activePane === "chats" ? (
          <ChatConversationPane
            demoMode={demoMode}
            draft={draft}
            error={error}
            history={history}
            mobileDetail={mobileDetail}
            notice={notice}
            onBack={() => go({ view: "elfies" })}
            onDraftChange={setDraft}
            onOpenDetail={() => { if (selectedId !== null) go({ view: "profile", elfie: selectedId }) }}
            onSubmit={submit}
            selected={selected}
            selectedId={selectedId}
          />
        ) : (
          <section className={mobileDetail ? "elfie-detail-pane elfie-detail-pane--mobile-active" : "elfie-detail-pane"}>
            <ElfieProfilePanel
              onBack={() => go({ view: "elfies" })}
              onChat={() => { if (selectedId !== null) go({ view: "conversation", elfie: selectedId }) }}
              projection={presentElfieProfile(selectedProfile ?? selected ?? null, user.account_id, selectedId === null ? null : data?.adopterAccountIds[selectedId] ?? null)}
            />
          </section>
        )}
        <nav className="mobile-tabbar" aria-label="聊天移动导航">
          <Button aria-label="聊天记录" className={mobileSection === "chats" ? "mobile-tabbar__item mobile-tabbar__item--active" : "mobile-tabbar__item"} onClick={() => openMobileSection("chats")} type="button" variant="ghost"><Icon name="messages-square" size={20} /><span>消息</span></Button>
          <Button aria-label="我的精灵" className={mobileSection === "elfies" ? "mobile-tabbar__item mobile-tabbar__item--active" : "mobile-tabbar__item"} onClick={() => openMobileSection("elfies")} type="button" variant="ghost"><Icon name="users" size={20} /><span>精灵</span></Button>
          <Button aria-label="我的" className={mobileSection === "me" ? "mobile-tabbar__item mobile-tabbar__item--active" : "mobile-tabbar__item"} onClick={() => openMobileSection("me")} type="button" variant="ghost"><Avatar imageUrl={user.avatar_url} name={user.nickname?.trim() || user.username} /><span>我的</span></Button>
        </nav>
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
