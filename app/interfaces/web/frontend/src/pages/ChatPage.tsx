import { Button } from "@/components/ui/button"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { ChatSocket } from "../api/chat-socket"
import { ApiError } from "../api/http"
import {
  conversations,
  elfies,
  messages,
  profile,
  sendMessage,
  type ChatMessage,
  type ElfieProfile,
} from "../api/client"
import { AdoptionPanel } from "../components/AdoptionPanel"
import { AccountMenuPanel } from "../components/AccountMenu"
import { AccountIdentityAvatar } from "../components/AccountIdentity"
import { ChatRail } from "../components/ChatRail"
import { ElfieProfilePanel } from "../components/ElfieProfilePanel"
import { ChatConversationPane } from "../components/elfie-profile/ChatConversationPane"
import { ChatListPane } from "../components/elfie-profile/ChatListPane"
import { createDemoChatData, createElfieListItems, createOwnedChatData, type ChatData } from "../components/elfie-profile/chat-data"
import type { ElfieListFilter } from "../components/elfie-profile/elfie-list-model"
import { presentElfieProfile } from "../components/elfie-profile/profile-presentation"
import { Icon } from "../components/Icon"
import { MobileAccessDialog } from "../components/MobileAccessDialog"
import { localizeBackendDetail } from "../i18n/errors"
import { currentLocale } from "../i18n/format"
import { useSession } from "../stores/session"
import { usePresenceHeartbeat } from "../stores/heartbeat"
import { useChatView } from "./use-chat-view"

type MobileSection = "chats" | "elfies" | "me"
type ChatFailure = { readonly detail: string | null; readonly operation: "chat.connect" | "chat.load" | "chat.send" }

export function ChatPage() {
  const { i18n, t } = useTranslation("chat")
  const { user, loading, refresh } = useSession()
  usePresenceHeartbeat(user)
  const { activePane, correct, go, mobileDetail, selectedId, state: viewState } = useChatView()
  const socket = useRef<ChatSocket | null>(null)
  const [data, setData] = useState<ChatData | null>(null)
  const [showMobileMe, setShowMobileMe] = useState(false)
  const [history, setHistory] = useState<readonly ChatMessage[]>([])
  const [selectedProfile, setSelectedProfile] = useState<ElfieProfile | null>(null)
  const [failure, setFailure] = useState<ChatFailure | null>(null)
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
          setFailure(null)
          return
        }
        setData(createOwnedChatData(ownedElfies, rows, user.account_id))
        setDemoMode(false)
        setFailure(null)
      })
      .catch(() => {
        const demoData = createDemoChatData()
        setData(demoData)
        setDemoMode(true)
        setFailure(null)
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
        setFailure({ detail: reason instanceof ApiError ? reason.message : null, operation: "chat.load" })
      })
  }, [demoMode, selectedId])

  useEffect(() => {
    setSelectedProfile(null)
    if (selectedId === null || viewState.view !== "profile" || demoMode) return
    void profile(selectedId)
      .then(setSelectedProfile)
      .catch((reason: unknown) => {
        setFailure({ detail: reason instanceof ApiError ? reason.message : null, operation: "chat.load" })
      })
  }, [demoMode, selectedId, viewState.view])

  useEffect(() => {
    if (user === null || demoMode) return undefined
    const realtime = new ChatSocket({
      onStatus: () => undefined,
      onEvent: (event) => {
        switch (event.event) {
          case "error": setFailure({ detail: event.detail, operation: "chat.connect" }); return
          case "message":
            if (event.message.elfie_id === selectedId) setHistory((current) =>
              current.some((row) => row.id === event.message.id) ? current : [...current, event.message],
            )
            return
          case "ready": return
          default: event satisfies never
        }
      },
    })
    socket.current = realtime
    realtime.connect()
    return () => realtime.close()
  }, [demoMode, selectedId, user])

  if (loading) return <main className="page"><p className="empty">{t("loading")}</p></main>
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
      setFailure({ detail: reason instanceof ApiError ? reason.message : null, operation: "chat.send" })
    }
  }

  return (
    <main className="app-page chat-page">
      <section className="chat-workbench">
        <ChatRail activePane={activePane} onMobileAccess={() => setShowMobileAccess(true)} onOpenSection={openMobileSection} onUpdated={refresh} user={user} />

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
            error={failure === null ? null : localizeBackendDetail(failure.detail, failure.operation, currentLocale(i18n))}
            history={history}
            mobileDetail={mobileDetail}
            notice={demoMode ? t("notices.demo") : null}
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
        <nav className="mobile-tabbar" aria-label={t("navigation.mobileLabel")}>
          <Button aria-label={t("navigation.chats")} className={mobileSection === "chats" ? "mobile-tabbar__item mobile-tabbar__item--active" : "mobile-tabbar__item"} onClick={() => openMobileSection("chats")} type="button" variant="ghost"><Icon name="messages-square" size={20} /><span>{t("navigation.chatsShort")}</span></Button>
          <Button aria-label={t("navigation.elfies")} className={mobileSection === "elfies" ? "mobile-tabbar__item mobile-tabbar__item--active" : "mobile-tabbar__item"} onClick={() => openMobileSection("elfies")} type="button" variant="ghost"><Icon name="users" size={20} /><span>{t("navigation.elfiesShort")}</span></Button>
          <Button aria-label={t("navigation.me")} className={mobileSection === "me" ? "mobile-tabbar__item mobile-tabbar__item--active" : "mobile-tabbar__item"} onClick={() => openMobileSection("me")} type="button" variant="ghost"><AccountIdentityAvatar user={user} /><span>{t("navigation.me")}</span></Button>
        </nav>
      </section>
      {showAdoption ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="adoption-modal">
            <Button aria-label={t("adoption.close")} className="modal-close" onClick={() => setShowAdoption(false)} size="icon" type="button" variant="ghost"><Icon name="x" /></Button>
            <AdoptionPanel csrfToken={user.csrf_token ?? ""} onAdopted={adoptionCompleted} />
          </div>
        </div>
      ) : null}
      {showMobileAccess ? <MobileAccessDialog onClose={() => setShowMobileAccess(false)} targetPath="/chat" /> : null}
    </main>
  )
}
