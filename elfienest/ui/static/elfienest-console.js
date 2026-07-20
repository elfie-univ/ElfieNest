let currentUser = null;
let csrfToken = "";
let wsPort = 8766;
let role = "owner";
let activeView = "overview";
let previousView = "overview";
let wizardStep = 0;
let elves = [];
let rooms = [];
let providers = [];
let models = [];
let systemConfig = {};
let toolConfigs = {};
let foodCatalog = { foods: {} };
let pendingFoodProposal = null;
let globalQuery = "";
let adoptionInfo = null;
let providerModalMode = "edit";
let roomLayoutEditing = false;
let roomCameraOpen = false;
let cameraStatus = {
  online: false,
  labels: [],
  active_index: 0,
  desired_index: 0,
  frame_version: 0,
};
let cameraPollTimer = null;
let lastCameraFrameVersion = -1;
let cameraControlsSignature = "";
let godotWebBundle = { ready: false, checked: false, entry_url: "", manifest: {} };
let godotWebRuntimeReady = false;
let roomBedCountSaving = false;
let pendingRoomBedCount = null;
let roomLayoutStatusOverride = "";
let chatHistoryFilters = {
  range: "all",
  keyword: "",
};
let chatHistorySearchTimer = null;
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
const ownerFilter = document.querySelector("#owner-filter");
const elfStatusFilter = document.querySelector("#elf-status-filter");
const elfSpeciesFilter = document.querySelector("#elf-species-filter");
const elfBuildFilter = document.querySelector("#elf-build-filter");
const backdrop = document.querySelector(".drawer-backdrop");
const adoptionDrawer = document.querySelector("#adoption-drawer");
const profileDrawer = document.querySelector("#profile-drawer");
const roomCameraDrawer = document.querySelector("#room-camera-drawer");
const userCreateModal = document.querySelector("#user-create-modal");
const providerConfigModal = document.querySelector("#provider-config-modal");
const roomLayoutConfirmModal = document.querySelector("#room-layout-confirm-modal");
const profileMenu = document.querySelector("#profile-menu");
const detailContent = document.querySelector("#elf-detail-content");
const detailHeading = document.querySelector("#elf-detail-heading");
const adoptionQuotaNote = document.querySelector("#adoption-quota-note");
const openAdoptionButton = document.querySelector("#open-adoption-button");

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
  items.push({ timestamp: new Date().toISOString(), time: nowLabel(), ...item });
  if (items.length > MAX_CHAT_ITEMS) items.splice(0, items.length - MAX_CHAT_ITEMS);
  chatHistory.set(elfieId, items);
  if (activeView === "elf-detail" && byId("elf-chat-history")?.dataset.elfieId === elfieId) {
    renderChatHistory(elfieId);
  }
  renderLogs();
}

function normalizeChatItem(record) {
  const timestamp = record.created_at || record.timestamp || new Date().toISOString();
  const date = new Date(timestamp);
  return {
    sender: record.sender || "system",
    text: record.text || "",
    meta: record.meta || "",
    timestamp,
    time: Number.isNaN(date.getTime()) ? nowLabel() : date.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }),
  };
}

async function loadChatHistory(elfieId) {
  if (!elfieId) return;
  const params = new URLSearchParams({
    range: chatHistoryFilters.range || "all",
    q: chatHistoryFilters.keyword || "",
    limit: "200",
  });
  try {
    const records = await fetchJson(`/api/user/elfies/${encodeURIComponent(elfieId)}/chat-history?${params.toString()}`);
    chatHistory.set(elfieId, (Array.isArray(records) ? records : []).map(normalizeChatItem));
    renderChatHistory(elfieId);
  } catch (error) {
    if (error.status === 404) {
      chatHistory.set(elfieId, [{
        sender: "system",
        text: "只有精灵主人可以查看这只精灵的历史消息。",
        meta: "权限范围",
        timestamp: new Date().toISOString(),
        time: nowLabel(),
      }]);
      renderChatHistory(elfieId);
      return;
    }
    addSystemNotice(error.message || "历史消息读取失败");
  }
}

function wsStatusLabel() {
  if (wsState === "online") return "WebSocket 已连接";
  if (wsState === "connecting") return "WebSocket 连接中";
  if (wsState === "error") return "WebSocket 连接异常";
  return "WebSocket 未连接";
}

function updateWsIndicators() {
  setText("ws-status-label", wsStatusLabel());
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
  return `${protocol}//${window.location.hostname}:${wsPort}`;
}

function connectRealtime() {
  if (!currentUser || wsState === "connecting" || wsState === "online") return;
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
      payload: {},
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

async function loadWsConfig() {
  try {
    const config = await fetchJson("/api/ws-config");
    if (Number.isInteger(config.port) && config.port > 0 && config.port <= 65535) {
      wsPort = config.port;
    }
  } catch {
    // Keep the default for older services that do not expose ws-config.
  }
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
    ["tools", ["工具", "搜索", "文件", "沙箱", "tool"]],
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

function isNotFoundError(error) {
  return error?.status === 404 || error?.message === "Not Found" || error?.message === "Room not found";
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

function resetUserCreateForm() {
  const form = byId("user-create-form");
  form?.reset();
  setFormMessage("user-create-message", "");
  const usernameInput = byId("user-create-username");
  if (usernameInput) usernameInput.focus();
}

function authTypeForApiMode(apiMode) {
  if (apiMode === "anthropic_messages") return "x-api-key";
  if (apiMode === "ollama") return "none";
  return "bearer";
}

function providerById(providerId) {
  return providers.find((provider) => provider.provider_id === providerId) || null;
}

function providerDisplayName(providerId) {
  const provider = providerById(providerId);
  return provider?.name || providerId || "未设置";
}

function resetProviderConfigForm(provider = null) {
  const form = byId("provider-config-form");
  form?.reset();
  const createMode = !provider;
  providerModalMode = createMode ? "create" : "edit";
  const apiMode = provider?.api_mode || "chat_completions";
  const providerIdInput = byId("provider-config-id");
  const nameInput = byId("provider-config-name");
  const apiBaseInput = byId("provider-config-api-base");
  const apiKeyInput = byId("provider-config-api-key");
  const testModelInput = byId("provider-config-test-model");
  const modelsInput = byId("provider-config-models");
  const apiModeSelect = byId("provider-config-api-mode");
  const authTypeSelect = byId("provider-config-auth-type");

  setText("provider-config-title", createMode ? "新增供应商" : `配置供应商：${provider.name || provider.provider_id}`);
  if (byId("provider-config-mode")) byId("provider-config-mode").value = providerModalMode;
  if (providerIdInput) {
    providerIdInput.value = provider?.provider_id || "";
    providerIdInput.readOnly = !createMode;
    providerIdInput.placeholder = createMode ? "例如 custom_openai_2" : "";
  }
  if (nameInput) nameInput.value = provider?.display_name || provider?.name || "";
  if (apiBaseInput) apiBaseInput.value = provider?.api_base || "";
  if (apiKeyInput) {
    apiKeyInput.value = "";
    apiKeyInput.placeholder = provider?.has_api_key ? "已保存，留空不修改" : "填写 API Key";
  }
  if (testModelInput) testModelInput.value = provider?.test_model || "";
  if (modelsInput) modelsInput.value = (provider?.models || []).map((item) => `${item.id || item.model_id || ""} | ${item.display_name || item.id || ""}`).join("\n");
  if (apiModeSelect) apiModeSelect.value = apiMode;
  if (authTypeSelect) authTypeSelect.value = provider?.auth_type || authTypeForApiMode(apiMode);
  setFormMessage("provider-config-message", "");
  setTimeout(() => (createMode ? providerIdInput : apiBaseInput)?.focus(), 0);
}

function providerPayloadFromForm(form, includeEmptyApiKey = false) {
  const data = new FormData(form);
  const apiKey = String(data.get("api_key") || "");
  const apiMode = String(data.get("api_mode") || "chat_completions");
  const payload = {
    provider_id: String(data.get("provider_id") || "").trim(),
    display_name: String(data.get("display_name") || "").trim(),
    api_base: String(data.get("api_base") || "").trim(),
    api_mode: apiMode,
    auth_type: String(data.get("auth_type") || authTypeForApiMode(apiMode)),
    test_model: String(data.get("test_model") || "").trim(),
    models: String(data.get("models") || "").split(/\r?\n/).map((line) => {
      const [id, ...labelParts] = line.split("|");
      const modelId = (id || "").trim();
      return modelId ? { id: modelId, display_name: labelParts.join("|").trim() || modelId } : null;
    }).filter(Boolean),
    refresh_models: true,
  };
  if (includeEmptyApiKey || apiKey) payload.api_key = apiKey;
  return payload;
}

async function saveProviderConfig({ verify = false } = {}) {
  const form = byId("provider-config-form");
  if (!(form instanceof HTMLFormElement)) return null;
  const payload = providerPayloadFromForm(form, providerModalMode === "create");
  if (!payload.provider_id) {
    setFormMessage("provider-config-message", "请填写供应商 ID", "error");
    return null;
  }
  if (!payload.api_base && payload.api_mode !== "ollama") {
    setFormMessage("provider-config-message", "请填写 API Base", "error");
    return null;
  }
  const endpoint = providerModalMode === "create"
    ? "/api/owner/providers/"
    : `/api/owner/providers/${encodeURIComponent(payload.provider_id)}`;
  const method = providerModalMode === "create" ? "POST" : "PUT";
  const body = { ...payload };
  delete body.provider_id;
  setFormMessage("provider-config-message", verify ? "正在保存并验证..." : "正在保存...");
  const saved = await fetchJson(endpoint, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(providerModalMode === "create" ? payload : body),
  });
  if (verify) {
    const result = await fetchJson(`/api/owner/providers/${encodeURIComponent(payload.provider_id)}/verify`, { method: "POST" });
    setFormMessage(
      "provider-config-message",
      result.status === "active" ? `已保存，验证可用（${result.latency_ms || 0}ms）` : `已保存，验证未通过：${result.error || result.status}`,
      result.status === "active" ? "success" : "error",
    );
  } else {
    const refresh = saved.model_refresh || {};
    const detail = refresh.status === "updated"
      ? `，已自动更新 ${refresh.count || 0} 个模型`
      : refresh.status === "failed" ? `，模型自动拉取失败，已保留手工目录` : "";
    setFormMessage("provider-config-message", `供应商配置已保存${detail}`, "success");
  }
  await loadProviders();
  await loadModels();
  return saved;
}

function updateProfileHeader(user) {
  currentUser = { ...(currentUser || {}), ...user };
  setText("profile-name", currentUser.nickname || currentUser.username);
  setText("profile-avatar", (currentUser.nickname || currentUser.username || "U").charAt(0).toUpperCase());
}

function systemPayload(section, form) {
  const data = new FormData(form);
  if (section === "adoption") {
    const maxPerUser = Number(data.get("max_elfies_per_user") || 3);
    const speciesIds = String(data.get("allowed_species_ids") || "dog, fox")
      .split(",")
      .map((item) => item.trim())
      .filter((item) => ["dog", "fox"].includes(item));
    const presetNames = ["活泼好动", "安静温顺", "好奇探索", "胆小害羞", "傲娇独立", "完全随机"];
    const enabledPresets = new Set(String(data.get("personality_presets") || presetNames.join(","))
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean));
    return {
      max_elfies_per_user: Math.max(1, Math.min(32, maxPerUser)),
      allowed_species_ids: speciesIds.length ? speciesIds : ["dog", "fox"],
      personality_presets_enabled: Object.fromEntries(
        presetNames.map((name) => [name, enabledPresets.has(name)]),
      ),
    };
  }
  if (section === "engine") {
    const maxRoom = String(data.get("max_elfies_per_room") || "").trim();
    return {
      tick_interval_sec: Number(data.get("tick_interval_sec") || 1.5),
      tts_enabled: data.get("tts_enabled") === "on",
      max_elfies_per_room: maxRoom ? Math.max(1, Math.min(32, Number(maxRoom))) : null,
    };
  }
  return {
    session_ttl_days: Number(data.get("session_ttl_days") || 7),
    rate_limit: {
      max_attempts: Number(data.get("max_attempts") || 5),
      window_seconds: Number(data.get("window_seconds") || 300),
    },
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
    const setupStatus = await fetchJson("/api/auth/setup-status");
    if (setupStatus.need_setup) {
      window.location.replace("/static/setup.html");
      return;
    }
  } catch {
    // 健康检查或旧服务不支持 setup-status 时，继续走常规登录流程。
  }

  try {
    const data = await fetchJson("/api/auth/me");
    currentUser = data;
    csrfToken = data.csrf_token || "";
    setRole(data.role || "user");
    setText("profile-name", data.nickname || data.username);
    setText("profile-role", data.role === "owner" ? "Owner" : "普通用户");
    setText("profile-avatar", (data.nickname || data.username || "U").charAt(0).toUpperCase());

    const loginView = byId("login-view");
    if (loginView) loginView.style.display = "none";
    await loadWsConfig();
    connectRealtime();
    startCameraPolling();
    await loadDashboardData();
  } catch {
    disconnectRealtime();
    stopCameraPolling();
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
      stopCameraPolling();
      currentUser = null;
      const loginView = byId("login-view");
      if (loginView) loginView.style.display = "flex";
      closeMenus();
    }
  });
}

