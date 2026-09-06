import { Button } from "@/components/ui/button"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { ChatSocket } from "../api/chat-socket"
import {
  conversations,
  messages,
  sendMessage,
  type ChatMessage,
} from "../api/communication"
import { ApiError } from "../api/http"
import {
  adoptionInfo,
  discordAccount,
  elfies,
  elfieFoodPolicy,
  profile,
  telegramAccount,
  type DiscordAccount,
  type TelegramAccount,
  type ElfieFoodPolicy,
  type ElfieProfileDetail,
  type AdoptionSpecies,
} from "../api/client"
import { AdoptionJourneyDialog } from "../components/adoption/AdoptionJourneyDialog"
import { AccountMenuPanel } from "../components/AccountMenu"
import { accountDisplayName, AccountIdentityAvatar } from "../components/AccountIdentity"
import { ChatRail } from "../components/ChatRail"
import { ElfieProfilePanel } from "../components/ElfieProfilePanel"
import { ChatConversationPane } from "../components/elfie-profile/ChatConversationPane"
import { ChatListPane } from "../components/elfie-profile/ChatListPane"
import { createElfieListItems, createOwnedChatData, recordChatMessage, replaceElfiePortrait, type ChatData } from "../components/elfie-profile/chat-data"
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
const REPLY_RECONCILE_INTERVAL_MILLISECONDS = 500
const REPLY_RECONCILE_TIMEOUT_MILLISECONDS = 120_000

function mergeChatMessages(
  current: readonly ChatMessage[],
  incoming: readonly ChatMessage[],
): readonly ChatMessage[] {
  const pending = current.filter((message) => message.id < 0)
  const unmatchedPending = [...pending]
  for (const message of incoming) {
    if (message.sender !== "user") continue
    const pendingIndex = unmatchedPending.findIndex((candidate) => (
      candidate.elfie_id === message.elfie_id && candidate.text === message.text
    ))
    if (pendingIndex !== -1) unmatchedPending.splice(pendingIndex, 1)
  }
  const byId = new Map(
    current
      .filter((message) => message.id >= 0)
      .map((message) => [message.id, message]),
  )
  for (const message of unmatchedPending) byId.set(message.id, message)
  for (const message of incoming) byId.set(message.id, message)
  return [...byId.values()].sort((left, right) => {
    const byTime = compareStableText(left.created_at, right.created_at)
    return byTime === 0 ? left.id - right.id : byTime
  })
}

function compareStableText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0
}

