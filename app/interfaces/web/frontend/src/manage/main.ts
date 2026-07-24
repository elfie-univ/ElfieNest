import {
  ApiError,
  type NestRoom,
  type OwnerElfie,
  type OwnerUser,
  createManagedUser,
  currentUser,
  logout,
  ownerElfies,
  ownerRooms,
  ownerUsers,
  saveLandingPage
} from "../shared/api"
import { clearAndMount, element, notice } from "../shared/ui"

type ManageState = {
  readonly csrfToken: string
  readonly elfies: readonly OwnerElfie[]
  readonly rooms: readonly NestRoom[]
  readonly user: Awaited<ReturnType<typeof currentUser>>
  users: readonly OwnerUser[]
}

async function loadState(): Promise<ManageState> {
  const user = await currentUser()
  if (user.role !== "owner") {
    window.location.assign("/chat")
    throw new ApiError(403, "普通用户不能进入管理页")
  }
  const [users, elfies, rooms] = await Promise.all([ownerUsers(), ownerElfies(), ownerRooms()])
  return { user, csrfToken: user.csrf_token ?? "", users, elfies, rooms }
}

function card(title: string, description: string): HTMLElement {
  const node = element("article", "manage-card")
  node.append(Object.assign(element("h2"), { textContent: title }), Object.assign(element("p"), { textContent: description }))
  return node
}

function landingCard(state: ManageState): HTMLElement {
  const node = card("默认打开页面", "Owner 可选择下一次登录的落点。")
  const actions = element("div", "manage-actions")
  const select = element("select")
  for (const [value, label] of [["manage", "管理页"], ["chat", "聊天页"]] as const) {
    const option = element("option")
    option.value = value
    option.textContent = label
    select.append(option)
  }
  select.value = state.user.default_landing_page === "chat" ? "chat" : "manage"
  const save = element("button", "button")
  save.textContent = "保存偏好"
  const status = element("div")
  save.addEventListener("click", async () => {
    try {
      await saveLandingPage(select.value === "chat" ? "chat" : "manage", state.csrfToken)
      status.replaceChildren(notice("默认页已保存。"))
    } catch (error: unknown) {
      status.replaceChildren(notice(error instanceof ApiError ? error.message : "设置未保存", "error"))
    }
  })
  actions.append(select, save)
  node.append(actions, status)
  return node
}

function elfieCard(elfies: readonly OwnerElfie[]): HTMLElement {
  const node = card("精灵总览", `当前共 ${elfies.length} 位精灵。`)
  const list = element("ul", "manage-list")
  if (elfies.length === 0) list.append(Object.assign(element("li"), { textContent: "还没有已接入精灵。" }))
  elfies.forEach((elfie) => {
    const location = elfie.room_name ? `${elfie.room_name} · ${elfie.bed_name ?? "未分床位"}` : "尚未分配精灵巢"
    list.append(Object.assign(element("li"), { textContent: `${elfie.name} · ${elfie.species_id} · ${elfie.owner_username ?? "未分配用户"} · ${location}` }))
  })
  node.append(list)
  return node
}

function nestCard(rooms: readonly NestRoom[]): HTMLElement {
  const node = card("精灵巢", `当前 ${rooms.length} 个房间。`)
  const list = element("ul", "manage-list")
  rooms.forEach((room) => {
    const occupied = room.beds.filter((bed) => bed.occupant_name !== null).length
    list.append(Object.assign(element("li"), { textContent: `${room.name} · ${occupied}/${room.beds.length} 个床位已使用` }))
  })
  node.append(list)
  return node
}

function usersCard(state: ManageState): HTMLElement {
  const node = card("用户管理", "创建普通用户；每个用户登录后直接进入聊天页。")
  const list = element("ul", "manage-list")
  const renderUsers = (): void => {
    list.replaceChildren(...state.users.map((user) => Object.assign(element("li"), { textContent: `${user.username} · ${user.elfie_count} 位精灵` })))
  }
  renderUsers()
  const form = element("form", "manage-form")
  const username = element("input")
  username.placeholder = "新用户名"
  username.required = true
  const password = element("input")
  password.type = "password"
  password.placeholder = "初始密码"
  password.required = true
  const submit = element("button", "button")
  submit.textContent = "创建用户"
  const status = element("div")
  form.append(username, password, submit)
  form.addEventListener("submit", async (event) => {
    event.preventDefault()
    submit.disabled = true
    try {
      const created = await createManagedUser(username.value.trim(), password.value, state.csrfToken)
      state.users = [...state.users, { ...created, elfie_count: 0 }]
      username.value = ""
      password.value = ""
      renderUsers()
      status.replaceChildren(notice("普通用户已创建。"))
    } catch (error: unknown) {
      status.replaceChildren(notice(error instanceof ApiError ? error.message : "用户未创建", "error"))
    } finally {
      submit.disabled = false
    }
  })
  node.append(list, form, status)
  return node
}

function sessionCard(state: ManageState): HTMLElement {
  const node = card("会话与入口", "聊天页与管理页共享同一会话。供应商、模型、工具、粮食与系统设置暂由兼容管理工作区承载，二期再完成其页面迁移。")
  const actions = element("div", "manage-actions")
  const toChat = element("a", "button")
  toChat.href = "/chat"
  toChat.textContent = "进入聊天"
  const classic = element("a", "button button--quiet")
  classic.href = "/manage?mode=classic"
  classic.textContent = "高级运行配置"
  const leave = element("button", "button button--quiet")
  leave.textContent = "退出登录"
  leave.addEventListener("click", async () => {
    await logout(state.csrfToken)
    window.location.assign("/login")
  })
  actions.append(toChat, classic, leave)
  node.append(actions)
  return node
}

function render(state: ManageState): void {
  const page = element("main", "page")
  const shell = element("section", "panel manage")
  const header = element("header", "manage-head")
  const identity = element("div")
  identity.append(Object.assign(element("p", "brand"), { textContent: "OWNER CONSOLE" }), Object.assign(element("h1"), { textContent: `你好，${state.user.username}` }))
  header.append(identity)
  const grid = element("section", "manage-grid")
  grid.append(landingCard(state), elfieCard(state.elfies), nestCard(state.rooms), usersCard(state), sessionCard(state))
  shell.append(header, grid)
  page.append(shell)
  clearAndMount(page)
}

void loadState().then(render).catch(() => window.location.assign("/login?next=/manage"))