async function loadDashboardData() {
  await loadElves();
  await loadAdoptionInfo();
  await loadRooms();
  if (role === "owner") {
    await Promise.all([
      loadProviders(),
      loadModels(),
      loadTools(),
      loadFoods(),
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
    species: raw.species_id || "fox",
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
    const data = role === "owner" ? await loadOwnerElfies() : await fetchJson("/api/user/elfies");
    elves = (Array.isArray(data) ? data : []).map(normalizeElfie);
  } catch (error) {
    console.error("Failed to load elfies", error);
    elves = [];
  }
  renderElfFilters();
  renderElves();
  setText("metric-overview-active", String(elves.length));
  setText("metric-overview-total", `总计 ${elves.length} 只`);
  renderAdoptionQuota();
}

async function loadOwnerElfies() {
  const [ownerResult, userResult] = await Promise.allSettled([
    fetchJson("/api/owner/elfies"),
    fetchJson("/api/user/elfies"),
  ]);
  const ownerData = ownerResult.status === "fulfilled" ? ownerResult.value : [];
  const userData = userResult.status === "fulfilled" ? userResult.value : [];
  const merged = new Map();
  for (const elf of [...(Array.isArray(ownerData) ? ownerData : []), ...(Array.isArray(userData) ? userData : [])]) {
    const id = elf.elfie_id || elf.id;
    if (id) merged.set(id, elf);
  }
  return Array.from(merged.values());
}

function adoptionQuotaFallback() {
  const max = Number(systemConfig.adoption?.max_elfies_per_user || 3);
  const used = elves.filter((elf) => elf.owned).length;
  return {
    used,
    max,
    remaining: Math.max(0, max - used),
    can_adopt: used < max,
  };
}

function adoptionQuota() {
  return adoptionInfo?.quota || adoptionQuotaFallback();
}

function renderAdoptionQuota() {
  const quota = adoptionQuota();
  if (adoptionQuotaNote) {
    adoptionQuotaNote.textContent = `最多领养 ${quota.max} 只，已领养 ${quota.used} 只，还可领养 ${quota.remaining} 只`;
  }
  if (openAdoptionButton) {
    openAdoptionButton.disabled = !quota.can_adopt;
    openAdoptionButton.setAttribute("aria-disabled", String(!quota.can_adopt));
    openAdoptionButton.title = quota.can_adopt ? "开始领养新精灵" : "领养额度已满";
  }
}

async function loadAdoptionInfo() {
  try {
    adoptionInfo = await fetchJson("/api/user/adoption-info");
  } catch (error) {
    console.error("Failed to load adoption info", error);
    adoptionInfo = { quota: adoptionQuotaFallback() };
  }
  renderAdoptionQuota();
  window.dispatchEvent(new CustomEvent("elfienest:adoption-info", { detail: adoptionInfo }));
  return adoptionInfo;
}

async function loadRooms() {
  try {
    const endpoint = role === "owner" ? "/api/owner/nest/rooms" : "/api/user/nest/rooms";
    rooms = await fetchJson(endpoint);
  } catch (error) {
    console.error("Failed to load rooms", error);
    rooms = [];
  }
  renderRooms();
}

async function loadProviders() {
  try {
    providers = await fetchJson("/api/owner/providers/");
  } catch (error) {
    console.error("Failed to load providers", error);
    providers = [];
  }
  renderProviders();
  renderOverview();
}

async function loadModels() {
  try {
    const catalogModels = await fetchJson("/api/owner/models/");
    models = withProviderConfiguredModels(Array.isArray(catalogModels) ? catalogModels : []);
  } catch (error) {
    console.error("Failed to load models", error);
    models = [];
  }
  renderModelFilters();
  renderModels();
  renderFoodStrategy();
}

async function loadTools() {
  try {
    const payload = await fetchJson("/api/owner/runtime/tools/");
    toolConfigs = payload.tools || {};
  } catch (error) {
    console.error("Failed to load tools", error);
    toolConfigs = {};
  }
  renderTools();
}

async function loadFoods() {
  try {
    foodCatalog = await fetchJson("/api/owner/runtime/foods/");
  } catch (error) {
    console.error("Failed to load foods", error);
    foodCatalog = { foods: {} };
  }
  renderFoodStrategy();
}

function withProviderConfiguredModels(catalogModels) {
  const merged = [...catalogModels];
  const knownIds = new Set(merged.map((model) => model.model_id));
  for (const provider of providers) {
    const configured = [...(provider.models || [])];
    if (provider.test_model && !configured.some((item) => item.id === provider.test_model)) configured.push({ id: provider.test_model, display_name: provider.test_model });
    for (const item of configured) {
      const modelName = String(item.id || item.model_id || "").trim();
      if (!modelName) continue;
      const modelId = `${provider.provider_id}/${modelName}`;
      if (knownIds.has(modelId)) continue;
      knownIds.add(modelId);
      merged.push({
        model_id: modelId,
        provider: provider.provider_id,
        display_name: item.display_name || modelName,
        capabilities: item.capabilities || ["text"],
        context_window: item.context_window || 0,
        cost_tier: item.cost_tier ?? 2,
        visible: true,
        active: provider.status === "active",
      });
    }
  }
  return merged;
}

async function loadSystemConfig() {
  const sections = ["engine", "adoption", "security"];
  const loaded = {};
  await Promise.all(sections.map(async (section) => {
    try {
      loaded[section] = await fetchJson(`/api/owner/system/${section}`);
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
  if (!body || role !== "owner") return;
  try {
    const users = await fetchJson("/api/owner/users");
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
        <span><mark class="status ${user.role === "owner" ? "info" : "success"}">${user.role === "owner" ? "Owner" : "普通用户"}</mark></span>
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

function labelForSpecies(value) {
  const map = { dog: "小狗", fox: "狐狸" };
  return map[value] || value || "未知";
}

function labelForAppearance(height, build) {
  const heights = { short: "矮小", standard: "标准", tall: "高大" };
  const builds = { slim: "纤细", standard: "标准", plump: "圆润" };
  return `${heights[height] || height || "标准"} · ${builds[build] || build || "标准"}`;
}

function elfieAvatarMarkup(elf, extraClass = "") {
  return window.ElfieAvatar3D.markup(elf, extraClass);
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
  const isOwner = nextRole === "owner" || nextRole === "owner";
  role = isOwner ? "owner" : nextRole;
  if (shell) shell.dataset.role = role;
  if (profileRole) profileRole.textContent = isOwner ? "Owner" : "普通用户";
  if (elvesCopy) {
    elvesCopy.textContent = role === "owner"
      ? "Owner 可查看本机精灵概览；私密聊天和配置仍只归拥有者管理。"
      : "这里只显示你的精灵，可领养、聊天，并管理自己的精灵配置。";
  }
  if (roomsCopy) {
    roomsCopy.textContent = role === "owner"
      ? "默认宿舍式精灵巢，管理床位数量、公共生活带和全屋观察视图。"
      : "普通用户可查看精灵巢布局和全屋摄像头观察，不能修改布局或床位。";
  }
  document.querySelectorAll(".owner-action").forEach((node) => {
    node.hidden = role !== "owner";
  });
  setView(role === "owner" ? "overview" : "elves");
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
    tools: "基础工具",
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
  if (nextView === "tools") loadTools();
  if (nextView === "food") loadFoods();
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

function openCenterModal(modal) {
  if (!modal) return;
  closeMenus();
  closeDrawers();
  if (backdrop) backdrop.hidden = false;
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
}

function closeDrawers() {
  if (backdrop) backdrop.hidden = true;
  document.querySelectorAll(".center-modal").forEach((modal) => {
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  });
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

function renderElfFilters() {
  if (!ownerFilter || role !== "owner") return;
  const selected = ownerFilter.value || "all";
  const ownerNames = Array.from(new Set(elves.map((elf) => elf.owner).filter(Boolean))).sort((a, b) => a.localeCompare(b, "zh-CN"));
  ownerFilter.innerHTML = [
    `<option value="all">全部拥有者</option>`,
    `<option value="mine">我的精灵</option>`,
    `<option value="others">其他用户</option>`,
    ...ownerNames.map((owner) => `<option value="owner:${escapeHtml(owner)}">${escapeHtml(owner)}</option>`),
  ].join("");
  ownerFilter.value = Array.from(ownerFilter.options).some((option) => option.value === selected) ? selected : "all";
}

function filteredElves() {
  let list = role === "user" ? elves.filter((elf) => elf.owned) : [...elves];
  const ownerValue = ownerFilter?.value || "all";
  const statusValue = elfStatusFilter?.value || "all";
  const speciesValue = elfSpeciesFilter?.value || "all";
  const buildValue = elfBuildFilter?.value || "all";

  if (role === "owner" && ownerValue === "mine") list = list.filter((elf) => elf.owned);
  if (role === "owner" && ownerValue === "others") list = list.filter((elf) => !elf.owned);
  if (role === "owner" && ownerValue.startsWith("owner:")) {
    list = list.filter((elf) => elf.owner === ownerValue.slice(6));
  }
  if (statusValue !== "all") list = list.filter((elf) => elf.status === statusValue);
  if (speciesValue !== "all") list = list.filter((elf) => elf.species === speciesValue);
  if (buildValue.startsWith("height-")) list = list.filter((elf) => elf.height === buildValue.slice(7));
  if (buildValue.startsWith("build-")) list = list.filter((elf) => elf.build === buildValue.slice(6));

  return list.filter((elf) => matchesQuery([
    elf.name,
    elf.owner,
    elf.role,
    elf.species,
    elf.height,
    elf.build,
    elf.statusLabel,
    elf.room,
    elf.bed,
    elf.mood,
  ]));
}

function renderElves() {
  if (!elfGrid) return;
  const list = filteredElves();

  if (!list.length) {
    elfGrid.innerHTML = emptyPanel("没有匹配的精灵", "普通用户只会看到自己领养的精灵。");
    return;
  }

  elfGrid.innerHTML = list.map((elf) => {
    const ownerTag = elf.owned
      ? `<span class="tag own">我的精灵</span>`
      : `<span class="tag owner">${escapeHtml(elf.owner)}</span>`;
    return `
      <article class="elf-card ${elf.owned ? "own" : "other"}">
        <div class="elf-top">
          ${elfieAvatarMarkup(elf, "card-avatar")}
          <mark class="status ${statusClass(elf.status)}">${escapeHtml(elf.statusLabel)}</mark>
        </div>
        <div>
          <h3>${escapeHtml(elf.name)}</h3>
          <p class="line-clamp" title="${escapeHtml(elf.role)}">${escapeHtml(elf.role)}</p>
        </div>
        <div class="tag-row">
          ${ownerTag}
          <span class="tag">${escapeHtml(labelForSpecies(elf.species))}</span>
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

function dormGroupCount(bedCount) {
  return Math.max(1, Math.ceil(Math.max(1, bedCount) / 4));
}

const DORM_PORTAL_WIDTH = 96;
const DORM_MODULE_WIDTH = 300;
const DORM_RIGHT_BOUNDARY_WIDTH = 40;

function dormPlanWidth(groupCount) {
  return DORM_PORTAL_WIDTH + groupCount * DORM_MODULE_WIDTH;
}

function dormMapWidth(groupCount) {
  return dormPlanWidth(groupCount) + DORM_RIGHT_BOUNDARY_WIDTH;
}

const ACTIVITY_ZONES = [
  { 
    key: "dining",
    title: '🍳 聚餐区', 
    detail: '开放厨房 + 长餐桌',
    renderUI: () => `
      <div class="relative w-full h-full flex flex-col p-1 hover:scale-105 transition-transform gap-1">
        <div class="w-full h-8 bg-stone-200 border-2 border-stone-400 rounded-sm flex items-center justify-between px-1 shadow-sm shrink-0">
           <div class="w-5 h-6 bg-gray-300 border border-gray-400 flex"><div class="w-1/2 border-r border-gray-400"></div><div class="w-1/2"></div></div>
           <div class="w-6 h-4 bg-gray-400 rounded-sm flex items-center justify-center shadow-inner"><div class="w-4 h-2 bg-blue-300 rounded-sm"></div></div>
           <div class="w-6 h-5 bg-amber-50 border border-amber-200"></div>
           <div class="w-8 h-6 bg-gray-800 rounded-sm border-2 border-gray-900 flex flex-wrap justify-center content-center gap-0.5 p-0.5">
             <div class="w-2 h-2 bg-red-500 rounded-full shadow-[0_0_3px_red]"></div>
             <div class="w-2 h-2 bg-red-500 rounded-full shadow-[0_0_3px_red]"></div>
           </div>
        </div>
        <div class="flex-1 flex flex-col items-center justify-center relative pt-1">
          <div class="flex gap-1.5 w-full justify-center">
            ${[1,2,3,4].map(i => `<div class="w-4 h-2 bg-orange-300 rounded-t-sm shadow-sm border border-orange-400"></div>`).join('')}
          </div>
          <div class="w-28 h-6 bg-orange-50 border-2 border-orange-300 shadow-md z-10 rounded-sm flex items-center justify-center">
             <div class="w-20 h-1 bg-orange-200/50 rounded-full"></div>
          </div>
          <div class="flex gap-1.5 w-full justify-center">
            ${[1,2,3,4].map(i => `<div class="w-4 h-2 bg-orange-300 rounded-b-sm shadow-sm border border-orange-400"></div>`).join('')}
          </div>
        </div>
      </div>
    `
  },
  { 
    key: "chat",
    title: '🎲 休闲区', 
    detail: '圆桌聊天 + 交友',
    renderUI: () => `
      <div class="relative w-20 h-20 flex items-center justify-center hover:scale-105 transition-transform">
        <div class="w-12 h-12 rounded-full bg-amber-200/90 border-2 border-amber-400 shadow-md z-10 flex items-center justify-center">
           <div class="w-8 h-8 rounded-full border border-amber-300/50"></div>
        </div>
        <div class="absolute top-0 w-4 h-3 bg-blue-400 rounded-t-full border border-blue-500 shadow-sm"></div>
        <div class="absolute bottom-0 w-4 h-3 bg-blue-400 rounded-b-full border border-blue-500 shadow-sm"></div>
        <div class="absolute left-0 w-3 h-4 bg-blue-400 rounded-l-full border border-blue-500 shadow-sm"></div>
        <div class="absolute right-0 w-3 h-4 bg-blue-400 rounded-r-full border border-blue-500 shadow-sm"></div>
      </div>
    `
  },
  { 
    key: "media",
    title: '📺 影音室', 
    detail: '大沙发 + 大电视',
    renderUI: () => `
      <div class="relative w-full h-full flex flex-col items-center justify-center p-2 hover:scale-105 transition-transform gap-3">
         <div class="w-24 h-2 bg-gray-800 rounded-sm shadow-[0_4px_15px_rgba(59,130,246,0.6)] border border-gray-900 flex justify-center items-center">
           <div class="w-16 h-[1px] bg-blue-400/50"></div>
         </div>
         <div class="w-24 h-12 border-b-8 border-x-8 border-indigo-300 rounded-b-xl flex items-end justify-center pb-1 shadow-md bg-indigo-50/30">
           <div class="w-12 h-5 bg-white/80 border border-gray-200 shadow-sm rounded-sm backdrop-blur-sm"></div>
         </div>
      </div>
    `
  },
  {
    key: "gym",
    title: '🏋️ 健身房',
    detail: '器械 + 自由力量区',
    renderUI: () => `
      <div class="flex w-full h-full items-center justify-between p-1 gap-2 hover:scale-105 transition-transform">
        <div class="flex gap-1 h-full max-h-[60px]">
          ${[1,2].map(i => `
            <div class="w-5 h-full bg-gray-700 rounded-sm border border-gray-800 flex flex-col items-center p-0.5 shadow-md">
              <div class="w-full h-2.5 bg-cyan-950 border-b border-gray-600 flex justify-center items-center">
                <div class="w-2 h-0.5 bg-cyan-400 rounded-full animate-pulse"></div>
              </div>
              <div class="w-2.5 flex-1 bg-gray-800 mt-0.5 border-x border-gray-600"></div>
            </div>
          `).join('')}
        </div>
        <div class="flex-1 h-full max-h-[60px] bg-blue-50/50 border border-blue-200 rounded-sm flex items-center justify-around p-1 relative">
          <div class="w-6 h-12 bg-red-100 border border-red-300 flex items-center justify-center relative shadow-sm">
             <div class="absolute w-10 h-1 bg-gray-400 rounded-full"></div>
             <div class="absolute left-[-2px] w-1.5 h-4 bg-gray-800 rounded-sm"></div>
             <div class="absolute right-[-2px] w-1.5 h-4 bg-gray-800 rounded-sm"></div>
          </div>
          <div class="flex flex-col gap-1 items-center">
             <div class="w-8 h-5 bg-purple-200 border border-purple-300 rounded-sm shadow-inner flex items-center justify-center">
               <div class="w-4 h-1 bg-gray-100/80 rounded-full"></div>
             </div>
             <div class="flex gap-1">
               <div class="w-2.5 h-2.5 bg-gray-800 rounded-full"></div>
               <div class="w-2.5 h-2.5 bg-gray-800 rounded-full"></div>
             </div>
          </div>
        </div>
      </div>
    `
  },
  {
    key: "garden",
    title: '🌱 小花园',
    detail: '绿植水景 + 宠物',
    renderUI: () => `
      <div class="w-full h-full bg-green-50/80 border-2 border-green-200 rounded-lg flex relative overflow-hidden hover:scale-105 transition-transform shadow-inner">
        <div class="absolute inset-0 bg-[radial-gradient(circle_at_bottom_right,rgba(134,239,172,0.4)_0%,transparent_70%)]"></div>
        <div class="absolute top-1 bottom-1 left-1/3 flex flex-col justify-around">
           <div class="w-4 h-3 bg-stone-300 rounded-[40%_60%_70%_30%] shadow-sm ml-2"></div>
           <div class="w-4 h-3 bg-stone-300 rounded-[60%_40%_30%_70%] shadow-sm -ml-1"></div>
           <div class="w-4 h-3 bg-stone-300 rounded-[50%_50%_60%_40%] shadow-sm ml-1"></div>
        </div>
        <div class="absolute top-2 left-2 w-10 h-8 bg-blue-300/80 rounded-[40%_60%_70%_30%] border-2 border-blue-400 shadow-inner flex items-center justify-center">
           <div class="w-3 h-2 bg-green-500 rounded-full"></div>
           <div class="w-2 h-2 bg-green-400 rounded-full absolute bottom-1 right-1"></div>
        </div>
        <div class="absolute top-1 right-1">
          <div class="w-10 h-10 bg-green-600 rounded-full shadow-lg border-2 border-green-700 absolute right-0 top-0"></div>
          <div class="w-6 h-6 bg-emerald-500 rounded-full absolute top-4 -left-3 border border-emerald-600"></div>
          <div class="w-4 h-4 bg-lime-400 rounded-full absolute top-1 -left-1 shadow-sm border border-lime-500"></div>
        </div>
        <div class="absolute bottom-1 right-2 w-8 h-8 bg-amber-100 rounded-full border-2 border-amber-300 flex items-center justify-center shadow-md">
          <div class="w-5 h-4 bg-amber-700 rounded-t-full border border-amber-800 shadow-inner flex justify-center items-end">
             <div class="w-2.5 h-2 bg-gray-900 rounded-t-full"></div>
          </div>
        </div>
      </div>
    `
  },
  {
    key: "workspace",
    title: '💻 工作台',
    detail: '电脑排座 + 手工台',
    renderUI: () => `
      <div class="flex flex-col w-full h-full items-center justify-between p-1 hover:scale-105 transition-transform gap-1">
        <div class="w-full flex flex-col items-center">
           <div class="flex gap-3 w-full justify-center mb-0.5">
              ${[1,2,3].map(i => `<div class="w-4 h-2 bg-gray-600 rounded-t-sm shadow-sm"></div>`).join('')}
           </div>
           <div class="w-full h-6 bg-blue-50 border-2 border-blue-200 rounded-sm shadow-sm flex justify-evenly items-center px-1">
              ${[1,2,3].map(i => `
                <div class="w-6 h-3 bg-gray-800 rounded-sm border border-gray-900 flex items-center justify-center">
                  <div class="w-4 h-1.5 bg-blue-400/80"></div>
                </div>
              `).join('')}
           </div>
        </div>
        <div class="w-full h-10 bg-stone-300 border-2 border-stone-500 rounded-sm shadow-md relative flex items-center justify-around px-2 overflow-hidden">
           <div class="absolute left-2 w-10 h-6 bg-green-800/80 border border-green-900 grid grid-cols-4 grid-rows-2">
              ${Array.from({length: 8}).map((_, i) => `<div class="border-[0.5px] border-green-700/50"></div>`).join('')}
           </div>
           <div class="absolute right-4 w-8 h-6 bg-blue-200 border border-blue-400 transform rotate-6 shadow-sm flex flex-col justify-evenly p-0.5">
              <div class="w-full h-[1px] bg-blue-500"></div>
              <div class="w-3/4 h-[1px] bg-blue-500"></div>
           </div>
           <div class="absolute bottom-1 right-2 w-2 h-2 bg-purple-400 rounded-full shadow-sm"></div>
           <div class="absolute bottom-1 right-5 w-2 h-2 bg-yellow-400 rounded-sm shadow-sm"></div>
           <div class="absolute top-1 left-1 w-3 h-1 bg-gray-800 rotate-45 shadow-sm"></div>
        </div>
      </div>
    `
  },
  {
    key: "art",
    title: '🎸 艺术角',
    detail: '画架 + 乐器',
    renderUI: () => `
      <div class="flex w-full h-full items-center justify-evenly p-2 hover:scale-105 transition-transform">
        <div class="w-8 h-16 bg-black rounded-sm border border-gray-800 shadow-lg flex">
          <div class="w-3 h-full bg-white ml-auto flex flex-col justify-evenly">
            ${Array.from({length: 10}).map((_, i) => `<div class="h-[1px] w-full bg-gray-400"></div>`).join('')}
          </div>
          <div class="absolute -left-2 top-6 w-3 h-4 bg-amber-800 rounded-sm shadow-sm"></div>
        </div>
        <div class="relative w-12 h-12 flex flex-col items-center justify-center">
          <div class="w-10 h-8 bg-amber-100 border-2 border-amber-700 shadow-md transform rotate-12 z-10 flex items-center justify-center overflow-hidden">
             <div class="w-6 h-6 bg-rose-400/50 rounded-full absolute -top-1 -left-1"></div>
             <div class="w-6 h-6 bg-cyan-400/50 rounded-full absolute -bottom-1 -right-1"></div>
          </div>
          <div class="absolute -bottom-2 -left-1 w-3 h-3 bg-stone-300 rounded-full shadow-sm border border-stone-400"></div>
          <div class="w-4 h-4 bg-amber-600 rounded-full shadow-sm mt-1"></div>
        </div>
      </div>
    `
  },
  {
    key: "reading",
    title: '📚 阅览角',
    detail: '环绕书架 + 中央书桌',
    renderUI: () => `
      <div class="relative flex w-full h-full p-1 hover:scale-105 transition-transform overflow-hidden">
         <div class="absolute top-1 left-1 right-1 h-3 bg-amber-900 border-2 border-amber-950 shadow-sm flex overflow-hidden opacity-90">
           <div class="w-full h-full bg-[linear-gradient(90deg,transparent_2px,#fff_2px,#fff_4px,transparent_4px)] bg-[size:6px_100%] opacity-40"></div>
         </div>
         <div class="absolute top-1 bottom-1 left-1 w-3 bg-amber-900 border-2 border-amber-950 shadow-sm flex overflow-hidden opacity-90">
           <div class="w-full h-full bg-[linear-gradient(0deg,transparent_2px,#fff_2px,#fff_4px,transparent_4px)] bg-[size:100%_6px] opacity-40"></div>
         </div>
         <div class="absolute top-0 left-0 w-8 h-6 bg-stone-800 rounded-br-lg border border-stone-600 flex items-center justify-center shadow-lg z-10">
           <div class="w-4 h-3 bg-orange-500 rounded-t-full animate-pulse blur-[1px] shadow-[0_0_10px_#f97316]"></div>
         </div>
         <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col items-center z-10 mt-1">
            <div class="flex gap-2 w-full justify-center">
               <div class="w-4 h-2 bg-emerald-700 rounded-t-sm shadow-sm"></div>
               <div class="w-4 h-2 bg-emerald-700 rounded-t-sm shadow-sm"></div>
            </div>
            <div class="w-20 h-8 bg-amber-100 border-2 border-amber-600 shadow-lg rounded-sm flex items-center justify-center relative">
               <div class="w-4 h-3 bg-rose-400 border border-rose-500 absolute left-2 rotate-12 shadow-sm"></div>
               <div class="w-5 h-3 bg-blue-100 border border-blue-300 absolute right-2 -rotate-6 shadow-sm flex items-center">
                  <div class="w-full h-[1px] bg-blue-300"></div>
               </div>
            </div>
            <div class="flex gap-2 w-full justify-center">
               <div class="w-4 h-2 bg-emerald-700 rounded-b-sm shadow-sm"></div>
               <div class="w-4 h-2 bg-emerald-700 rounded-b-sm shadow-sm"></div>
            </div>
         </div>
      </div>
    `
  }
];

function dormActivityZones(groupCount) {
  const zones = [];
  for (let i = 0; i < groupCount; i++) {
    zones.push(ACTIVITY_ZONES[i % ACTIVITY_ZONES.length]);
  }
  return zones;
}

function bedOccupantLabel(bed) {
  if (!bed?.occupant_id) return "空闲";
  return bed.occupant_name || "已入住";
}

function shortFloorLabel(value, maxLength = 6) {
  const label = String(value ?? "");
  if (label.length <= maxLength) return label;
  return `${label.slice(0, maxLength - 1)}…`;
}

function renderActivitySymbol(zone) {
  return zone.renderUI ? zone.renderUI() : "";
}

function renderActivityRoom(zone) {
  return `
    <div class="activity-room-card activity-${escapeHtml(zone.key)}">
      <div class="activity-room-head">
        <strong>${escapeHtml(zone.title)}</strong>
        <span>${escapeHtml(zone.detail)}</span>
      </div>
      <div class="activity-room-body">
        ${renderActivitySymbol(zone)}
      </div>
    </div>
  `;
}

function renderDormBedSlot(bed, index, side) {
  const bedNumber = index + 1;
  const occupied = Boolean(bed?.occupant_id);
  const emptyReserve = !bed;
  if (emptyReserve) {
    return `
      <div class="floor-bed-unit reserve ${side === "right" ? "right" : "left"}" aria-label="空白床位区域"></div>
    `;
  }
  const label = bedOccupantLabel(bed);
  const shortLabel = shortFloorLabel(label, 5);
  const className = ["floor-bed-unit", side === "right" ? "right" : "left", occupied ? "occupied" : "", emptyReserve ? "reserve" : ""]
    .filter(Boolean)
    .join(" ");
  return `
    <div class="${className}" title="${escapeHtml(emptyReserve ? `床位 ${bedNumber} 预留` : `床位 ${bedNumber} · ${label}`)}">
      <div class="bed-label-row">
        <span>${String(bedNumber).padStart(2, "0")}</span>
        <strong>${escapeHtml(shortLabel)}</strong>
      </div>
      <div class="bed-furniture">
        <div class="upper-bunk">
          <i></i>
          <span>上铺</span>
        </div>
        <div class="under-desk-plan">
          <i></i>
          <b></b>
          <span>下桌</span>
        </div>
      </div>
    </div>
  `;
}

function renderDormBedGroup(groupIndex, beds, zone) {
  const slotIndexes = [
    groupIndex * 4,
    groupIndex * 4 + 1,
    groupIndex * 4 + 2,
    groupIndex * 4 + 3,
  ];
  return `
    <div class="floor-module">
      <div class="module-activity-area">
        ${renderActivityRoom(zone)}
      </div>
      <div class="main-corridor">
        <span>主干道</span>
      </div>
      <div class="module-dorm-area">
        <div class="room-unit">
          <div class="room-entry">
            <i></i>
            <span>${groupIndex + 1}号房间入口</span>
            <i></i>
          </div>
          <div class="room-interior">
            <div class="bed-stack left">
              ${renderDormBedSlot(beds[slotIndexes[0]], slotIndexes[0], "left")}
              ${renderDormBedSlot(beds[slotIndexes[1]], slotIndexes[1], "left")}
            </div>
            <div class="inner-corridor">
              <span>内部通道</span>
            </div>
            <div class="bed-stack right">
              ${renderDormBedSlot(beds[slotIndexes[2]], slotIndexes[2], "right")}
              ${renderDormBedSlot(beds[slotIndexes[3]], slotIndexes[3], "right")}
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderDormFloorplan(room, beds) {
  const bedCount = Math.max(4, beds.length);
  const groupCount = dormGroupCount(bedCount);
  const zones = dormActivityZones(groupCount);
  const bedGroups = Array.from({ length: groupCount }, (_, index) => (
    renderDormBedGroup(index, beds, zones[index % zones.length])
  )).join("");

  return `
    <div class="nest-floorplan" role="img" aria-label="${escapeHtml(room.name || "Main Nest")} 建筑平面图，包含虫洞终端、主干道、公共功能区和床位房间">
      <aside class="portal-entrance" aria-label="虫洞终端">
        <div class="portal-wall top"><span>主建筑体</span></div>
        <div class="wormhole-terminal">
          <i class="wormhole-ring outer"></i>
          <i class="wormhole-ring inner"></i>
          <i class="wormhole-core"></i>
          <strong>虫洞终端</strong>
          <small>星际穿越</small>
        </div>
        <div class="portal-wall bottom"><span>隔离边界</span></div>
      </aside>
      <div class="floor-modules">
      ${bedGroups}
      </div>
    </div>
  `;
}

function cameraCategory(label, index) {
  if (index === 0 || label === "整体总览") return "总览";
  if (label.startsWith("区域俯视")) return "区域";
  if (label.endsWith("宿舍")) return "宿舍";
  if (label === "传送室") return "入口";
  return "活动区";
}

function cameraLabels() {
  return cameraStatus.labels?.length ? cameraStatus.labels : ["整体总览"];
}

function setCameraImagesReady(ready) {
  byId("room-camera-preview")?.classList.toggle("has-frame", ready);
  byId("room-camera-live-frame")?.classList.toggle("has-frame", ready && !godotWebRuntimeReady);
}

function godotWebRuntimeUrl(status) {
  const version = status.manifest?.generated_at || status.manifest?.godot_version || "current";
  return `${status.entry_url}?v=${encodeURIComponent(version)}`;
}

async function startGodotWebRuntime() {
  const iframe = byId("godot-web-runtime");
  if (!iframe || iframe.getAttribute("src")) return;
  try {
    godotWebBundle = { ...(await fetchJson("/api/godot-web/status")), checked: true };
  } catch {
    godotWebBundle = { ready: false, checked: true, entry_url: "", manifest: {} };
  }
  if (godotWebBundle.ready) {
    iframe.src = godotWebRuntimeUrl(godotWebBundle);
  }
  renderCameraStatus();
}

function stopGodotWebRuntime() {
  const iframe = byId("godot-web-runtime");
  if (iframe) iframe.removeAttribute("src");
  godotWebRuntimeReady = false;
  byId("room-camera-live-frame")?.classList.remove("has-web-runtime");
}

window.addEventListener("message", (event) => {
  if (event.origin !== window.location.origin || event.data !== "elfienest:godot-web-ready") return;
  godotWebRuntimeReady = true;
  byId("room-camera-live-frame")?.classList.add("has-web-runtime");
  renderCameraStatus();
});

function updateCameraFrame() {
  if (!cameraStatus.online || !cameraStatus.frame_version) {
    setCameraImagesReady(false);
    return;
  }
  if (cameraStatus.frame_version === lastCameraFrameVersion) return;
  lastCameraFrameVersion = cameraStatus.frame_version;
  const frameUrl = `/api/camera/frame.jpg?v=${cameraStatus.frame_version}`;
  const image = roomCameraOpen
    ? byId("room-camera-live-image")
    : byId("room-camera-thumbnail");
  if (image) {
    image.onload = () => setCameraImagesReady(true);
    image.onerror = () => setCameraImagesReady(false);
    image.src = frameUrl;
  }
}

function renderCameraStatus() {
  const labels = cameraLabels();
  const activeIndex = Math.max(0, Math.min(labels.length - 1, Number(cameraStatus.active_index || 0)));
  const activeLabel = labels[activeIndex] || "整体总览";
  setText("room-camera-active-title", activeLabel);
  setText("room-camera-thumbnail-title", activeLabel);
  const runtimeAvailable = godotWebBundle.ready;
  const live = cameraStatus.online || godotWebRuntimeReady;
  setText("room-camera-feed-state", live ? "实时" : "离线");
  setText("room-camera-thumbnail-state", cameraStatus.online
    ? "实时"
    : runtimeAvailable ? "3D Runtime 加载中" : "3D Runtime 未构建");
  setText("room-camera-offline-title", runtimeAvailable ? "3D Runtime 加载中" : "3D Runtime 未构建");
  setText("room-camera-offline-copy", runtimeAvailable
    ? "浏览器正在启动内置 Godot Web Runtime"
    : "运行 ./elfie.sh build-godot-web 生成发布资源");
  byId("room-camera-offline-state")?.toggleAttribute("hidden", live);
  const syncStatus = byId("room-sync-status");
  if (syncStatus) {
    const isSyncing = roomBedCountSaving || (cameraStatus.online && cameraStatus.layout_syncing);
    const label = roomLayoutStatusOverride || (isSyncing
      ? "正在重建"
      : cameraStatus.online ? "已同步" : "Godot 离线");
    syncStatus.textContent = label;
    syncStatus.className = `status ${isSyncing ? "warning is-loading" : cameraStatus.online ? "success" : "info"}`;
  }

  const strip = byId("room-camera-view-strip");
  const controlsSignature = `${activeIndex}:${labels.join("\u0000")}`;
  if (strip && controlsSignature !== cameraControlsSignature) {
    cameraControlsSignature = controlsSignature;
    strip.innerHTML = labels.map((label, index) => `
      <button class="camera-view-button ${index === activeIndex ? "active" : ""}" type="button" role="option" data-camera-index="${index}" aria-selected="${index === activeIndex}">
        <span>${escapeHtml(cameraCategory(label, index))}</span>
        <strong>${escapeHtml(label)}</strong>
      </button>
    `).join("");
    requestAnimationFrame(() => {
      strip.querySelector("[data-camera-index].active")?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
        inline: "center",
      });
    });
  }
  updateCameraFrame();
}

async function loadCameraStatus() {
  try {
    cameraStatus = await fetchJson("/api/camera/status");
  } catch {
    cameraStatus = { ...cameraStatus, online: false };
  }
  renderCameraStatus();
}

function startCameraPolling() {
  if (cameraPollTimer) return;
  startGodotWebRuntime();
  loadCameraStatus();
  cameraPollTimer = window.setInterval(loadCameraStatus, 180);
}

function stopCameraPolling() {
  if (cameraPollTimer) window.clearInterval(cameraPollTimer);
  cameraPollTimer = null;
  cameraStatus = { ...cameraStatus, online: false };
  cameraControlsSignature = "";
  stopGodotWebRuntime();
  renderCameraStatus();
}

async function selectRoomCamera(index) {
  const labels = cameraLabels();
  const boundedIndex = Math.max(0, Math.min(labels.length - 1, Number(index || 0)));
  cameraStatus = { ...cameraStatus, active_index: boundedIndex, desired_index: boundedIndex };
  renderCameraStatus();
  await fetchJson("/api/camera/view", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index: boundedIndex }),
  });
}

function stepRoomCamera(direction) {
  const labels = cameraLabels();
  if (!labels.length) return;
  const currentIndex = Number(cameraStatus.active_index || 0);
  selectRoomCamera((currentIndex + direction + labels.length) % labels.length).catch(() => {});
}

function openRoomCameraPreview() {
  roomCameraOpen = true;
  renderRooms();
  openDrawer(roomCameraDrawer);
  selectRoomCamera(0).catch(() => {});
}

function resetRoomCameraPreview() {
  if (!roomCameraOpen) return;
  roomCameraOpen = false;
  selectRoomCamera(0).catch(() => {});
  renderRoomSide();
}

function renderRooms() {
  const mapRender = byId("room-map-render");
  if (!mapRender) return;
  mapRender.innerHTML = "";
  const room = rooms[0];
  mapRender.style.removeProperty("--nest-plan-width");
  mapRender.style.removeProperty("min-width");
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

  setText("room-map-title", `${room.name || "Main Nest"} · 宿舍俯视图`);
  const beds = room.beds || [];
  mapRender.classList.toggle("editing", roomLayoutEditing && role === "owner");
  const groupCount = dormGroupCount(Math.max(4, beds.length));
  const planWidth = dormPlanWidth(groupCount);
  const mapWidth = dormMapWidth(groupCount);
  mapRender.style.setProperty("--nest-plan-width", `${planWidth}px`);
  mapRender.style.setProperty("--nest-map-width", `${mapWidth}px`);
  mapRender.style.minWidth = `${mapWidth}px`;
  mapRender.innerHTML = `
    ${renderDormFloorplan(room, beds)}
    ${roomLayoutEditing ? `
      <div class="room-layout-rules" role="note">
        <strong>布局规则</strong>
        <span>每 4 张床生成 1 个房间模块；模块内编号为左上、左下、右上、右下；顶部公共功能区按模块循环显示圆桌、聚餐、书房和影音区。</span>
      </div>
    ` : ""}
  `;
  renderRoomSide();
}

function renderRoomSide() {
  const unassignedList = byId("unassigned-elfies-list");
  if (!unassignedList) return;
  const room = rooms[0];
  const bedCountInput = byId("room-bed-count");
  const editToggle = byId("room-edit-toggle");
  const cameraToggle = byId("room-camera-toggle");
  const cameraPreview = byId("room-camera-preview");
  const bedAssignmentCard = byId("room-bed-assignment-card");
  if (bedCountInput && room?.beds && !roomBedCountSaving) {
    bedCountInput.value = String(pendingRoomBedCount ?? room.beds.length);
  }
  if (editToggle) editToggle.textContent = roomLayoutEditing ? "隐藏布局规则" : "查看布局规则";
  if (cameraToggle) cameraToggle.textContent = "打开预览";
  cameraPreview?.classList.toggle("open", roomCameraOpen);
  renderCameraStatus();
  if (role === "user") {
    if (bedAssignmentCard) bedAssignmentCard.hidden = true;
    unassignedList.innerHTML = "";
    return;
  }
  if (bedAssignmentCard) bedAssignmentCard.hidden = false;
  setText("bed-panel-title", "床位分配");
  const unassigned = elves.filter((elf) => !elf.raw.bed_id);
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
    grid.innerHTML = emptyPanel("暂无供应商数据", "检查 /api/owner/providers/ 是否可用。");
    return;
  }

  grid.innerHTML = visibleProviders.map((provider) => `
    <article class="provider-card ${provider.status === "active" ? "active" : "muted"}">
      <div class="card-inline-head">
        <strong>${escapeHtml(provider.name || provider.provider_id)}</strong>
        <mark class="status ${statusClass(provider.status)}">${provider.status === "active" ? "可用" : "未配置"}</mark>
      </div>
      <span>${escapeHtml(provider.provider_id)} · ${escapeHtml(provider.api_mode || "chat")} · ${escapeHtml(provider.auth_type || authTypeForApiMode(provider.api_mode))}</span>
      <span class="mono">${escapeHtml(provider.api_base || "未设置 API Base")}</span>
      <span>${provider.has_api_key || provider.provider_id === "ollama" ? "密钥状态正常" : "缺少 API Key"}</span>
      ${provider.test_model ? `<span>测试模型：${escapeHtml(provider.test_model)}</span>` : ""}
      <div class="card-action-row">
        <button class="ghost-button" type="button" data-config-provider="${escapeHtml(provider.provider_id)}">配置</button>
        <button class="ghost-button" type="button" data-verify-provider="${escapeHtml(provider.provider_id)}">验证</button>
      </div>
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

function modelFamilyKey(model) {
  const rawName = model.display_name || (model.model_id || "").split("/").pop() || model.model_id || "";
  return rawName
    .toLowerCase()
    .replace(/\s*\([^)]*\)\s*/g, " ")
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function modelProviderTags(items) {
  return items
    .map((model) => `<span class="tag ${model.active ? "own" : ""}" title="${escapeHtml(model.model_id)}">${escapeHtml(providerDisplayName(model.provider))}</span>`)
    .join(" ");
}

function groupedModels(list) {
  const groups = new Map();
  for (const model of list) {
    const key = modelFamilyKey(model);
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        display_name: model.display_name || model.model_id,
        capabilities: new Set(),
        providers: [],
        context_window: model.context_window || 0,
        cost_tier: model.cost_tier ?? 0,
        visible: false,
        active: false,
      });
    }
    const group = groups.get(key);
    group.providers.push(model);
    for (const capability of model.capabilities || []) group.capabilities.add(capability);
    group.context_window = Math.max(group.context_window || 0, Number(model.context_window || 0));
    group.cost_tier = Math.max(group.cost_tier || 0, Number(model.cost_tier ?? 0));
    group.visible = group.visible || Boolean(model.visible);
    group.active = group.active || Boolean(model.active);
  }
  return Array.from(groups.values()).sort((left, right) => left.display_name.localeCompare(right.display_name, "zh-CN"));
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
  const groups = groupedModels(list);

  table.innerHTML = `
    <div class="table-row model-row table-head">
      <span>模型</span>
      <span>来源供应商</span>
      <span>能力</span>
      <span>上下文</span>
      <span>成本</span>
      <span>状态</span>
    </div>
    ${groups.map((group) => `
      <div class="table-row model-row">
        <span><strong>${escapeHtml(group.display_name)}</strong><small>${group.providers.map((model) => escapeHtml(model.model_id)).join(" / ")}</small></span>
        <span>
          <div class="tag-row compact">${modelProviderTags(group.providers)}</div>
          <small>${group.providers.length} 个来源</small>
        </span>
        <span>${Array.from(group.capabilities).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join(" ") || "text"}</span>
        <span>${escapeHtml(group.context_window || "-")}</span>
        <span><mark class="status info">L${escapeHtml(group.cost_tier ?? 0)}</mark></span>
        <span><mark class="status ${group.active && group.visible ? "success" : "warning"}">${group.active && group.visible ? "可用" : group.visible ? "待配置" : "隐藏"}</mark></span>
      </div>
    `).join("")}
  `;
}

function modelOptionsForProvider(providerId, selectedModel) {
  const providerModels = models.filter((model) => model.provider === providerId);
  const hasSelectedModel = providerModels.some((model) => {
    const modelName = (model.model_id || "").split("/").slice(1).join("/") || model.display_name || model.model_id;
    return selectedModel === model.model_id || selectedModel === modelName;
  });
  const customOption = selectedModel && !hasSelectedModel
    ? `<option value="${escapeHtml(selectedModel)}" selected>${escapeHtml(selectedModel)}（当前配置）</option>`
    : "";
  return [
    `<option value="">选择模型</option>`,
    customOption,
    ...providerModels.map((model) => {
      const modelName = (model.model_id || "").split("/").slice(1).join("/") || model.display_name || model.model_id;
      return `<option value="${escapeHtml(modelName)}" ${selectedModel === modelName || selectedModel === model.model_id ? "selected" : ""}>${escapeHtml(model.display_name || modelName)}</option>`;
    }),
  ].join("");
}

function providerOptions(selectedProvider) {
  const providerIds = providers.length
    ? providers.map((provider) => provider.provider_id)
    : [...new Set(models.map((model) => model.provider).filter(Boolean))];
  const uniqueIds = Array.from(new Set(["ollama", ...providerIds, selectedProvider].filter(Boolean)));
  return uniqueIds.map((providerId) => `
    <option value="${escapeHtml(providerId)}" ${providerId === selectedProvider ? "selected" : ""}>${escapeHtml(providerDisplayName(providerId))}</option>
  `).join("");
}

function renderFoodSlot(slot) {
  const selectedProvider = slot.provider || "ollama";
  const selectedModel = slot.model || "";
  const iconMap = {
    cheap: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="slot-icon cheap-icon"><path d="M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z"></path><line x1="16" y1="8" x2="2" y2="22"></line><line x1="17.5" y1="15" x2="9" y2="15"></line></svg>`,
    deep: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="slot-icon deep-icon"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.44 2.5 2.5 0 0 1 0-3.12 3 3 0 0 1 0-3.88 2.5 2.5 0 0 1 0-3.12A2.5 2.5 0 0 1 9.5 2z"></path><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.44 2.5 2.5 0 0 0 0-3.12 3 3 0 0 0 0-3.88 2.5 2.5 0 0 0 0-3.12A2.5 2.5 0 0 0 14.5 2z"></path></svg>`,
    multimodal: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="slot-icon multimodal-icon"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`
  };
  return `
    <article class="strategy-card editable ${slot.key}">
      <div class="card-inline-head">
        <div class="slot-title-with-icon">
          ${iconMap[slot.key] || ""}
          <strong>${escapeHtml(slot.title)}</strong>
        </div>
        <mark class="status info">${escapeHtml(slot.mode)}</mark>
      </div>
      <p class="slot-desc">${escapeHtml(slot.desc)}</p>
      <div class="food-select-field">
        <span>供应商</span>
        <div class="food-select-control-wrap">
          <select name="${escapeHtml(slot.providerName)}" data-food-provider="${escapeHtml(slot.key)}">
            ${providerOptions(selectedProvider)}
          </select>
        </div>
      </div>
      <div class="food-select-field">
        <span>模型</span>
        <div class="food-select-control-wrap">
          <select name="${escapeHtml(slot.modelName)}" data-food-model="${escapeHtml(slot.key)}" data-selected-model="${escapeHtml(selectedModel)}">
            ${modelOptionsForProvider(selectedProvider, selectedModel)}
          </select>
        </div>
      </div>
    </article>
  `;
}

const FOOD_ORDER = ["coarse", "standard", "focus", "creative", "tool", "vision", "premium", "emergency"];

function renderFoodStrategy() {
  const grid = byId("food-strategy-grid");
  if (!grid) return;
  const foods = foodCatalog.foods || {};
  if (!Object.keys(foods).length) {
    grid.innerHTML = emptyPanel("尚未生成粮食策略", "点击“自动更新粮食策略”生成预览。");
    return;
  }
  grid.innerHTML = FOOD_ORDER.filter((key) => foods[key]).map((key) => {
    const recipe = foods[key];
    const primary = recipe.primary || {};
    return `
      <form class="strategy-card editable food-recipe-form" data-food-key="${escapeHtml(key)}">
        <div class="card-inline-head"><strong>${escapeHtml(recipe.display_name || key)}</strong><mark class="status ${statusClass(recipe.validation_status)}">${escapeHtml(recipe.validation_status || "unverified")}</mark></div>
        <p class="slot-desc">${escapeHtml(recipe.description || "")}</p>
        <label class="food-input-field"><span>主模型（Provider/Model）</span><input name="model" value="${escapeHtml(primary.model || "")}" /></label>
        <label class="food-input-field"><span>推理强度</span><select name="reasoning_profile">${["off", "low", "balanced", "deep", "max", "verify"].map((value) => `<option value="${value}" ${primary.reasoning_profile === value ? "selected" : ""}>${value}</option>`).join("")}</select></label>
        <label class="food-input-field"><span>Max tokens</span><input name="max_tokens" type="number" min="1" value="${escapeHtml(primary.max_tokens || 1500)}" /></label>
        <label class="food-input-field"><span>Temperature</span><input name="temperature" type="number" min="0" max="2" step="0.1" value="${escapeHtml(primary.temperature ?? 0.7)}" /></label>
        <small>Fallback：${escapeHtml((recipe.technical_fallbacks || []).map((item) => item.model).join(" → ") || "无")}</small>
        <p class="form-message" data-food-message="${escapeHtml(key)}"></p>
        <button class="ghost-button" type="submit">保存该配方</button>
      </form>`;
  }).join("");
}

function renderTools() {
  const grid = byId("tool-management-grid");
  if (!grid) return;
  const labels = { web_search: "网络搜索", local_file: "本地文件", code_sandbox: "代码沙箱", skills_evolution: "技能进化" };
  grid.innerHTML = Object.entries(labels).map(([key, label]) => {
    const config = toolConfigs[key] || {};
    let fields = "";
    if (key === "web_search") fields = `
      <label class="form-row"><span>搜索 Provider</span><select name="provider">${["duckduckgo", "brave", "tavily"].map((value) => `<option value="${value}" ${config.provider === value ? "selected" : ""}>${value}</option>`).join("")}</select></label>
      <label class="form-row"><span>API Base（可选）</span><input name="api_base" value="${escapeHtml(config.api_base || "")}" /></label>
      <label class="form-row"><span>API Key</span><input name="api_key" type="password" placeholder="${config.has_api_key ? "已保存，留空不修改" : "DuckDuckGo 无需 Key"}" /></label>
      <label class="form-row"><span>结果数</span><input name="max_results" type="number" min="1" max="10" value="${escapeHtml(config.max_results || 3)}" /></label>`;
    if (key === "local_file") fields = `<label class="form-row"><span>允许根目录</span><input name="root" value="${escapeHtml(config.root || "")}" /></label>`;
    if (key === "code_sandbox") fields = `<label class="form-row"><span>超时秒数</span><input name="timeout_seconds" type="number" min="1" max="60" value="${escapeHtml(config.timeout_seconds || 5)}" /></label>`;
    return `<form class="provider-card tool-config-form" data-tool-key="${key}">
      <div class="card-inline-head"><strong>${label}</strong><mark class="status ${config.enabled ? "success" : "warning"}">${config.enabled ? "已启用" : "已停用"}</mark></div>
      <label class="form-row"><span>启用</span><input name="enabled" type="checkbox" ${config.enabled ? "checked" : ""} /></label>${fields}
      <p class="form-message" data-tool-message="${key}"></p>
      <div class="card-actions"><button class="ghost-button" type="submit">保存</button><button class="ghost-button" type="button" data-verify-tool="${key}">验证</button></div>
    </form>`;
  }).join("");
}

async function previewFoodUpdate() {
  const preview = byId("food-update-preview");
  if (preview) preview.textContent = "正在用模型建议与规则生成预览…";
  pendingFoodProposal = await fetchJson("/api/owner/runtime/foods/update-preview", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ use_llm: true }),
  });
  if (!preview) return;
  const changes = pendingFoodProposal.changes || [];
  preview.innerHTML = `<p>生成来源：${escapeHtml((pendingFoodProposal.generation_sources || []).join(" + ") || "rules")}</p>
    <div class="health-list">${changes.map((change) => `<div><span>${escapeHtml(change.food_key)}: ${escapeHtml(change.old_model || "未配置")} → ${escapeHtml(change.new_model || "不可用")}</span><mark class="status ${change.change_type === "unchanged" ? "info" : "warning"}">${escapeHtml(change.change_type)}</mark></div>`).join("")}</div>
    ${(pendingFoodProposal.warnings || []).map((warning) => `<p class="form-message">${escapeHtml(warning)}</p>`).join("")}
    <div class="card-actions"><button class="primary-button" type="button" id="apply-food-update">确认更新</button><button class="ghost-button" type="button" id="cancel-food-update">放弃</button></div>`;
}

function renderSystemConfig() {
  const engine = systemConfig.engine || {};
  const adoption = systemConfig.adoption || {};
  const security = systemConfig.security || {};
  const adoptionPanel = byId("config-adoption-panel");
  const enginePanel = byId("config-engine-panel");
  const securityPanel = byId("config-security-panel");
  if (adoptionPanel) {
    const enabledPresets = adoption.personality_presets_enabled || {};
    const enabledNames = Object.entries(enabledPresets)
      .filter(([, enabled]) => enabled)
      .map(([name]) => name);
    adoptionPanel.innerHTML = `
      <h3>领养策略</h3>
      <form class="config-grid system-config-form" data-system-section="adoption">
        <label class="form-row"><span>每用户上限</span><input name="max_elfies_per_user" type="number" min="1" max="32" value="${escapeHtml(adoption.max_elfies_per_user || 3)}" /></label>
        <label class="form-row"><span>允许物种（逗号分隔）</span><input name="allowed_species_ids" type="text" value="${escapeHtml((adoption.allowed_species_ids || ["dog", "fox"]).join(", "))}" /></label>
        <label class="form-row"><span>启用性格（逗号分隔）</span><input name="personality_presets" type="text" value="${escapeHtml(enabledNames.join(", "))}" /></label>
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
        <label class="form-row"><span>房间容量</span><input name="max_elfies_per_room" type="number" min="1" max="32" value="${escapeHtml(engine.max_elfies_per_room || "")}" placeholder="不限" /></label>
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
        <label class="form-row"><span>最大登录尝试</span><input name="max_attempts" type="number" min="1" max="100" value="${escapeHtml(security.rate_limit?.max_attempts || 5)}" /></label>
        <label class="form-row"><span>限流窗口（秒）</span><input name="window_seconds" type="number" min="1" max="3600" value="${escapeHtml(security.rate_limit?.window_seconds || 300)}" /></label>
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
    `精灵巢：${role === "owner" ? `读取到 ${rooms.length} 个房间。` : "普通用户为只读权限。"}`,
    `模型供应商：${providers.length || 1} 个供应商，${activeProviders || 1} 个可用。`,
    `模型目录：${models.length} 个模型已纳入粮食策略候选。`,
    "完整进程日志请使用 serve 前台输出或本机日志目录查看。",
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
    const isFiltered = chatHistoryFilters.range !== "all" || Boolean(chatHistoryFilters.keyword);
    historyNode.innerHTML = `
      <div class="history-divider">${isFiltered ? "当前筛选范围没有历史消息。" : "还没有对话。发送第一句话后，精灵会在下一次 tick 响应。"}</div>
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
          ${elfieAvatarMarkup(elf, "detail-avatar")}
          <div>
            <h3>${escapeHtml(elf.name)}</h3>
            <p>${escapeHtml(elf.owner)} · ${escapeHtml(labelForSpecies(elf.species))}</p>
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
        <div class="callout privacy">${elf.owned ? "基础形态和性格已锁定，只能查看不能修改。" : "Owner 只能查看公开元信息，不能读取主人聊天或私密配置。"}</div>
      </section>
      ${elf.owned ? `<section class="config-card detail-config"><h3>精灵粮食权限</h3><div id="elf-food-policy" data-elfie-id="${escapeHtml(elf.id)}">正在读取…</div></section>` : ""}
      <section class="chat-panel">
        <div class="chat-toolbar">
          <div>
            <h3>主人聊天</h3>
            <p id="ws-status-label">${escapeHtml(wsStatusLabel())}</p>
          </div>
          <div class="chat-toolbar-actions">
            <button class="ghost-button" type="button" id="chat-history-reset-button">全部历史</button>
            <button class="ghost-button" type="button" id="chat-reconnect-button">重新连接</button>
          </div>
        </div>
        <div class="chat-history-controls">
          <label class="select-wrap">
            <span>历史时间</span>
            <select id="chat-history-range">
              <option value="all" ${chatHistoryFilters.range === "all" ? "selected" : ""}>全部</option>
              <option value="15m" ${chatHistoryFilters.range === "15m" ? "selected" : ""}>最近 15 分钟</option>
              <option value="1h" ${chatHistoryFilters.range === "1h" ? "selected" : ""}>最近 1 小时</option>
              <option value="today" ${chatHistoryFilters.range === "today" ? "selected" : ""}>今天</option>
            </select>
          </label>
          <label class="search compact">
            <span class="visually-hidden">搜索历史消息</span>
            <input id="chat-history-search" type="search" placeholder="搜索历史消息" value="${escapeHtml(chatHistoryFilters.keyword)}" />
          </label>
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
  if (elf.owned) loadElfFoodPolicy(elf.id);
  loadChatHistory(elf.id);
  updateWsIndicators();
  setView("elf-detail");
}

async function loadElfFoodPolicy(elfieId) {
  const host = byId("elf-food-policy");
  if (!host) return;
  try {
    const policy = await fetchJson(`/api/user/elfies/${encodeURIComponent(elfieId)}/food-policy/`);
    const allowed = new Set(policy.allowed_foods || []);
    host.innerHTML = `<form class="elf-food-policy-form" data-elfie-id="${escapeHtml(elfieId)}">
      <label class="form-row"><span>默认粮食</span><select name="default_food">${FOOD_ORDER.filter((key) => allowed.has(key)).map((key) => `<option value="${key}" ${policy.default_food === key ? "selected" : ""}>${key}</option>`).join("")}</select></label>
      <label class="form-row"><span>Fallback 粮食</span><select name="fallback_food">${FOOD_ORDER.filter((key) => allowed.has(key)).map((key) => `<option value="${key}" ${policy.fallback_food === key ? "selected" : ""}>${key}</option>`).join("")}</select></label>
      <div class="tag-row">${FOOD_ORDER.map((key) => `<label class="tag"><input type="checkbox" name="allowed_foods" value="${key}" ${allowed.has(key) ? "checked" : ""} /> ${key}</label>`).join("")}</div>
      <p class="form-message" id="elf-food-policy-message"></p><button class="ghost-button" type="submit">保存粮食权限</button>
    </form>`;
  } catch (error) {
    host.textContent = error.message || "粮食权限读取失败";
  }
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("button, [data-close-drawer], [data-view-shortcut], [data-open-camera]");
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
    if (!target.disabled) {
      openDrawer(adoptionDrawer);
      loadAdoptionInfo();
    }
  }
  if (target.matches("[data-open-profile-menu]")) {
    togglePopover(profileMenu, target);
  }
  if (target.matches("[data-open-profile]")) {
    fillProfileForm();
    openDrawer(profileDrawer);
  }
  if (target.id === "open-user-create-modal") {
    openCenterModal(userCreateModal);
    resetUserCreateForm();
  }
  if (target.id === "open-provider-create-modal") {
    openCenterModal(providerConfigModal);
    resetProviderConfigForm();
  }
  if (target.matches("[data-config-provider]")) {
    const provider = providerById(target.dataset.configProvider || "");
    openCenterModal(providerConfigModal);
    resetProviderConfigForm(provider);
  }
  if (target.matches("[data-verify-provider]")) {
    const providerId = target.dataset.verifyProvider || "";
    if (providerId) {
      target.disabled = true;
      fetchJson(`/api/owner/providers/${encodeURIComponent(providerId)}/verify`, { method: "POST" })
        .then((result) => {
          addSystemNotice(result.status === "active"
            ? `${providerDisplayName(providerId)} 验证可用。`
            : `${providerDisplayName(providerId)} 验证未通过：${result.error || result.status}`);
          return loadProviders();
        })
        .catch((error) => addSystemNotice(error.message || "供应商验证失败"))
        .finally(() => {
          target.disabled = false;
        });
    }
  }
  if (target.matches("[data-open-alerts]")) {
    togglePopover(byId("alerts-menu"), target);
  }
  if (target.id === "chat-reconnect-button") {
    disconnectRealtime(true);
  }
  if (target.id === "chat-history-reset-button") {
    chatHistoryFilters = { range: "all", keyword: "" };
    const elfieId = byId("elf-chat-history")?.dataset.elfieId || "";
    if (elfieId) renderElfDetail(elfieId);
  }
  if (target.id === "room-edit-toggle") {
    roomLayoutEditing = !roomLayoutEditing;
    renderRooms();
    addSystemNotice(roomLayoutEditing ? "已显示宿舍布局规则。" : "已隐藏宿舍布局规则。");
  }
  if (target.id === "room-camera-toggle") {
    openRoomCameraPreview();
  }
  if (target.matches("[data-open-camera]")) {
    openRoomCameraPreview();
  }
  if (target.matches("[data-camera-index]")) {
    selectRoomCamera(Number(target.dataset.cameraIndex || 0)).catch(() => {});
  }
  if (target.id === "room-camera-previous") {
    stepRoomCamera(-1);
  }
  if (target.id === "room-camera-next") {
    stepRoomCamera(1);
  }
  if (target.matches("[data-close-drawer]")) {
    if (roomCameraDrawer?.classList.contains("open")) resetRoomCameraPreview();
    closeDrawers();
  }

  if (target.id === "refresh-overview") loadDashboardData();
  if (target.id === "refresh-rooms") loadRooms();
  if (target.id === "refresh-config") loadSystemConfig();
  if (target.id === "refresh-providers") loadProviders();
  if (target.id === "refresh-models") loadModels();
  if (target.id === "refresh-tools") loadTools();
  if (target.id === "refresh-food") loadFoods();
  if (target.id === "auto-update-food") previewFoodUpdate().catch((error) => {
    const preview = byId("food-update-preview");
    if (preview) preview.textContent = error.message || "预览生成失败";
  });
  if (target.id === "cancel-food-update") {
    pendingFoodProposal = null;
    const preview = byId("food-update-preview");
    if (preview) preview.textContent = "已放弃本次更新。";
  }
  if (target.id === "apply-food-update" && pendingFoodProposal?.candidate) {
    fetchJson("/api/owner/runtime/foods/update-apply", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: true, candidate: pendingFoodProposal.candidate }),
    }).then(() => {
      pendingFoodProposal = null;
      addSystemNotice("粮食策略已按预览确认更新。");
      loadFoods();
      const preview = byId("food-update-preview");
      if (preview) preview.textContent = "更新已应用。";
    }).catch((error) => {
      const preview = byId("food-update-preview");
      if (preview) preview.textContent = error.message || "更新失败";
    });
  }
  if (target.matches("[data-verify-tool]")) {
    const key = target.dataset.verifyTool || "";
    const message = document.querySelector(`[data-tool-message="${key}"]`);
    if (message) message.textContent = "正在验证…";
    fetchJson(`/api/owner/runtime/tools/${encodeURIComponent(key)}/verify`, { method: "POST" })
      .then((result) => { if (message) message.textContent = result.passed ? "验证通过" : `验证失败：${result.results?.[0]?.message || "未知错误"}`; })
      .catch((error) => { if (message) message.textContent = error.message || "验证失败"; });
  }
  if (target.id === "refresh-logs") renderLogs();
});

