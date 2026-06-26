let currentUser = null;
let csrfToken = "";
let role = "admin";
let activeView = "overview";
let previousView = "overview";
let wizardStep = 0;
let elves = [];
let rooms = [];
let providers = [];
let models = [];
let systemConfig = {};
let globalQuery = "";
let ws = null;
let wsState = "offline";
let wsReconnectTimer = null;
const chatHistory = new Map();
const MAX_CHAT_ITEMS = 80;

const USER_VIEWS = new Set(["elves", "rooms", "elf-detail"]);
const shell = document.querySelector(".app-shell");
const pageTitle = document.querySelector("#page-title");
const profileRole = document.querySelector("#profile-role");
const elvesCopy = document.querySelector("#elves-copy");
const roomsCopy = document.querySelector("#rooms-copy");
const elfGrid = document.querySelector("#elf-grid");
const scopeFilter = document.querySelector("#scope-filter");
const ownerFilter = document.querySelector("#owner-filter");
const backdrop = document.querySelector(".drawer-backdrop");
const adoptionDrawer = document.querySelector("#adoption-drawer");
const profileDrawer = document.querySelector("#profile-drawer");
const profileMenu = document.querySelector("#profile-menu");
const detailContent = document.querySelector("#elf-detail-content");
const detailHeading = document.querySelector("#elf-detail-heading");