export function ChatPage() {
  const { i18n, t } = useTranslation("chat")
  const { user, loading, refresh, refreshCsrfToken } = useSession()
  usePresenceHeartbeat(user)
  const { activePane, correct, go, mobileDetail, selectedId, state: viewState } = useChatView()
  const socket = useRef<ChatSocket | null>(null)
  const [data, setData] = useState<ChatData | null>(null)
  const [showMobileMe, setShowMobileMe] = useState(false)
  const [history, setHistory] = useState<readonly ChatMessage[]>([])
  const [selectedProfile, setSelectedProfile] = useState<ElfieProfileDetail | null>(null)
  const [selectedFoodPolicy, setSelectedFoodPolicy] = useState<ElfieFoodPolicy | null>(null)
  const [selectedTelegramAccount, setSelectedTelegramAccount] = useState<TelegramAccount | null>(null)
  const [selectedDiscordAccount, setSelectedDiscordAccount] = useState<DiscordAccount | null>(null)
  const [telegramAccountLoading, setTelegramAccountLoading] = useState(false)
  const [telegramAccountError, setTelegramAccountError] = useState<string | null>(null)
  const [discordAccountLoading, setDiscordAccountLoading] = useState(false)
  const [discordAccountError, setDiscordAccountError] = useState<string | null>(null)
  const [speciesCatalog, setSpeciesCatalog] = useState<ReadonlyMap<string, AdoptionSpecies>>(() => new Map())
  const [failure, setFailure] = useState<ChatFailure | null>(null)
  const [draft, setDraft] = useState("")
  const [showAdoption, setShowAdoption] = useState(false)
  const [showMobileAccess, setShowMobileAccess] = useState(false)
  const [elfieQuery, setElfieQuery] = useState("")
  const [elfieFilter, setElfieFilter] = useState<ElfieListFilter>("all")
  const reconcileTimerRef = useRef<number | null>(null)
  const reconcileGenerationRef = useRef(0)
  const dataLoadGenerationRef = useRef(0)
  const historyLoadGenerationRef = useRef(0)
  const optimisticMessageSequenceRef = useRef(0)

  const clearReplyReconciliation = useCallback((): void => {
    if (reconcileTimerRef.current !== null) window.clearTimeout(reconcileTimerRef.current)
    reconcileTimerRef.current = null
  }, [])

  const mergeLoadedHistory = useCallback((loaded: readonly ChatMessage[]): void => {
    setHistory((current) => mergeChatMessages(current, loaded))
    setData((current) => current === null
      ? current
      : loaded.reduce((next, message) => recordChatMessage(next, message), current))
  }, [])

  const reconcileReply = useCallback((elfieId: string, knownMessageIds: ReadonlySet<number>): void => {
    clearReplyReconciliation()
    const generation = reconcileGenerationRef.current + 1
    reconcileGenerationRef.current = generation
    const startedAt = Date.now()
    const poll = async (): Promise<void> => {
      if (reconcileGenerationRef.current !== generation) return
      try {
        const loaded = await messages(elfieId)
        if (reconcileGenerationRef.current !== generation) return
        const scoped = loaded.filter((message) => message.elfie_id === elfieId)
        mergeLoadedHistory(scoped)
        const receivedReply = scoped.some(
          (message) => message.sender === "elfie" && !knownMessageIds.has(message.id),
        )
        if (receivedReply || Date.now() - startedAt >= REPLY_RECONCILE_TIMEOUT_MILLISECONDS) return
      } catch {
        if (reconcileGenerationRef.current !== generation) return
      }
      reconcileTimerRef.current = window.setTimeout(() => { void poll() }, REPLY_RECONCILE_INTERVAL_MILLISECONDS)
    }
    reconcileTimerRef.current = window.setTimeout(() => { void poll() }, REPLY_RECONCILE_INTERVAL_MILLISECONDS)
  }, [clearReplyReconciliation, mergeLoadedHistory])

  useEffect(() => {
    reconcileGenerationRef.current += 1
    clearReplyReconciliation()
  }, [clearReplyReconciliation, selectedId])

  useEffect(() => clearReplyReconciliation, [clearReplyReconciliation])

  useEffect(() => {
    if (user === null) return
    const generation = dataLoadGenerationRef.current + 1
    dataLoadGenerationRef.current = generation
    const load = async (): Promise<readonly [Awaited<ReturnType<typeof elfies>>, Awaited<ReturnType<typeof conversations>>]> => {
      let lastError: unknown
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          return await Promise.all([elfies(), conversations()])
        } catch (reason: unknown) {
          lastError = reason
          if (attempt < 2) await new Promise((resolve) => window.setTimeout(resolve, 300))
        }
      }
      throw lastError
    }
    void load()
      .then(([visibleElfies, rows]) => {
        if (dataLoadGenerationRef.current !== generation) return
        setData(createOwnedChatData(visibleElfies, rows, user.account_id))
      })
      .catch((reason: unknown) => {
        if (dataLoadGenerationRef.current !== generation) return
        setData(null)
        setFailure({ detail: reason instanceof ApiError ? reason.message : null, operation: "chat.load" })
      })
  }, [user])

  useEffect(() => {
    if (user === null) {
      setSpeciesCatalog(new Map())
      return
    }
    void adoptionInfo()
      .then((info) => setSpeciesCatalog(new Map(info.species.map((species) => [species.species_id, species]))))
      .catch(() => setSpeciesCatalog(new Map()))
  }, [user])

  useEffect(() => {
    if (data === null || selectedId === null) return
    setFailure(null)
    if (!data.elfies.some((entry) => entry.elfie_id === selectedId)) correct({ view: "elfies" })
  }, [correct, data, selectedId])

  useEffect(() => {
    const generation = historyLoadGenerationRef.current + 1
    historyLoadGenerationRef.current = generation
    setHistory([])
    if (activePane !== "chats" || selectedId === null) {
      return
    }
    void messages(selectedId)
      .then((loaded) => {
        if (historyLoadGenerationRef.current !== generation) return
        const scoped = loaded.filter((message) => message.elfie_id === selectedId)
        setHistory((current) => mergeChatMessages(current, scoped))
      })
      .catch((reason: unknown) => {
        if (historyLoadGenerationRef.current !== generation) return
        setFailure({ detail: reason instanceof ApiError ? reason.message : null, operation: "chat.load" })
      })
  }, [activePane, selectedId])

  useEffect(() => {
    setSelectedProfile(null)
    setSelectedFoodPolicy(null)
    setSelectedTelegramAccount(null)
    setSelectedDiscordAccount(null)
    setFailure(null)
    setTelegramAccountLoading(false)
    setTelegramAccountError(null)
    setDiscordAccountLoading(false)
    setDiscordAccountError(null)
    if (selectedId === null || viewState.view !== "profile") return
    void Promise.all([profile(selectedId), elfieFoodPolicy(selectedId)])
      .then(async ([loadedProfile, foodPolicy]) => {
        setSelectedProfile(loadedProfile)
        setSelectedFoodPolicy(foodPolicy)
        if (loadedProfile.relationship !== "owned") return
        setTelegramAccountLoading(true)
        setTelegramAccountError(null)
        setDiscordAccountLoading(true)
        setDiscordAccountError(null)
        const results = await Promise.allSettled([
          telegramAccount(selectedId),
          discordAccount(selectedId),
        ])
        const telegramResult = results[0]
        const discordResult = results[1]
        if (telegramResult.status === "fulfilled") setSelectedTelegramAccount(telegramResult.value)
        else setTelegramAccountError(telegramResult.reason instanceof ApiError ? telegramResult.reason.message : null)
        if (discordResult.status === "fulfilled") setSelectedDiscordAccount(discordResult.value)
        else setDiscordAccountError(discordResult.reason instanceof ApiError ? discordResult.reason.message : null)
        setTelegramAccountLoading(false)
        setDiscordAccountLoading(false)
      })
      .catch(() => undefined)
  }, [selectedId, viewState.view])

  useEffect(() => {
    if (user === null) return undefined
    const realtime = new ChatSocket({
      onStatus: () => undefined,
      onEvent: (event) => {
        switch (event.event) {
          case "error": setFailure({ detail: event.detail, operation: "chat.connect" }); return
          case "message":
            setData((current) => current === null ? current : recordChatMessage(current, event.message))
            if (event.message.elfie_id === selectedId) {
              setHistory((current) => mergeChatMessages(current, [event.message]))
            }
            return
          case "ready": return
          default: event satisfies never
        }
      },
    })
    socket.current = realtime
    realtime.connect()
    return () => realtime.close()
  }, [selectedId, user])

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
    if (selectedId === null) {
      go({ view: "chats" })
      return
    }
    go({ view: "conversation", elfie: selectedId })
  }
  const adoptionCompleted = async (elfieId: string): Promise<void> => {
    let visibleElfies: Awaited<ReturnType<typeof elfies>>
    try {
      visibleElfies = await elfies()
    } catch (reason: unknown) {
      setFailure({ detail: reason instanceof ApiError ? reason.message : null, operation: "chat.load" })
      go({ view: "elfies" })
      return
    }
    const orderedElfies = [
      ...visibleElfies.filter((entry) => entry.elfie_id === elfieId),
      ...visibleElfies.filter((entry) => entry.elfie_id !== elfieId),
    ]
    setData((current) => createOwnedChatData(orderedElfies, current?.conversations ?? [], user.account_id))
    setFailure(null)
    go({ view: "conversation", elfie: elfieId })
    void conversations()
      .then((rows) => {
        setData((current) => current === null
          ? current
          : createOwnedChatData(current.elfies, rows, user.account_id))
      })
      .catch((reason: unknown) => {
        setFailure({ detail: reason instanceof ApiError ? reason.message : null, operation: "chat.load" })
      })
  }
  const saveSelectedFood = async (): Promise<void> => {
    if (selectedId === null) return
    const [loadedProfile, foodPolicy] = await Promise.all([
      profile(selectedId),
      elfieFoodPolicy(selectedId),
    ])
    setSelectedProfile(loadedProfile)
    setSelectedFoodPolicy(foodPolicy)
  }
  const handleAvatarSaved = (elfieId: string, portraitUrl: string): void => {
    setData((current) => current === null ? current : replaceElfiePortrait(current, elfieId, portraitUrl))
    setSelectedProfile((current) => current === null || current.elfie_id !== elfieId
      ? current
      : { ...current, portrait_url: portraitUrl })
  }
  const refreshSelectedTelegram = async (): Promise<void> => {
    if (selectedId === null) return
    setTelegramAccountError(null)
    try {
      setSelectedTelegramAccount(await telegramAccount(selectedId))
    } catch (reason: unknown) {
      const detail = reason instanceof ApiError ? reason.message : null
      setTelegramAccountError(detail)
      throw reason
    }
  }
  const refreshSelectedDiscord = async (): Promise<void> => {
    if (selectedId === null) return
    setDiscordAccountError(null)
    try {
      setSelectedDiscordAccount(await discordAccount(selectedId))
    } catch (reason: unknown) {
      const detail = reason instanceof ApiError ? reason.message : null
      setDiscordAccountError(detail)
      throw reason
    }
  }
  const submit = async (): Promise<void> => {
    if (selectedId === null || !draft.trim()) return
    const text = draft.trim()
    const knownMessageIds = new Set(history.map((message) => message.id))
    try {
      const sentRealtime = socket.current?.send(selectedId, text) ?? false
      if (sentRealtime) {
        optimisticMessageSequenceRef.current += 1
        const optimisticMessage: ChatMessage = {
          id: -optimisticMessageSequenceRef.current,
          elfie_id: selectedId,
          sender: "user",
          text,
          created_at: new Date().toISOString(),
        }
        setHistory((current) => mergeChatMessages(current, [optimisticMessage]))
        setData((current) => current === null ? current : recordChatMessage(current, optimisticMessage))
      } else {
        const message = await sendMessage(selectedId, text, user.csrf_token ?? "")
        knownMessageIds.add(message.id)
        setHistory((current) => mergeChatMessages(current, [message]))
        setData((current) => current === null ? current : recordChatMessage(current, message))
      }
      setDraft("")
      reconcileReply(selectedId, knownMessageIds)
    } catch (reason: unknown) {
      setFailure({ detail: reason instanceof ApiError ? reason.message : null, operation: "chat.send" })
    }
  }
  const visibleHistory = selectedId === null
    ? []
    : history.filter((message) => message.elfie_id === selectedId)

  return (
    <main className="app-page chat-page">
      <section className="chat-workbench">
        <ChatRail activePane={activePane} onMobileAccess={() => setShowMobileAccess(true)} onOpenSection={openMobileSection} onUpdated={refresh} user={user} />

        <ChatListPane
          activePane={activePane}
          conversations={data?.conversations ?? []}
          error={failure?.operation === "chat.load" && activePane === "elfies"
            ? localizeBackendDetail(failure.detail, failure.operation, currentLocale(i18n))
            : null}
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
            draft={draft}
            error={failure === null ? null : localizeBackendDetail(failure.detail, failure.operation, currentLocale(i18n))}
            history={visibleHistory}
            mobileDetail={mobileDetail}
            onBack={() => go({ view: "chats" })}
            onDraftChange={setDraft}
            onOpenDetail={() => { if (selectedId !== null) go({ view: "profile", elfie: selectedId }) }}
            onSubmit={submit}
            selected={selected}
            selectedId={selectedId}
            userAvatarUrl={user.avatar_url}
            userDisplayName={accountDisplayName(user)}
          />
        ) : (
          <section className={mobileDetail ? "elfie-detail-pane elfie-detail-pane--mobile-active" : "elfie-detail-pane"}>
            <ElfieProfilePanel
              csrfToken={user.csrf_token ?? ""}
              onBack={() => go({ view: "elfies" })}
              onChat={() => { if (selectedId !== null) go({ view: "conversation", elfie: selectedId }) }}
              onAvatarSaved={handleAvatarSaved}
              onFoodSaved={saveSelectedFood}
              onTelegramAccountChange={setSelectedTelegramAccount}
              onTelegramRefresh={refreshSelectedTelegram}
              onDiscordAccountChange={setSelectedDiscordAccount}
              onDiscordRefresh={refreshSelectedDiscord}
              projection={presentElfieProfile(
                selectedProfile ?? selected ?? null,
                user.account_id,
                selectedId === null ? null : data?.adopterAccountIds[selectedId] || null,
                selectedFoodPolicy,
              )}
              speciesDefinition={selectedProfile?.species
                ?? selected?.species
                ?? speciesCatalog.get(selectedProfile?.species_id ?? selected?.species_id ?? "")}
              telegramAccount={selectedTelegramAccount}
              telegramAccountError={telegramAccountError}
              telegramAccountLoading={telegramAccountLoading}
              discordAccount={selectedDiscordAccount}
              discordAccountError={discordAccountError}
              discordAccountLoading={discordAccountLoading}
            />
          </section>
        )}
        <nav className={mobileDetail ? "mobile-tabbar mobile-tabbar--hidden" : "mobile-tabbar"} aria-label={t("navigation.mobileLabel")}>
          <Button aria-label={t("navigation.chats")} className={mobileSection === "chats" ? "mobile-tabbar__item mobile-tabbar__item--active" : "mobile-tabbar__item"} onClick={() => openMobileSection("chats")} type="button" variant="ghost"><Icon name="messages-square" size={20} /><span>{t("navigation.chatsShort")}</span></Button>
          <Button aria-label={t("navigation.elfies")} className={mobileSection === "elfies" ? "mobile-tabbar__item mobile-tabbar__item--active" : "mobile-tabbar__item"} onClick={() => openMobileSection("elfies")} type="button" variant="ghost"><Icon name="users" size={20} /><span>{t("navigation.elfiesShort")}</span></Button>
          <Button aria-label={t("navigation.me")} className={mobileSection === "me" ? "mobile-tabbar__item mobile-tabbar__item--active" : "mobile-tabbar__item"} onClick={() => openMobileSection("me")} type="button" variant="ghost"><AccountIdentityAvatar user={user} /><span>{t("navigation.me")}</span></Button>
        </nav>
      </section>
      <AdoptionJourneyDialog accountCreatedAt={user.created_at} accountId={user.account_id} csrfToken={user.csrf_token ?? ""} onAdopted={adoptionCompleted} onOpenChange={setShowAdoption} onRefreshCsrfToken={refreshCsrfToken} open={showAdoption} />
      {showMobileAccess ? <MobileAccessDialog onClose={() => setShowMobileAccess(false)} targetPath="/chat" /> : null}
    </main>
  )
}