[ownerFilter, elfStatusFilter, elfSpeciesFilter, elfBuildFilter].forEach((filter) => {
  filter?.addEventListener("change", renderElves);
});
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
  if (target instanceof HTMLSelectElement && target.matches("[data-food-provider]")) {
    const key = target.dataset.foodProvider || "";
    const modelSelect = document.querySelector(`[data-food-model="${key}"]`);
    if (modelSelect instanceof HTMLSelectElement) {
      modelSelect.innerHTML = modelOptionsForProvider(target.value, "");
      modelSelect.dataset.selectedModel = modelSelect.value || "";
    }
    return;
  }
  if (target instanceof HTMLSelectElement && target.matches("[data-food-model]")) {
    target.dataset.selectedModel = target.value || "";
    return;
  }
  if (target instanceof HTMLSelectElement && target.id === "chat-history-range") {
    chatHistoryFilters.range = target.value || "all";
    const elfieId = byId("elf-chat-history")?.dataset.elfieId || "";
    if (elfieId) loadChatHistory(elfieId);
    return;
  }
  if (!(target instanceof HTMLSelectElement) || !target.matches("[data-assign-bed]")) return;
  const elfieId = target.dataset.assignBed || "";
  const bedId = target.value ? Number(target.value) : null;
  if (!elfieId || !bedId) return;
  try {
    await fetchJson(`/api/owner/nest/elfies/${encodeURIComponent(elfieId)}/bed`, {
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

document.addEventListener("input", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement) || target.id !== "chat-history-search") return;
  chatHistoryFilters.keyword = target.value.trim();
  const elfieId = byId("elf-chat-history")?.dataset.elfieId || "";
  if (!elfieId) return;
  if (chatHistorySearchTimer) clearTimeout(chatHistorySearchTimer);
  chatHistorySearchTimer = setTimeout(() => loadChatHistory(elfieId), 220);
});