function byId(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function setText(id, value) {
  const node = byId(id);
  if (node) node.textContent = value;
}

function nowLabel() {
  return new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function addChatItem(elfieId, item) {
  if (!elfieId) return;
  const items = chatHistory.get(elfieId) || [];
  items.push({ time: nowLabel(), ...item });
  if (items.length > MAX_CHAT_ITEMS) items.splice(0, items.length - MAX_CHAT_ITEMS);
  chatHistory.set(elfieId, items);
  if (activeView === "elf-detail" && byId("elf-chat-history")?.dataset.elfieId === elfieId) {
    renderChatHistory(elfieId);
  }
  renderLogs();
}

function wsStatusLabel() {
  if (wsState === "online") return "WebSocket 已连接";
  if (wsState === "connecting") return "WebSocket 连接中";
  if (wsState === "error") return "WebSocket 连接异常";
  return "WebSocket 未连接";
}

function updateWsIndicators() {
  setText("ws-status-label", wsStatusLabel());
  setText("room-sync-status", wsState === "online" ? "WebSocket 在线" : "WebSocket 待连接");
  const sendButton = byId("chat-send-button");
  if (sendButton) sendButton.disabled = wsState !== "online";
}

function statusClass(status) {
  if (["online", "active", "ok", "success", true].includes(status)) return "success";
  if (["inactive", "missing", "warning", false].includes(status)) return "warning";
  if (["error", "failed"].includes(status)) return "error";
  return "info";
}

function wsUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.hostname}:8766`;
}

function connectRealtime() {
  if (!currentUser?.session_token || wsState === "connecting" || wsState === "online") return;
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = null;
  }
  wsState = "connecting";
  updateWsIndicators();
  ws = new WebSocket(wsUrl());

  ws.addEventListener("open", () => {
    ws.send(JSON.stringify({
      event: "auth",
      payload: { token: currentUser.session_token },
    }));
  });

  ws.addEventListener("message", (event) => {
    handleRealtimeMessage(event.data);
  });

  ws.addEventListener("close", () => {
    wsState = currentUser ? "offline" : "closed";
    updateWsIndicators();
    if (currentUser) {
      wsReconnectTimer = setTimeout(connectRealtime, 3000);
    }
  });

  ws.addEventListener("error", () => {
    wsState = "error";
    updateWsIndicators();
  });
}

function disconnectRealtime(reconnect = false) {
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = null;
  }
  if (ws) {
    ws.close(1000, "logout");
    ws = null;
  }
  wsState = "offline";
  updateWsIndicators();
  if (reconnect) {
    connectRealtime();
  }
}

function handleRealtimeMessage(raw) {
  let message;
  try {
    message = JSON.parse(raw);
  } catch {
    return;
  }
  const event = message.event || message.action;
  const payload = message.payload || {};
  if (event === "auth_ok") {
    wsState = "online";
    updateWsIndicators();
    return;
  }
  if (event === "speak_event") {
    const elfieId = payload.elfie_id || "";
    addChatItem(elfieId, {
      sender: "elfie",
      text: payload.text || "精灵发出了一条空消息。",
      meta: payload.emotion ? `情绪：${payload.emotion}` : "实时回复",
    });
    return;
  }
  if (event) {
    addSystemNotice(`收到实时事件：${event}`);
  }
}

function sendUserMessage(elfieId, message) {
  if (!ws || wsState !== "online") {
    throw new Error("WebSocket 未连接");
  }
  ws.send(JSON.stringify({
    event: "user_message",
    payload: { elfie_id: elfieId, message },
  }));
}

function addSystemNotice(text) {
  const list = byId("alerts-list");
  if (!list) return;
  const node = document.createElement("article");
  node.innerHTML = `<strong>${escapeHtml(nowLabel())}</strong><span>${escapeHtml(text)}</span>`;
  list.prepend(node);
}

function matchesQuery(values) {
  if (!globalQuery) return true;
  const haystack = values.map((value) => String(value ?? "").toLowerCase()).join(" ");
  return haystack.includes(globalQuery);
}

function applySearchShortcut() {
  if (!globalQuery) return;
  const viewMatches = [
    ["elves", ["精灵", "elf", "elfie"]],
    ["rooms", ["房间", "床位", "精灵巢", "room", "nest"]],
    ["users", ["用户", "user"]],
    ["providers", ["供应商", "provider", "api"]],
    ["models", ["模型", "model"]],
    ["food", ["粮食", "路由", "food", "route"]],
    ["config", ["配置", "系统", "config"]],
    ["logs", ["日志", "提醒", "log", "alert"]],
  ];
  const match = viewMatches.find(([, words]) => words.some((word) => word.includes(globalQuery) || globalQuery.includes(word)));
  if (match) setView(match[0]);
}

function setFormMessage(id, text, kind = "info") {
  const node = byId(id);
  if (!node) return;
  node.textContent = text;
  node.style.color = kind === "error" ? "var(--status-error)" : kind === "success" ? "var(--status-success)" : "var(--text-secondary)";
}

function fillProfileForm() {
  const nameInput = byId("profile-edit-name");
  const colorSelect = byId("profile-edit-color");
  if (nameInput) nameInput.value = currentUser?.nickname || currentUser?.username || "";
  if (colorSelect) colorSelect.value = String(currentUser?.avatar_color ?? 0);
  setFormMessage("profile-message", "");
  setFormMessage("password-message", "");
  const oldPassword = byId("profile-old-password");
  const newPassword = byId("profile-new-password");
  if (oldPassword) oldPassword.value = "";
  if (newPassword) newPassword.value = "";
}

function updateProfileHeader(user) {
  currentUser = { ...(currentUser || {}), ...user };
  setText("profile-name", currentUser.nickname || currentUser.username);
  setText("profile-avatar", (currentUser.nickname || currentUser.username || "U").charAt(0).toUpperCase());
}

function systemPayload(section, form) {
  const data = new FormData(form);
  if (section === "adoption") {
    return {
      max_elfies_per_user: Number(data.get("max_elfies_per_user") || 3),
      default_personality_style: String(data.get("default_personality_style") || "活泼好动").trim(),
      allowed_personality_styles: String(data.get("allowed_personality_styles") || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    };
  }
  if (section === "engine") {
    const maxRoom = String(data.get("max_elfies_per_room") || "").trim();
    return {
      tick_interval_sec: Number(data.get("tick_interval_sec") || 1.5),
      tts_enabled: data.get("tts_enabled") === "on",
      max_elfies_per_room: maxRoom ? Number(maxRoom) : null,
    };
  }
  return {
    session_ttl_days: Number(data.get("session_ttl_days") || 7),
    max_login_attempts: Number(data.get("max_login_attempts") || 5),
    rate_limit_window_seconds: Number(data.get("rate_limit_window_seconds") || 300),
  };
}

function apiHeaders(method = "GET") {
  const headers = {};
  if (!["GET", "HEAD"].includes(method.toUpperCase())) {
    headers["X-CSRF-Token"] = csrfToken;
  }
  return headers;
}

async function fetchJson(url, options = {}) {
  const method = options.method || "GET";
  const response = await fetch(url, {
    credentials: "include",
    ...options,
    headers: {
      ...apiHeaders(method),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

async function checkAuth() {
  try {
    const data = await fetchJson("/api/auth/me");
    currentUser = data;
    csrfToken = data.csrf_token || "";
    setRole(data.role || "user");
    setText("profile-name", data.nickname || data.username);
    setText("profile-role", data.role === "admin" ? "管理员" : "普通用户");
    setText("profile-avatar", (data.nickname || data.username || "U").charAt(0).toUpperCase());

    const loginView = byId("login-view");
    if (loginView) loginView.style.display = "none";
    connectRealtime();
    await loadDashboardData();
  } catch {
    disconnectRealtime();
    const loginView = byId("login-view");
    if (loginView) loginView.style.display = "flex";
  }
}

const loginForm = byId("login-form");
if (loginForm) {
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorNode = byId("login-error");
    if (errorNode) errorNode.style.display = "none";

    const form = new FormData();
    form.append("username", byId("username")?.value || "");
    form.append("password", byId("password")?.value || "");

    try {
      const response = await fetch("/api/auth/login", { method: "POST", body: form });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "登录失败");
      }
      await checkAuth();
    } catch (error) {
      if (errorNode) {
        errorNode.textContent = error.message || "网络连接失败";
        errorNode.style.display = "block";
      }
    }
  });
}

const logoutButton = byId("logout-btn");
if (logoutButton) {
  logoutButton.addEventListener("click", async () => {
    try {
      await fetchJson("/api/auth/logout", { method: "POST" });
    } catch {
    } finally {
      disconnectRealtime();
      currentUser = null;
      const loginView = byId("login-view");
      if (loginView) loginView.style.display = "flex";
      closeMenus();
    }
  });
}

async function loadDashboardData() {
  await loadElves();
  await loadRooms();
  if (role === "admin") {
    await Promise.all([
      loadProviders(),
      loadModels(),
      loadSystemConfig(),
      loadUsers(),
    ]);
  }
  renderOverview();
  renderLogs();
}

function normalizeElfie(raw) {
  const id = raw.elfie_id || raw.id || "";
  const name = raw.name || id || "未命名精灵";
  const bedId = raw.bed_id || raw.bedId || null;
  return {
    id,
    name,
    owner: raw.owner_username || raw.owner || currentUser?.username || "我",
    owned: !raw.owner_user_id || raw.owner_user_id === currentUser?.id || raw.owner === currentUser?.username,
    status: raw.status || "online",
    statusLabel: raw.status_label || "在线",
    model: raw.model || raw.default_model || "按粮食策略",
    role: raw.prompt || raw.personality_style || "基础陪伴精灵",
    anatomy: raw.anatomy_type || "biped",
    height: raw.height || "standard",
    build: raw.build || "standard",
    energy: raw.energy ?? 100,
    mood: raw.mood || "平静",
    room: raw.room_name || (raw.room_id ? `房间 ${raw.room_id}` : "主精灵巢"),
    bed: bedId ? (raw.bed_name || `床位 ${bedId}`) : "未分配床位",
    createdAt: raw.created_at || "",
    raw,
  };
}

async function loadElves() {
  try {
    const data = await fetchJson(role === "admin" ? "/api/admin/elfies" : "/api/user/elfies");
    elves = (Array.isArray(data) ? data : []).map(normalizeElfie);
  } catch (error) {
    console.error("Failed to load elfies", error);
    elves = [];
  }
  renderElves();
  setText("metric-active", String(elves.length));
  setText("metric-overview-active", String(elves.length));
  setText("metric-overview-total", `总计 ${elves.length} 只`);
  const unassigned = elves.filter((elf) => !elf.raw.bed_id).length;
  setText("metric-unassigned", String(unassigned));
}

async function loadRooms() {
  try {
    const endpoint = role === "admin" ? "/api/admin/nest/rooms" : "/api/user/nest/rooms";
    rooms = await fetchJson(endpoint);
  } catch (error) {
    console.error("Failed to load rooms", error);
    rooms = [];
  }
  renderRooms();
}

async function loadProviders() {
  try {
    providers = await fetchJson("/api/admin/providers/");
  } catch (error) {
    console.error("Failed to load providers", error);
    providers = [];
  }
  renderProviders();
  renderOverview();
}

async function loadModels() {
  try {
    models = await fetchJson("/api/admin/models/");
  } catch (error) {
    console.error("Failed to load models", error);
    models = [];
  }
  renderModelFilters();
  renderModels();
  renderFoodStrategy();
}

async function loadSystemConfig() {
  const sections = ["llm", "engine", "adoption", "security"];
  const loaded = {};
  await Promise.all(sections.map(async (section) => {
    try {
      loaded[section] = await fetchJson(`/api/admin/system/${section}`);
    } catch (error) {
      console.error(`Failed to load system ${section}`, error);
      loaded[section] = {};
    }
  }));
  systemConfig = loaded;
  renderSystemConfig();
  renderFoodStrategy();
  renderOverview();
}

async function loadUsers() {
  const body = byId("users-table-body");
  if (!body || role !== "admin") return;
  try {
    const users = await fetchJson("/api/admin/users");
    const rows = [
      {
        id: currentUser.id,
        username: currentUser.username,
        role: currentUser.role,
        created_at: currentUser.created_at,
        elfie_count: elves.length,
        current: true,
      },
      ...(Array.isArray(users) ? users : []),
    ].filter((user) => matchesQuery([user.username, user.role, user.id]));
    body.innerHTML = rows.map((user) => `
      <div class="table-row user-row">
        <span><strong>${escapeHtml(user.username)}</strong><small>${user.current ? "当前登录" : `ID ${user.id}`}</small></span>
        <span><mark class="status ${user.role === "admin" ? "info" : "success"}">${user.role === "admin" ? "管理员" : "普通用户"}</mark></span>
        <span><mark class="status success">正常</mark></span>
        <span>${formatDate(user.created_at) || "未知"}</span>
        <span>${user.elfie_count ?? 0} 只精灵</span>
      </div>
    `).join("");
  } catch (error) {
    body.innerHTML = emptyPanel("用户列表读取失败", error.message);
  }
}

function formatDate(value) {
  if (!value) return "";
  return String(value).slice(0, 10);
}

function labelForAnatomy(value) {
  const map = { biped: "双足", quadruped: "四足" };
  return map[value] || value || "未知";
}

function labelForAppearance(height, build) {
  const heights = { short: "矮小", standard: "标准", tall: "高大" };
  const builds = { slim: "纤细", standard: "标准", plump: "圆润" };
  return `${heights[height] || height || "标准"} · ${builds[build] || build || "标准"}`;
}

function emptyPanel(title, detail = "") {
  return `
    <article class="drawer-section empty-panel">
      <h3>${escapeHtml(title)}</h3>
      ${detail ? `<p>${escapeHtml(detail)}</p>` : ""}
    </article>
  `;
}

function setRole(nextRole) {
  role = nextRole;
  if (shell) shell.dataset.role = role;
  if (profileRole) profileRole.textContent = role === "admin" ? "管理员" : "普通用户";
  if (elvesCopy) {
    elvesCopy.textContent = role === "admin"
      ? "管理员可查看本机精灵概览；私密聊天和配置仍只归拥有者管理。"
      : "这里只显示你的精灵，可领养、聊天，并管理自己的精灵配置。";
  }
  if (roomsCopy) {
    roomsCopy.textContent = role === "admin"
      ? "管理员管理房间布局、床位分配、家具配置和 Godot 视角。"
      : "普通用户可查看精灵巢布局、摄像头和公开状态，不能修改布局或床位。";
  }
  document.querySelectorAll(".admin-action").forEach((node) => {
    node.hidden = role !== "admin";
  });
  setView(role === "admin" ? "overview" : "elves");
}

function setView(view) {
  const nextView = role === "user" && !USER_VIEWS.has(view) ? "elves" : view;
  previousView = activeView === "elf-detail" ? previousView : activeView;
  activeView = nextView;
  const titles = {
    overview: "综合监控",
    elves: "精灵管理",
    "elf-detail": "精灵详情",
    rooms: "精灵巢管理",
    users: "用户管理",
    providers: "供应商管理",
    models: "模型管理",
    food: "粮食策略",
    logs: "运行日志",
    config: "系统配置",
  };
  if (pageTitle) pageTitle.textContent = titles[nextView] || "";

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === nextView);
  });
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.viewPanel === nextView);
  });

  if (nextView === "rooms") loadRooms();
  if (nextView === "providers") loadProviders();
  if (nextView === "models") loadModels();
  if (nextView === "food") {
    if (!models.length) loadModels();
    if (!systemConfig.llm) loadSystemConfig();
    renderFoodStrategy();
  }
  if (nextView === "logs") renderLogs();
  if (nextView === "config") loadSystemConfig();
  if (nextView === "users") loadUsers();
}

function openDrawer(drawer) {
  if (!drawer) return;
  closeMenus();
  closeDrawers();
  if (backdrop) backdrop.hidden = false;
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
}

function closeDrawers() {
  if (backdrop) backdrop.hidden = true;
  document.querySelectorAll(".drawer").forEach((drawer) => {
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
  });
}

function togglePopover(popover, anchor) {
  if (!popover || !anchor) return;
  const wasHidden = popover.hidden;
  closeMenus();
  if (!wasHidden) return;
  const rect = anchor.getBoundingClientRect();
  popover.hidden = false;
  popover.style.top = `${rect.bottom + 8}px`;
  popover.style.right = `${window.innerWidth - rect.right}px`;
}

function closeMenus() {
  if (profileMenu) profileMenu.hidden = true;
}

function renderElves() {
  if (!elfGrid) return;
  let list = elves;
  if (role === "user" || scopeFilter?.value === "mine") {
    list = elves.filter((elf) => elf.owned);
  }
  if (scopeFilter?.value === "others") {
    list = elves.filter((elf) => !elf.owned);
  }
  list = list.filter((elf) => matchesQuery([
    elf.name,
    elf.owner,
    elf.role,
    elf.anatomy,
    elf.room,
    elf.bed,
    elf.mood,
  ]));

  if (!list.length) {
    elfGrid.innerHTML = emptyPanel("没有匹配的精灵", "普通用户只会看到自己领养的精灵。");
    return;
  }

  elfGrid.innerHTML = list.map((elf) => {
    const ownerTag = elf.owned
      ? `<span class="tag own">我的精灵</span>`
      : `<span class="tag admin">${escapeHtml(elf.owner)}</span>`;
    return `
      <article class="elf-card ${elf.owned ? "own" : "other"}">
        <div class="elf-top">
          <div class="elf-avatar" aria-hidden="true"></div>
          <mark class="status ${statusClass(elf.status)}">${escapeHtml(elf.statusLabel)}</mark>
        </div>
        <div>
          <h3>${escapeHtml(elf.name)}</h3>
          <p class="line-clamp" title="${escapeHtml(elf.role)}">${escapeHtml(elf.role)}</p>
        </div>
        <div class="tag-row">
          ${ownerTag}
          <span class="tag">${escapeHtml(labelForAnatomy(elf.anatomy))}</span>
          <span class="tag">${escapeHtml(labelForAppearance(elf.height, elf.build))}</span>
        </div>
        <div class="metric-mini-row">
          <div class="metric-mini"><span>能量</span><strong>${escapeHtml(elf.energy)}%</strong></div>
          <div class="metric-mini"><span>情绪</span><strong>${escapeHtml(elf.mood)}</strong></div>
        </div>
        <div class="elf-actions">
          <span class="privacy-note">${escapeHtml(elf.room)} · ${escapeHtml(elf.bed)}</span>
          <button class="ghost-button" type="button" data-open-elf="${escapeHtml(elf.id)}">进入详情</button>
        </div>
      </article>
    `;
  }).join("");
}

function renderRooms() {
  const mapRender = byId("room-map-render");
  if (!mapRender) return;
  mapRender.innerHTML = "";
  const room = rooms[0];
  if (!room) {
    mapRender.innerHTML = `
      <div class="room-readonly-state">
        <strong>暂无房间数据</strong>
        <span>初始化数据库后会默认生成 Main Nest 和床位。</span>
      </div>
    `;
    renderRoomSide();
    return;
  }

  setText("room-map-title", `${room.name || "主房间"} · 俯视布局`);
  const beds = room.beds || [];
  const numericXs = beds
    .map((bed) => Number(bed.grid_x))
    .filter((value) => Number.isFinite(value));
  const numericYs = beds
    .map((bed) => Number(bed.grid_y))
    .filter((value) => Number.isFinite(value));
  const minX = numericXs.length ? Math.min(...numericXs) : 0;
  const maxX = numericXs.length ? Math.max(...numericXs) : 0;
  const minY = numericYs.length ? Math.min(...numericYs) : 0;
  const maxY = numericYs.length ? Math.max(...numericYs) : 0;
  beds.forEach((bed, index) => {
    const node = document.createElement("button");
    node.type = "button";
    const occupied = Boolean(bed.occupant_id);
    const ownerLabel = bed.occupant_is_mine ? "我的" : bed.occupant_owner_username || "未知主人";
    const occupantLabel = occupied
      ? `${bed.occupant_name || "未命名精灵"} · ${ownerLabel}`
      : "空闲";
    node.className = `room-object bed ${occupied ? "" : "empty"}`;
    const rawX = Number(bed.grid_x);
    const rawY = Number(bed.grid_y);
    const hasX = Number.isFinite(rawX);
    const hasY = Number.isFinite(rawY);
    const x = hasX && maxX > minX ? 16 + ((rawX - minX) / (maxX - minX)) * 68 : 18 + (index % 2) * 58;
    const y = hasY && maxY > minY ? 16 + ((rawY - minY) / (maxY - minY)) * 68 : 16 + Math.floor(index / 2) * 26;
    node.style.left = `${Math.min(84, Math.max(12, x))}%`;
    node.style.top = `${Math.min(84, Math.max(12, y))}%`;
    node.innerHTML = `<strong>${escapeHtml(bed.name || `床位 ${bed.id}`)}</strong><span>${escapeHtml(occupantLabel)}</span>`;
    if (role === "user") {
      node.disabled = true;
      node.title = "普通用户只能查看床位";
    } else {
      node.dataset.editBed = String(bed.id);
      node.dataset.gridX = String(bed.grid_x ?? 0);
      node.dataset.gridY = String(bed.grid_y ?? 0);
      node.title = "点击编辑床位坐标";
    }
    mapRender.appendChild(node);
  });

  const desk = document.createElement("div");
  desk.className = "room-object desk desk-a";
  desk.innerHTML = "<strong>公共桌</strong><span>互动点</span>";
  mapRender.appendChild(desk);
  const camera = document.createElement("div");
  camera.className = "room-object hotspot window";
  camera.innerHTML = "<strong>Godot Camera</strong><span>可查看</span>";
  mapRender.appendChild(camera);
  renderRoomSide();
}

function renderRoomSide() {
  const unassignedList = byId("unassigned-elfies-list");
  if (!unassignedList) return;
  if (role === "user") {
    setText("bed-panel-title", "公开状态");
    unassignedList.innerHTML = `
      <div><span>权限</span><strong>只读查看</strong></div>
      <div><span>可查看</span><strong>布局、摄像头、公开床位</strong></div>
      <div><span>不可修改</span><strong>布局、床位、其他用户配置</strong></div>
    `;
    return;
  }
  setText("bed-panel-title", "床位分配");
  const unassigned = elves.filter((elf) => !elf.raw.bed_id);
  const room = rooms[0];
  const emptyBeds = (room?.beds || []).filter((bed) => !bed.occupant_id);
  unassignedList.innerHTML = unassigned.length
    ? unassigned.map((elf) => `
      <div>
        <span>未分配</span>
        <strong>${escapeHtml(elf.name)}</strong>
        <select data-assign-bed="${escapeHtml(elf.id)}">
          <option value="">选择床位</option>
          ${emptyBeds.map((bed) => `<option value="${escapeHtml(bed.id)}">${escapeHtml(bed.name || `床位 ${bed.id}`)}</option>`).join("")}
        </select>
      </div>
    `).join("")
    : "<div><span>床位</span><strong>没有未分配的精灵</strong></div>";
}

function renderProviders() {
  const grid = byId("provider-management-grid");
  if (!grid) return;
  const activeCount = providers.filter((provider) => provider.status === "active").length;
  const missingCount = providers.length - activeCount;
  setText("metric-provider-active", String(activeCount));
  setText("metric-provider-missing", String(Math.max(0, missingCount)));

  const visibleProviders = providers.filter((provider) => matchesQuery([
    provider.name,
    provider.provider_id,
    provider.api_mode,
    provider.api_base,
    provider.status,
  ]));
  if (!visibleProviders.length) {
    grid.innerHTML = emptyPanel("暂无供应商数据", "检查 /api/admin/providers/ 是否可用。");
    return;
  }

  grid.innerHTML = visibleProviders.map((provider) => `
    <article class="provider-card ${provider.status === "active" ? "active" : "muted"}">
      <div class="card-inline-head">
        <strong>${escapeHtml(provider.name || provider.provider_id)}</strong>
        <mark class="status ${statusClass(provider.status)}">${provider.status === "active" ? "可用" : "未配置"}</mark>
      </div>
      <span>${escapeHtml(provider.provider_id)} · ${escapeHtml(provider.api_mode || "chat")}</span>
      <span class="mono">${escapeHtml(provider.api_base || "未设置 API Base")}</span>
      <span>${provider.has_api_key || provider.provider_id === "ollama" ? "密钥状态正常" : "缺少 API Key"}</span>
    </article>
  `).join("");
}

function renderModelFilters() {
  const select = byId("model-provider-filter");
  if (!select) return;
  const providerIds = [...new Set(models.map((model) => model.provider).filter(Boolean))].sort();
  const current = select.value || "all";
  select.innerHTML = `<option value="all">全部供应商</option>${providerIds.map((id) => `<option value="${escapeHtml(id)}">${escapeHtml(id)}</option>`).join("")}`;
  select.value = providerIds.includes(current) ? current : "all";
}

function renderModels() {
  const table = byId("models-table");
  if (!table) return;
  const providerFilter = byId("model-provider-filter")?.value || "all";
  const statusFilter = byId("model-status-filter")?.value || "all";
  let list = models;
  if (providerFilter !== "all") {
    list = list.filter((model) => model.provider === providerFilter);
  }
  if (statusFilter === "active") {
    list = list.filter((model) => model.active);
  } else if (statusFilter === "visible") {
    list = list.filter((model) => model.visible);
  } else if (statusFilter === "hidden") {
    list = list.filter((model) => !model.visible);
  }
  list = list.filter((model) => matchesQuery([
    model.display_name,
    model.model_id,
    model.provider,
    (model.capabilities || []).join(" "),
    model.context_window,
  ]));

  if (!list.length) {
    table.innerHTML = emptyPanel("没有匹配的模型", "换一个供应商或状态筛选。");
    return;
  }

  table.innerHTML = `
    <div class="table-row model-row table-head">
      <span>模型</span>
      <span>供应商</span>
      <span>能力</span>
      <span>上下文</span>
      <span>成本</span>
      <span>状态</span>
    </div>
    ${list.map((model) => `
      <div class="table-row model-row">
        <span><strong>${escapeHtml(model.display_name || model.model_id)}</strong><small>${escapeHtml(model.model_id)}</small></span>
        <span>${escapeHtml(model.provider || "unknown")}</span>
        <span>${(model.capabilities || []).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join(" ") || "text"}</span>
        <span>${escapeHtml(model.context_window || "-")}</span>
        <span><mark class="status info">L${escapeHtml(model.cost_tier ?? 0)}</mark></span>
        <span><mark class="status ${model.active && model.visible ? "success" : "warning"}">${model.active && model.visible ? "可用" : model.visible ? "待配置" : "隐藏"}</mark></span>
      </div>
    `).join("")}
  `;
}

function renderFoodStrategy() {
  const strategyGrid = byId("food-strategy-grid");
  const routeGrid = byId("food-route-grid");
  if (!strategyGrid || !routeGrid) return;
  const llm = systemConfig.llm || {};
  const slots = [
    ["轻量粮食", llm.default_cheap_provider, llm.default_cheap_model, "日常短对话、低能耗思考"],
    ["深度粮食", llm.default_deep_provider, llm.default_deep_model, "复杂推理、规划和复盘"],
    ["多模态粮食", llm.default_multimodal_provider, llm.default_multimodal_model, "图像、场景和跨模态理解"],
    ["本地兜底", "ollama", llm.default_cheap_model || "qwen3.5:0.8b", "外部模型失效时说明故障并维持基础沟通"],
  ];
  strategyGrid.innerHTML = slots.map(([title, provider, model, desc]) => {
    const match = models.find((item) => item.provider === provider && (item.model_id === model || item.display_name === model));
    return `
      <article class="strategy-card">
        <div class="card-inline-head">
          <strong>${escapeHtml(title)}</strong>
          <mark class="status ${match?.active || provider === "ollama" ? "success" : "warning"}">${match?.active || provider === "ollama" ? "已配对" : "待确认"}</mark>
        </div>
        <span>${escapeHtml(provider || "未设置")} · ${escapeHtml(model || "未设置")}</span>
        <p>${escapeHtml(desc)}</p>
      </article>
    `;
  }).join("");

  const routeItems = [
    ["Temperature", llm.temperature ?? "默认"],
    ["Max tokens", llm.max_tokens ?? "默认"],
    ["低能耗阈值", llm.energy_threshold ?? "默认"],
    ["深度复杂度阈值", llm.complexity_threshold ?? "默认"],
  ];
  routeGrid.innerHTML = routeItems.map(([label, value]) => `
    <article class="provider-card">
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml(value)}</span>
    </article>
  `).join("");
}

function renderSystemConfig() {
  const engine = systemConfig.engine || {};
  const adoption = systemConfig.adoption || {};
  const security = systemConfig.security || {};
  const adoptionPanel = byId("config-adoption-panel");
  const enginePanel = byId("config-engine-panel");
  const securityPanel = byId("config-security-panel");
  if (adoptionPanel) {
    const styles = adoption.allowed_personality_styles || adoption.personality_styles || [];
    adoptionPanel.innerHTML = `
      <h3>领养策略</h3>
      <form class="config-grid system-config-form" data-system-section="adoption">
        <label class="form-row"><span>每用户上限</span><input name="max_elfies_per_user" type="number" min="1" max="99" value="${escapeHtml(adoption.max_elfies_per_user || 3)}" /></label>
        <label class="form-row"><span>默认性格</span><input name="default_personality_style" type="text" value="${escapeHtml(adoption.default_personality_style || "活泼好动")}" /></label>
        <label class="form-row"><span>可选性格（逗号分隔）</span><input name="allowed_personality_styles" type="text" value="${escapeHtml(styles.join(", "))}" /></label>
        <p class="form-message" data-system-message="adoption"></p>
        <button class="primary-button full" type="submit">保存领养策略</button>
      </form>
    `;
  }
  if (enginePanel) {
    enginePanel.innerHTML = `
      <h3>引擎设置</h3>
      <form class="config-grid system-config-form" data-system-section="engine">
        <label class="form-row"><span>Tick 间隔（秒）</span><input name="tick_interval_sec" type="number" min="0.2" max="60" step="0.1" value="${escapeHtml(engine.tick_interval_sec ?? 1.5)}" /></label>
        <label class="check-row"><input name="tts_enabled" type="checkbox" ${engine.tts_enabled === false ? "" : "checked"} /><span>TTS 语音开启</span></label>
        <label class="form-row"><span>房间容量</span><input name="max_elfies_per_room" type="number" min="1" max="99" value="${escapeHtml(engine.max_elfies_per_room || "")}" placeholder="不限" /></label>
        <p class="form-message" data-system-message="engine"></p>
        <button class="primary-button full" type="submit">保存引擎设置</button>
      </form>
    `;
  }
  if (securityPanel) {
    securityPanel.innerHTML = `
      <h3>安全设置</h3>
      <form class="config-grid system-config-form" data-system-section="security">
        <label class="form-row"><span>会话有效期（天）</span><input name="session_ttl_days" type="number" min="1" max="90" value="${escapeHtml(security.session_ttl_days || 7)}" /></label>
        <label class="form-row"><span>最大登录尝试</span><input name="max_login_attempts" type="number" min="1" max="30" value="${escapeHtml(security.max_login_attempts || 5)}" /></label>
        <label class="form-row"><span>限流窗口（秒）</span><input name="rate_limit_window_seconds" type="number" min="10" max="3600" value="${escapeHtml(security.rate_limit_window_seconds || 300)}" /></label>
        <p class="form-message" data-system-message="security"></p>
        <button class="primary-button full" type="submit">保存安全设置</button>
      </form>
    `;
  }
}

function renderOverview() {
  const providerHealth = byId("overview-models-list");
  if (providerHealth) {
    const topProviders = providers.length ? providers.slice(0, 5) : [{ name: "Ollama", status: "active" }];
    providerHealth.innerHTML = topProviders.map((provider) => `
      <div><span>${escapeHtml(provider.name || provider.provider_id)}</span><mark class="status ${statusClass(provider.status)}">${provider.status === "active" ? "在线" : "待配置"}</mark></div>
    `).join("");
  }
  renderLogs();
}

function buildLogItems() {
  const activeProviders = providers.filter((provider) => provider.status === "active").length;
  return [
    `精灵管理：当前用户可见 ${elves.length} 只精灵。`,
    `精灵巢：${role === "admin" ? `读取到 ${rooms.length} 个房间。` : "普通用户为只读权限。"}`,
    `模型供应商：${providers.length || 1} 个供应商，${activeProviders || 1} 个可用。`,
    `模型目录：${models.length} 个模型已纳入粮食策略候选。`,
    "完整进程日志可在本机运行 ./elfie.sh logs 查看。",
  ];
}

function renderLogs() {
  const items = buildLogItems();
  const overviewLog = byId("overview-log-list");
  const consoleNode = byId("runtime-log-console");
  const alertsList = byId("alerts-list");
  if (overviewLog) {
    overviewLog.innerHTML = items.slice(0, 3).map((item) => `<span>${escapeHtml(item)}</span>`).join("");
  }
  if (alertsList && !alertsList.children.length) {
    alertsList.innerHTML = items.slice(0, 4).map((item) => `
      <article>
        <strong>状态</strong>
        <span>${escapeHtml(item)}</span>
      </article>
    `).join("");
  }
  if (consoleNode) {
    consoleNode.innerHTML = items.map((item, index) => `
      <div class="log-line">
        <span>${new Date().toLocaleTimeString("zh-CN", { hour12: false })}</span>
        <strong>${index === 0 ? "INFO" : "STATE"}</strong>
        <p>${escapeHtml(item)}</p>
      </div>
    `).join("");
  }
}

function renderChatHistory(elfieId) {
  const historyNode = byId("elf-chat-history");
  if (!historyNode) return;
  historyNode.dataset.elfieId = elfieId;
  const items = chatHistory.get(elfieId) || [];
  if (!items.length) {
    historyNode.innerHTML = `
      <div class="history-divider">还没有对话。发送第一句话后，精灵会在下一次 tick 响应。</div>
    `;
    return;
  }
  historyNode.innerHTML = items.map((item) => `
    <article class="chat-bubble ${item.sender === "user" ? "user" : ""}">
      <span>${escapeHtml(item.sender === "user" ? "你" : "精灵")} · ${escapeHtml(item.time)}</span>
      <p>${escapeHtml(item.text)}</p>
      ${item.meta ? `<small>${escapeHtml(item.meta)}</small>` : ""}
    </article>
  `).join("");
  historyNode.scrollTop = historyNode.scrollHeight;
}

function renderElfDetail(id) {
  const elf = elves.find((item) => item.id === id);
  if (!elf || !detailContent) return;
  detailHeading.textContent = `精灵详情：${elf.name}`;
  const canChat = elf.owned;
  detailContent.innerHTML = `
    <div class="elf-detail-layout">
      <section class="config-card detail-config">
        <div class="elf-detail-head">
          <div class="elf-avatar large" aria-hidden="true"></div>
          <div>
            <h3>${escapeHtml(elf.name)}</h3>
            <p>${escapeHtml(elf.owner)} · ${escapeHtml(labelForAnatomy(elf.anatomy))}</p>
          </div>
        </div>
        <label class="form-row">
          <span>性格风格</span>
          <input type="text" value="${escapeHtml(elf.role)}" readonly />
        </label>
        <label class="form-row">
          <span>外形</span>
          <input type="text" value="${escapeHtml(labelForAppearance(elf.height, elf.build))}" readonly />
        </label>
        <label class="form-row">
          <span>所在精灵巢</span>
          <input type="text" value="${escapeHtml(`${elf.room} · ${elf.bed}`)}" readonly />
        </label>
        <div class="callout privacy">${elf.owned ? "你可以在用户工作台继续聊天和管理配置。" : "管理员只能查看公开元信息，不能读取主人聊天或私密配置。"}</div>
      </section>
      <section class="chat-panel">
        <div class="chat-toolbar">
          <div>
            <h3>主人聊天</h3>
            <p id="ws-status-label">${escapeHtml(wsStatusLabel())}</p>
          </div>
          <button class="ghost-button" type="button" id="chat-reconnect-button">重新连接</button>
        </div>
        <div class="chat-history" id="elf-chat-history" data-elfie-id="${escapeHtml(elf.id)}"></div>
        <form class="chat-input-row" id="elf-chat-form" data-elfie-id="${escapeHtml(elf.id)}">
          <input
            id="elf-chat-input"
            type="text"
            maxlength="240"
            placeholder="${canChat ? "输入要对精灵说的话" : "只有精灵主人可以聊天"}"
            ${canChat ? "" : "disabled"}
          />
          <button class="primary-button" type="submit" id="chat-send-button" ${canChat ? "" : "disabled"}>发送</button>
        </form>
      </section>
    </div>
  `;
  renderChatHistory(elf.id);
  updateWsIndicators();
  setView("elf-detail");
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("button, [data-close-drawer], [data-view-shortcut]");
  if (!target) {
    if (!event.target.closest(".popover")) closeMenus();
    return;
  }

  if (target.matches("[data-view]")) {
    setView(target.dataset.view);
  }
  if (target.matches("[data-view-shortcut]")) {
    setView(target.dataset.viewShortcut);
  }
  if (target.matches("[data-open-elf]")) {
    renderElfDetail(target.dataset.openElf);
  }
  if (target.matches("[data-back-to-elves]")) {
    setView("elves");
  }
  if (target.matches("[data-open-adoption]")) {
    openDrawer(adoptionDrawer);
  }
  if (target.matches("[data-open-profile-menu]")) {
    togglePopover(profileMenu, target);
  }
  if (target.matches("[data-open-profile]")) {
    fillProfileForm();
    openDrawer(profileDrawer);
  }
  if (target.matches("[data-open-alerts]")) {
    togglePopover(byId("alerts-menu"), target);
  }
  if (target.id === "chat-reconnect-button") {
    disconnectRealtime(true);
  }
  if (target.matches("[data-edit-bed]")) {
    const bedId = target.dataset.editBed;
    const nextX = prompt("床位 grid_x", target.dataset.gridX || "0");
    if (nextX === null) return;
    const nextY = prompt("床位 grid_y", target.dataset.gridY || "0");
    if (nextY === null) return;
    fetchJson(`/api/admin/nest/beds/${bedId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ grid_x: Number(nextX), grid_y: Number(nextY) }),
    })
      .then(loadRooms)
      .then(() => addSystemNotice(`床位 ${bedId} 坐标已更新。`))
      .catch((error) => addSystemNotice(error.message || "床位更新失败"));
  }
  if (target.matches("[data-close-drawer]")) {
    closeDrawers();
  }

  if (target.id === "refresh-overview") loadDashboardData();
  if (target.id === "refresh-rooms") loadRooms();
  if (target.id === "refresh-config") loadSystemConfig();
  if (target.id === "refresh-providers") loadProviders();
  if (target.id === "refresh-models") loadModels();
  if (target.id === "refresh-food") {
    loadSystemConfig();
    loadModels();
  }
  if (target.id === "refresh-logs") renderLogs();
});

