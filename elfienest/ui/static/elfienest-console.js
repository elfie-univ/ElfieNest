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

function statusClass(status) {
  if (["online", "active", "ok", "success", true].includes(status)) return "success";
  if (["inactive", "missing", "warning", false].includes(status)) return "warning";
  if (["error", "failed"].includes(status)) return "error";
  return "info";
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
    await loadDashboardData();
  } catch {
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
    ];
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
  unassignedList.innerHTML = unassigned.length
    ? unassigned.map((elf) => `<div><span>未分配</span><strong>${escapeHtml(elf.name)}</strong></div>`).join("")
    : "<div><span>床位</span><strong>没有未分配的精灵</strong></div>";
}

function renderProviders() {
  const grid = byId("provider-management-grid");
  if (!grid) return;
  const activeCount = providers.filter((provider) => provider.status === "active").length;
  const missingCount = providers.length - activeCount;
  setText("metric-provider-active", String(activeCount));
  setText("metric-provider-missing", String(Math.max(0, missingCount)));

  if (!providers.length) {
    grid.innerHTML = emptyPanel("暂无供应商数据", "检查 /api/admin/providers/ 是否可用。");
    return;
  }

  grid.innerHTML = providers.map((provider) => `
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
      <div class="provider-grid">
        <article class="provider-card active"><strong>每用户上限</strong><span>${escapeHtml(adoption.max_elfies_per_user || 3)} 只精灵</span></article>
        <article class="provider-card"><strong>默认性格</strong><span>${escapeHtml(adoption.default_personality_style || "活泼好动")}</span></article>
        <article class="provider-card"><strong>可选性格</strong><span>${escapeHtml(styles.length ? styles.join("、") : "使用系统默认")}</span></article>
      </div>
    `;
  }
  if (enginePanel) {
    enginePanel.innerHTML = `
      <h3>引擎设置</h3>
      <div class="provider-grid">
        <article class="provider-card"><strong>Tick 间隔</strong><span>${escapeHtml(engine.tick_interval_sec ?? "默认")} 秒</span></article>
        <article class="provider-card"><strong>TTS</strong><span>${engine.tts_enabled === false ? "关闭" : "开启"}</span></article>
        <article class="provider-card"><strong>房间容量</strong><span>${escapeHtml(engine.max_elfies_per_room || "不限")} / 房间</span></article>
      </div>
    `;
  }
  if (securityPanel) {
    securityPanel.innerHTML = `
      <h3>安全设置</h3>
      <div class="provider-grid">
        <article class="provider-card"><strong>会话有效期</strong><span>${escapeHtml(security.session_ttl_days || security.session_ttl_hours || "默认")}</span></article>
        <article class="provider-card"><strong>登录尝试</strong><span>${escapeHtml(security.max_login_attempts || "默认")}</span></article>
        <article class="provider-card"><strong>限流窗口</strong><span>${escapeHtml(security.rate_limit_window_seconds || security.rate_limit_per_minute || "默认")}</span></article>
      </div>
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
  if (overviewLog) {
    overviewLog.innerHTML = items.slice(0, 3).map((item) => `<span>${escapeHtml(item)}</span>`).join("");
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

function renderElfDetail(id) {
  const elf = elves.find((item) => item.id === id);
  if (!elf || !detailContent) return;
  detailHeading.textContent = `精灵详情：${elf.name}`;
  detailContent.innerHTML = `
    <div class="elf-detail-layout detail-single">
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
    </div>
  `;
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