async function saveRoomBedCount(requestedBedCount) {
  try {
    return await fetchJson("/api/owner/nest/rooms/default/bed-count", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bed_count: requestedBedCount }),
    });
  } catch (error) {
    if (!isNotFoundError(error)) throw error;
  }

  let room = rooms[0];
  if (!room) {
    await loadRooms();
    room = rooms[0];
  }
  if (!room) throw new Error("没有可保存的房间数据");

  try {
    return await fetchJson(`/api/owner/nest/rooms/${room.id}/bed-count`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bed_count: requestedBedCount }),
    });
  } catch (error) {
    if (!isNotFoundError(error)) throw error;
  }

  await loadRooms();
  room = rooms[0];
  if (!room) throw new Error("房间数据刷新后仍不可用");
  return fetchJson(`/api/owner/nest/rooms/${room.id}/bed-count`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bed_count: requestedBedCount }),
  });
}

function closeRoomLayoutConfirmation() {
  if (roomBedCountSaving) return;
  pendingRoomBedCount = null;
  const bedCountInput = byId("room-bed-count");
  if (bedCountInput) bedCountInput.value = String(rooms[0]?.beds?.length || 4);
  closeDrawers();
}

function setRoomLayoutSaving(saving) {
  roomBedCountSaving = saving;
  const bedCountInput = byId("room-bed-count");
  const saveButton = roomLayoutForm?.querySelector("button[type='submit']");
  const confirmButton = byId("room-layout-confirm-submit");
  const refreshButton = byId("refresh-rooms");
  if (bedCountInput) bedCountInput.disabled = saving;
  if (saveButton) saveButton.disabled = saving;
  if (confirmButton) {
    confirmButton.disabled = saving;
    confirmButton.classList.toggle("is-loading", saving);
  }
  if (refreshButton) {
    refreshButton.disabled = saving;
    refreshButton.classList.toggle("is-loading", saving);
  }
  renderCameraStatus();
}