scopeFilter?.addEventListener("change", renderElves);
ownerFilter?.addEventListener("change", renderElves);
byId("model-provider-filter")?.addEventListener("change", renderModels);
byId("model-status-filter")?.addEventListener("change", renderModels);
byId("global-search")?.addEventListener("input", (event) => {
  globalQuery = (event.target.value || "").trim().toLowerCase();
  applySearchShortcut();
  renderElves();
  renderProviders();
  renderModels();
  loadUsers();
});

document.addEventListener("change", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLSelectElement) || !target.matches("[data-assign-bed]")) return;
  const elfieId = target.dataset.assignBed || "";
  const bedId = target.value ? Number(target.value) : null;
  if (!elfieId || !bedId) return;
  try {
    await fetchJson(`/api/admin/nest/elfies/${encodeURIComponent(elfieId)}/bed`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bed_id: bedId }),
    });
    await loadElves();
    await loadRooms();
    addSystemNotice(`已为 ${elfieId} 分配床位。`);
  } catch (error) {
    addSystemNotice(error.message || "床位分配失败");
  }
});

const adoptionForm = byId("adoption-form");
if (adoptionForm) {
  adoptionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = byId("adoption-message");
    if (message) {
      message.textContent = "正在领养...";
      message.style.color = "var(--text-secondary)";
    }

    const species = byId("adopt-species")?.value || "biped";
    const height = byId("adopt-height")?.value || "standard";
    const build = byId("adopt-build")?.value || "standard";
    const personality = byId("adopt-personality")?.value || "活泼好动";
    const name = (byId("adopt-name")?.value || "").trim() || `新精灵${elves.length + 1}`;

    try {
      await fetchJson("/api/user/adopt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          anatomy_type: species,
          personality_style: personality,
          height,
          build,
        }),
      });
      if (message) {
        message.textContent = "领养成功";
        message.style.color = "var(--status-success)";
      }
      await loadElves();
      setTimeout(() => {
        closeDrawers();
        if (message) message.textContent = "";
      }, 1200);
    } catch (error) {
      if (message) {
        message.textContent = error.message || "领养失败";
        message.style.color = "var(--status-error)";
      }
    }
  });
}

