import {
  ApiError,
  type ChatMessage,
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
import { ChatSocket, type ChatSocketEvent, type ChatSocketStatus } from "../shared/chat_socket"
import { avatar, clearAndMount, element, notice } from "../shared/ui"

type ChatState = {
  readonly csrfToken: string
  readonly elfies: readonly ElfieProfile[]
  readonly user: Awaited<ReturnType<typeof currentUser>>
  conversations: readonly Conversation[]
  currentMessages: readonly ChatMessage[]
  profile: ElfieProfile | null
  selectedId: string | null
  socketNotice: string | null
  socketStatus: ChatSocketStatus
  unread: ReadonlyMap<string, number>
}

let realtime: ChatSocket | null = null

async function loadState(): Promise<ChatState> {
  const user = await currentUser()
  const [rows, ownedElfies] = await Promise.all([conversations(), elfies()])
  const selectedId = new URLSearchParams(window.location.search).get("elfie") ?? rows[0]?.elfie_id ?? ownedElfies[0]?.elfie_id ?? null
  const currentMessages = selectedId === null ? [] : await messages(selectedId)
  return { user, csrfToken: user.csrf_token ?? "", conversations: rows, elfies: ownedElfies, selectedId, currentMessages, profile: null, socketNotice: null, socketStatus: "offline", unread: new Map() }
}

function renderMessage(message: ChatMessage): HTMLElement {
  const row = element("article", `message${message.sender === "user" ? " message--user" : ""}`)
  row.append(avatar(message.sender === "user" ? "我" : "精"))
  const bubble = element("div", "bubble")
  bubble.textContent = message.text
  row.append(bubble)
  return row
}

function unreadLabel(state: ChatState, elfieId: string): string {
  const count = state.unread.get(elfieId) ?? 0
  return count > 0 ? ` · ${count} 条新消息` : ""
}

async function selectElfie(state: ChatState, elfieId: string, openProfile: boolean): Promise<void> {
  state.selectedId = elfieId
  state.currentMessages = await messages(elfieId)
  state.profile = openProfile ? await profile(elfieId) : null
  const unread = new Map(state.unread)
  unread.delete(elfieId)
  state.unread = unread
  await render(state)
}

async function refreshConversationRows(state: ChatState): Promise<void> {
  state.conversations = await conversations()
}

async function handleRealtimeEvent(state: ChatState, event: ChatSocketEvent): Promise<void> {
  if (event.event === "error") {
    state.socketNotice = event.detail
    await render(state)
    return
  }
  if (event.event !== "message") return
  if (event.message.elfie_id === state.selectedId) {
    if (!state.currentMessages.some((message) => message.id === event.message.id)) {
      state.currentMessages = [...state.currentMessages, event.message]
    }
  } else {
    const unread = new Map(state.unread)
    unread.set(event.message.elfie_id, (unread.get(event.message.elfie_id) ?? 0) + 1)
    state.unread = unread
  }
  await refreshConversationRows(state)
  await render(state)
}

function connectRealtime(state: ChatState): void {
  realtime?.close()
  realtime = new ChatSocket({
    onEvent: (event) => { void handleRealtimeEvent(state, event) },
    onStatus: (status) => { state.socketStatus = status; void render(state) }
  })
  realtime.connect()
}

async function render(state: ChatState): Promise<void> {
  const page = element("main", "page")
  const workspace = element("section", "panel workspace")
  const sidebar = element("aside", "sidebar")
  const header = element("div", "sidebar-header")
  header.append(Object.assign(element("strong"), { textContent: "ElfieNest" }), Object.assign(element("a", "button button--quiet"), { href: "/manage", textContent: state.user.role === "owner" ? "管理" : "设置" }))
  sidebar.append(header, Object.assign(element("p", "section-label"), { textContent: "聊天记录" }))
  const conversationList = element("div", "sidebar-list")
  state.conversations.forEach((conversation) => {
    const row = element("button", `list-row${conversation.elfie_id === state.selectedId ? " list-row--active" : ""}`)
    row.type = "button"
    row.append(avatar(conversation.name))
    const copy = element("span", "list-copy")
    copy.append(Object.assign(element("strong"), { textContent: conversation.name }), Object.assign(element("small"), { textContent: `${conversation.last_message_preview || "还没有消息"}${unreadLabel(state, conversation.elfie_id)}` }))
    row.append(copy)
    row.addEventListener("click", () => { void selectElfie(state, conversation.elfie_id, false) })
    conversationList.append(row)
  })
  sidebar.append(conversationList, Object.assign(element("p", "section-label"), { textContent: "我的精灵" }))
  const elfieList = element("div", "sidebar-list")
  state.elfies.forEach((elfie) => {
    const row = element("button", `list-row${elfie.elfie_id === state.selectedId ? " list-row--active" : ""}`)
    row.type = "button"
    row.append(avatar(elfie.name))
    const copy = element("span", "list-copy")
    copy.append(Object.assign(element("strong"), { textContent: elfie.name }), Object.assign(element("small"), { textContent: `${elfie.species_id} · ${elfie.embodiment.state}${unreadLabel(state, elfie.elfie_id)}` }))
    row.append(copy)
    row.addEventListener("click", () => { void selectElfie(state, elfie.elfie_id, true) })
    elfieList.append(row)
  })
  sidebar.append(elfieList)
  const settings = element("div", "sidebar-bottom")
  const channel = element("small", "connection-state")
  channel.textContent = state.socketStatus === "online" ? "实时通道已连接" : state.socketStatus === "connecting" ? "正在连接实时通道…" : "实时通道离线，发送将使用安全 HTTP 备用通道"
  const leave = element("button", "button button--quiet")
  leave.textContent = "退出登录"
  leave.addEventListener("click", async () => { await logout(state.csrfToken); window.location.assign("/login") })
  settings.append(channel, leave)
  sidebar.append(settings)

  const conversation = element("section", "conversation")
  const selected = state.elfies.find((entry) => entry.elfie_id === state.selectedId)
  const title = element("div", "topline")
  title.append(Object.assign(element("h1"), { textContent: selected?.name ?? "选择一只精灵" }))
  const detailButton = element("button", "button button--quiet")
  detailButton.textContent = "资料"
  detailButton.disabled = selected === undefined
  detailButton.addEventListener("click", async () => {
    if (state.selectedId !== null) {
      state.profile = await profile(state.selectedId)
      await render(state)
    }
  })
  title.append(detailButton)
  conversation.append(title)
  const history = element("section", "message-list")
  if (state.selectedId === null) history.append(Object.assign(element("p", "empty"), { textContent: "先选择一只属于你的精灵。" }))
  else state.currentMessages.forEach((message) => history.append(renderMessage(message)))
  if (state.socketNotice !== null) history.append(notice(state.socketNotice, "error"))
  conversation.append(history)
  const composer = element("form", "composer")
  const input = element("textarea")
  input.placeholder = selected === undefined ? "请选择精灵" : `对 ${selected.name} 说点什么…`
  input.disabled = selected === undefined
  const send = element("button", "button")
  send.textContent = "发送"
  send.disabled = selected === undefined || !state.csrfToken
  composer.append(input, send)
  composer.addEventListener("submit", async (event) => {
    event.preventDefault()
    if (state.selectedId === null || !input.value.trim()) return
    const text = input.value.trim()
    input.value = ""
    send.disabled = true
    try {
      if (!realtime?.send(state.selectedId, text)) {
        const message = await sendMessage(state.selectedId, text, state.csrfToken)
        state.currentMessages = [...state.currentMessages, message]
        await refreshConversationRows(state)
        await render(state)
      }
    } catch (error: unknown) {
      state.socketNotice = error instanceof ApiError ? error.message : "消息没有送达"
      await render(state)
    } finally {
      send.disabled = false
    }
  })
  conversation.append(composer)
  const detail = element("aside", "detail")
  if (state.profile === null) detail.append(Object.assign(element("p", "empty"), { textContent: "打开资料，查看外貌、人格和具身状态。" }))
  else renderProfile(detail, state.profile)
  workspace.append(sidebar, conversation, detail)
  page.append(workspace)
  clearAndMount(page)
}

function renderProfile(target: HTMLElement, data: ElfieProfile): void {
  target.append(avatar(data.name), Object.assign(element("h2"), { textContent: data.name }), Object.assign(element("p"), { textContent: `${data.species_id} · ${data.embodiment.state}` }))
  const tags = element("div")
  data.personality_tags.forEach((tag) => tags.append(Object.assign(element("span", "tag"), { textContent: tag })))
  target.append(tags)
  const facts = element("dl")
  Object.entries(data.big_five).forEach(([name, value]) => { facts.append(Object.assign(element("dt"), { textContent: name }), Object.assign(element("dd"), { textContent: value.toFixed(2) })) })
  facts.append(Object.assign(element("dt"), { textContent: "巢内位置" }), Object.assign(element("dd"), { textContent: data.nest.room_name ?? "未分配" }))
  facts.append(Object.assign(element("dt"), { textContent: "外貌摘要" }), Object.assign(element("dd"), { textContent: Object.values(data.appearance).filter((value): value is string => typeof value === "string").join(" · ") || "待完善" }))
  target.append(facts)
  const preview = element("a", "button button--quiet")
  preview.href = "/runtime/godot"
  preview.textContent = "打开 3D 巢内预览"
  target.append(preview)
}

void loadState().then((state) => { void render(state); connectRealtime(state) }).catch(() => window.location.assign("/login?next=/chat"))
window.addEventListener("beforeunload", () => realtime?.close())