async function waitForGodotLayout(savedBedCount) {
  await loadCameraStatus();
  if (!cameraStatus.online) return "offline";
  for (let attempt = 0; attempt < 24; attempt += 1) {
    if (Number(cameraStatus.reported_bed_count) === savedBedCount && !cameraStatus.layout_syncing) {
      return "synced";
    }
    await new Promise((resolve) => window.setTimeout(resolve, 250));
    await loadCameraStatus();
    if (!cameraStatus.online) return "offline";
  }
  return "pending";
}

async function confirmRoomLayoutChange() {
  if (roomBedCountSaving || pendingRoomBedCount === null) return;
  const requestedBedCount = pendingRoomBedCount;
  let savedBedCount = null;
  roomLayoutStatusOverride = "正在重建";
  setRoomLayoutSaving(true);
  setFormMessage("room-layout-confirm-message", "正在保存并通知 Godot 重建...");
  setFormMessage("room-message", "正在重建...");
  try {
    const result = await saveRoomBedCount(requestedBedCount);
    await loadRooms();
    savedBedCount = rooms[0]?.beds?.length || 0;
    const expectedBedCount = Number(result.bed_count || requestedBedCount);
    if (savedBedCount !== expectedBedCount) {
      throw new Error(`保存后读取到 ${savedBedCount} 个床位，请刷新后重试`);
    }
    const syncResult = await waitForGodotLayout(savedBedCount);
    roomLayoutStatusOverride = syncResult === "synced"
      ? "已同步"
      : syncResult === "offline" ? "已保存 · Godot 离线" : "已保存 · 等待 Godot";
    setFormMessage("room-message", `已保存 ${savedBedCount} 个床位`, "success");
    closeDrawers();
  } catch (error) {
    roomLayoutStatusOverride = "重建失败";
    setFormMessage("room-layout-confirm-message", error.message || "保存失败", "error");
    setFormMessage("room-message", error.message || "保存失败", "error");
  } finally {
    setRoomLayoutSaving(false);
    pendingRoomBedCount = null;
    const bedCountInput = byId("room-bed-count");
    if (bedCountInput && savedBedCount !== null) bedCountInput.value = String(savedBedCount);
  }
}