const roomCreateForm = byId("room-create-form");
if (roomCreateForm) {
  roomCreateForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setFormMessage("room-message", "正在创建...");
    try {
      await fetchJson("/api/admin/nest/rooms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: (byId("room-create-name")?.value || "New Room").trim(),
          max_capacity: Number(byId("room-create-capacity")?.value || 4),
        }),
      });
      setFormMessage("room-message", "房间已创建", "success");
      await loadRooms();
    } catch (error) {
      setFormMessage("room-message", error.message || "创建失败", "error");
    }
  });
}

const profileForm = byId("profile-form");
if (profileForm) {
  profileForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setFormMessage("profile-message", "正在保存...");
    try {
      const updated = await fetchJson("/api/auth/me/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nickname: (byId("profile-edit-name")?.value || "").trim(),
          avatar_color: Number(byId("profile-edit-color")?.value || 0),
        }),
      });
      updateProfileHeader(updated);
      setFormMessage("profile-message", "个人信息已保存", "success");
      addSystemNotice("个人信息已更新。");
    } catch (error) {
      setFormMessage("profile-message", error.message || "保存失败", "error");
    }
  });
}

const passwordForm = byId("password-form");
if (passwordForm) {
  passwordForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const oldPassword = byId("profile-old-password")?.value || "";
    const newPassword = byId("profile-new-password")?.value || "";
    if (!oldPassword || !newPassword) {
      setFormMessage("password-message", "请填写旧密码和新密码", "error");
      return;
    }
    setFormMessage("password-message", "正在修改...");
    try {
      await fetchJson("/api/auth/me/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
      });
      byId("profile-old-password").value = "";
      byId("profile-new-password").value = "";
      setFormMessage("password-message", "密码已更新", "success");
      addSystemNotice("登录密码已更新。");
    } catch (error) {
      setFormMessage("password-message", error.message || "修改失败", "error");
    }
  });
}

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.id !== "elf-chat-form") return;
  event.preventDefault();
  const elfieId = form.dataset.elfieId || "";
  const input = byId("elf-chat-input");
  const text = (input?.value || "").trim();
  if (!text) return;
  try {
    sendUserMessage(elfieId, text);
    addChatItem(elfieId, {
      sender: "user",
      text,
      meta: "已投递到下一次 tick",
    });
    input.value = "";
  } catch (error) {
    addChatItem(elfieId, {
      sender: "system",
      text: error.message || "消息发送失败",
      meta: "连接状态",
    });
  }
});

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.matches(".system-config-form")) return;
  event.preventDefault();
  const section = form.dataset.systemSection || "";
  const message = document.querySelector(`[data-system-message="${section}"]`);
  if (message) {
    message.textContent = "正在保存...";
    message.style.color = "var(--text-secondary)";
  }
  try {
    const saved = await fetchJson(`/api/admin/system/${section}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(systemPayload(section, form)),
    });
    systemConfig[section] = saved;
    renderSystemConfig();
    renderFoodStrategy();
    addSystemNotice(`系统配置已保存：${section}`);
  } catch (error) {
    if (message) {
      message.textContent = error.message || "保存失败";
      message.style.color = "var(--status-error)";
    }
  }
});

document.querySelectorAll("[data-config-tab]").forEach((tab) => {
  tab.addEventListener("click", () => {
    const name = tab.dataset.configTab;
    document.querySelectorAll("[data-config-tab]").forEach((item) => item.classList.toggle("active", item === tab));
    document.querySelectorAll("[data-config-panel]").forEach((panel) => {
      panel.classList.toggle("active", panel.dataset.configPanel === name);
    });
  });
});

document.querySelectorAll("[data-step]").forEach((stepButton) => {
  stepButton.addEventListener("click", () => {
    wizardStep = Number(stepButton.dataset.step || 0);
    updateWizard();
  });
});

function updateWizard() {
  document.querySelectorAll("[data-step]").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.step || 0) === wizardStep);
  });
  document.querySelectorAll("[data-wizard-panel]").forEach((panel) => {
    panel.classList.toggle("active", Number(panel.dataset.wizardPanel || 0) === wizardStep);
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeDrawers();
    closeMenus();
  }
});

checkAuth();