const roomLayoutForm = byId("room-layout-form");
if (roomLayoutForm) {
  roomLayoutForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const bedCountInput = byId("room-bed-count");
    const requestedBedCount = Math.max(4, Math.min(32, Number(bedCountInput?.value || 4)));
    const currentBedCount = rooms[0]?.beds?.length || 4;
    if (bedCountInput) bedCountInput.value = String(requestedBedCount);
    if (requestedBedCount === currentBedCount) {
      setFormMessage("room-message", "床位数未变化");
      return;
    }
    pendingRoomBedCount = requestedBedCount;
    setText("room-layout-current-beds", currentBedCount);
    setText("room-layout-next-beds", requestedBedCount);
    setText("room-layout-current-rooms", Math.ceil(currentBedCount / 4));
    setText("room-layout-next-rooms", Math.ceil(requestedBedCount / 4));
    setFormMessage("room-layout-confirm-message", "");
    openCenterModal(roomLayoutConfirmModal);
  });
}

byId("room-layout-confirm-submit")?.addEventListener("click", confirmRoomLayoutChange);
byId("room-layout-confirm-cancel")?.addEventListener("click", closeRoomLayoutConfirmation);
byId("room-layout-confirm-close")?.addEventListener("click", closeRoomLayoutConfirmation);

const userCreateForm = byId("user-create-form");
if (userCreateForm) {
  userCreateForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = userCreateForm.querySelector("button[type='submit']");
    const username = (byId("user-create-username")?.value || "").trim();
    const password = byId("user-create-password")?.value || "";
    const nextRole = byId("user-create-role")?.value || "user";
    if (!username || !password) {
      setFormMessage("user-create-message", "请填写用户名和初始密码", "error");
      return;
    }
    if (submitButton) submitButton.disabled = true;
    setFormMessage("user-create-message", "正在创建...");
    try {
      await fetchJson("/api/owner/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, role: nextRole }),
      });
      setFormMessage("user-create-message", "用户已创建", "success");
      await loadUsers();
      addSystemNotice(`已创建用户：${username}`);
      closeDrawers();
    } catch (error) {
      setFormMessage("user-create-message", error.message || "创建失败", "error");
    } finally {
      if (submitButton) submitButton.disabled = false;
    }
  });
}

const providerConfigForm = byId("provider-config-form");
if (providerConfigForm) {
  byId("provider-config-api-mode")?.addEventListener("change", (event) => {
    const authTypeSelect = byId("provider-config-auth-type");
    if (authTypeSelect instanceof HTMLSelectElement) {
      authTypeSelect.value = authTypeForApiMode(event.target.value || "chat_completions");
    }
  });

  byId("provider-config-verify")?.addEventListener("click", async () => {
    const button = byId("provider-config-verify");
    if (button) button.disabled = true;
    try {
      await saveProviderConfig({ verify: true });
    } catch (error) {
      setFormMessage("provider-config-message", error.message || "保存或验证失败", "error");
    } finally {
      if (button) button.disabled = false;
    }
  });

  providerConfigForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = providerConfigForm.querySelector("button[type='submit']");
    if (submitButton) submitButton.disabled = true;
    try {
      await saveProviderConfig();
      closeDrawers();
    } catch (error) {
      setFormMessage("provider-config-message", error.message || "保存失败", "error");
    } finally {
      if (submitButton) submitButton.disabled = false;
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
  if (form instanceof HTMLFormElement && form.matches(".tool-config-form")) {
    event.preventDefault();
    const key = form.dataset.toolKey || "";
    const data = new FormData(form);
    const payload = { enabled: data.get("enabled") === "on" };
    if (key === "web_search") Object.assign(payload, { provider: String(data.get("provider") || "duckduckgo"), api_base: String(data.get("api_base") || ""), max_results: Number(data.get("max_results") || 3) });
    if (key === "web_search" && data.get("api_key")) payload.api_key = String(data.get("api_key"));
    if (key === "local_file") payload.root = String(data.get("root") || "");
    if (key === "code_sandbox") payload.timeout_seconds = Number(data.get("timeout_seconds") || 5);
    const message = document.querySelector(`[data-tool-message="${key}"]`);
    try {
      await fetchJson(`/api/owner/runtime/tools/${encodeURIComponent(key)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (message) message.textContent = "已保存";
      await loadTools();
    } catch (error) {
      if (message) message.textContent = error.message || "保存失败";
    }
    return;
  }
  if (form instanceof HTMLFormElement && form.matches(".food-recipe-form")) {
    event.preventDefault();
    const key = form.dataset.foodKey || "";
    const current = foodCatalog.foods?.[key] || {};
    const data = new FormData(form);
    const payload = { ...current, primary: { ...(current.primary || {}), model: String(data.get("model") || ""), reasoning_profile: String(data.get("reasoning_profile") || "balanced"), max_tokens: Number(data.get("max_tokens") || 1500), temperature: Number(data.get("temperature") || 0.7) } };
    const message = document.querySelector(`[data-food-message="${key}"]`);
    try {
      const saved = await fetchJson(`/api/owner/runtime/foods/${encodeURIComponent(key)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (message) message.textContent = saved.warnings?.length ? `已保存，警告：${saved.warnings.join("；")}` : "已保存";
      await loadFoods();
    } catch (error) {
      if (message) message.textContent = error.message || "保存失败";
    }
    return;
  }
  if (form instanceof HTMLFormElement && form.matches(".elf-food-policy-form")) {
    event.preventDefault();
    const data = new FormData(form);
    const elfieId = form.dataset.elfieId || "";
    const payload = { default_food: String(data.get("default_food") || "standard"), fallback_food: String(data.get("fallback_food") || "coarse"), allowed_foods: data.getAll("allowed_foods").map(String) };
    try {
      await fetchJson(`/api/user/elfies/${encodeURIComponent(elfieId)}/food-policy/`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      setFormMessage("elf-food-policy-message", "已保存", "success");
      await loadElfFoodPolicy(elfieId);
    } catch (error) {
      setFormMessage("elf-food-policy-message", error.message || "保存失败", "error");
    }
    return;
  }
  if (!(form instanceof HTMLFormElement) || !form.matches(".system-config-form")) return;
  event.preventDefault();
  const section = form.dataset.systemSection || "";
  const message = document.querySelector(`[data-system-message="${section}"]`);
  if (message) {
    message.textContent = "正在保存...";
    message.style.color = "var(--text-secondary)";
  }
  try {
    const saved = await fetchJson(`/api/owner/system/${section}`, {
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

window.ElfieNestConsole = {
  addSystemNotice,
  closeDrawers,
  escapeHtml,
  fetchJson,
  labelForSpecies,
  labelForAppearance,
  loadAdoptionInfo,
  loadElves,
  getAdoptionInfo: () => adoptionInfo,
  getElfieCount: () => elves.length,
};

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (roomCameraDrawer?.classList.contains("open")) resetRoomCameraPreview();
    closeDrawers();
    closeMenus();
  }
});

checkAuth();
