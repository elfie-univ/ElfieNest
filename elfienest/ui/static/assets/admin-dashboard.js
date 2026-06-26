(function () {
  "use strict";

  const state = {
    user: null,
    csrfToken: "",
    activePanel: "overview",
    activeSystemTab: "llm",
    health: null,
    providers: [],
    models: [],
    users: [],
    elfies: [],
    runtime: null,
    system: {
      llm: null,
      adoption: null,
      engine: null,
      security: null,
    },
    editingProviderId: null,
    editingUserId: null,
    confirmAction: null,
    selectedAvatarColor: 0,
  };

  const PERSONALITY_PRESETS = ["活泼好动", "安静温顺", "好奇探索", "胆小害羞", "傲娇独立", "完全随机"];
  const AVATAR_COLORS = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#06b6d4", "#3b82f6", "#a855f7", "#ec4899"];

  const COMMANDS = [
    {
      title: "启动管理服务",
      body: "用于本机 Web 管理和用户工作台。",
      command: "python scripts/serve.py",
    },
    {
      title: "首次设置向导",
      body: "shell 安装后创建管理员并写入基础运行配置。",
      command: "python scripts/elfie.py setup",
    },
    {
      title: "重启服务",
      body: "配置保存后，如果运行进程需要重新加载，用 CLI 重启。",
      command: "python scripts/elfie.py restart",
    },
    {
      title: "安装 Ollama 运行时",
      body: "准备本地免费兜底模型服务。",
      command: "python runtime/setup_runtime.py",
    },
    {
      title: "拉取轻量模型",
      body: "保证云端模型不可用时仍能解释故障并进行轻量对话。",
      command: "ollama pull qwen3.5:0.8b",
    },
    {
      title: "运行管理面板 E2E",
      body: "验证登录、领养、权限与 API 基础链路。",
      command: "python scripts/e2e_dashboard_check.py",
    },
  ];

  const TITLES = {
    overview: "综合监控",
    setup: "安装向导",
    myElfies: "我的精灵",
    providers: "模型供应商",
    models: "模型目录",
    system: "系统配置",
    users: "用户管理",
    operations: "服务操作",
  };

  const els = {
    pageTitle: document.getElementById("pageTitle"),
    nav: document.getElementById("mainNav"),
    globalSearch: document.getElementById("globalSearch"),
    refreshAllBtn: document.getElementById("refreshAllBtn"),
    loadingOverlay: document.getElementById("loadingOverlay"),
    toastContainer: document.getElementById("toastContainer"),
    overviewMetrics: document.getElementById("overviewMetrics"),
    providerHealthList: document.getElementById("providerHealthList"),
    setupStatusList: document.getElementById("setupStatusList"),
    runtimeNotes: document.getElementById("runtimeNotes"),
    setupTimeline: document.getElementById("setupTimeline"),
    setupRoomLimit: document.getElementById("setupRoomLimit"),
    saveSetupRoomBtn: document.getElementById("saveSetupRoomBtn"),
    myElfieGrid: document.getElementById("myElfieGrid"),
    providerGrid: document.getElementById("providerGrid"),
    addProviderBtn: document.getElementById("addProviderBtn"),
    modelsTable: document.getElementById("modelsTable"),
    modelProviderFilter: document.getElementById("modelProviderFilter"),
    modelVisibleFilter: document.getElementById("modelVisibleFilter"),
    scanModelsBtn: document.getElementById("scanModelsBtn"),
    saveActiveSystemBtn: document.getElementById("saveActiveSystemBtn"),
    usersTable: document.getElementById("usersTable"),
    newUserBtn: document.getElementById("newUserBtn"),
    commandGrid: document.getElementById("commandGrid"),
    modalBackdrop: document.getElementById("modalBackdrop"),
    providerModal: document.getElementById("providerModal"),
    userModal: document.getElementById("userModal"),
    confirmModal: document.getElementById("confirmModal"),
    profileModal: document.getElementById("profileModal"),
    passwordModal: document.getElementById("passwordModal"),
  };

  function escapeHtml(value) {
    if (value == null) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showLoading(show) {
    els.loadingOverlay.hidden = !show;
  }

  function showToast(message, type) {
    const toast = document.createElement("div");
    toast.className = `toast ${type || "info"}`;
    toast.textContent = message;
    els.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-4px)";
      toast.style.transition = "opacity 160ms ease-out, transform 160ms ease-out";
      setTimeout(() => toast.remove(), 180);
    }, 3200);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      showToast("已复制命令", "success");
    } catch (_) {
      showToast("复制失败，请手动选择命令", "error");
    }
  }

  function getCsrfToken() {
    return state.csrfToken || localStorage.getItem("csrf_token") || "";
  }

  async function apiFetch(url, options) {
    const opts = options || {};
    opts.credentials = "include";
    opts.headers = opts.headers || {};
    const method = (opts.method || "GET").toUpperCase();
    if (method !== "GET" && method !== "HEAD") {
      opts.headers["X-CSRF-Token"] = getCsrfToken();
    }
    const response = await fetch(url, opts);
    if (response.status === 401) {
      window.location.href = "/static/login.html";
      throw new Error("未登录");
    }
    let data = null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      data = await response.json();
    }
    if (!response.ok) {
      const detail = data && data.detail ? data.detail : `HTTP ${response.status}`;
      throw new Error(detail);
    }
    return data;
  }

  async function loadCurrentUser() {
    const data = await apiFetch("/api/auth/me");
    state.user = data;
    state.csrfToken = data.csrf_token || "";
    if (state.csrfToken) localStorage.setItem("csrf_token", state.csrfToken);
    if (data.session_token) localStorage.setItem("session_token", data.session_token);
    if (data.role !== "admin") {
      window.location.href = "/static/user.html";
      return data;
    }
    ProfileDropdown.mount(document.getElementById("profileDropdown"), {
      userData: data,
      onLogout() {
        localStorage.removeItem("csrf_token");
        localStorage.removeItem("session_token");
      },
    });
    return data;
  }

  async function loadAllData() {
    showLoading(true);
    try {
      await loadCurrentUser();
      const [health, providers, models, users, elfies, runtime, llm, adoption, engine, security] = await Promise.all([
        apiFetch("/api/health").catch(() => ({ status: "error", engine_ready: false })),
        apiFetch("/api/admin/providers"),
        apiFetch("/api/admin/models"),
        apiFetch("/api/admin/users"),
        apiFetch("/api/user/elfies"),
        apiFetch("/api/admin/runtime/status").catch(() => null),
        apiFetch("/api/admin/system/llm"),
        apiFetch("/api/admin/system/adoption"),
        apiFetch("/api/admin/system/engine"),
        apiFetch("/api/admin/system/security"),
      ]);
      state.health = health;
      state.providers = providers || [];
      state.models = models || [];
      state.users = users || [];
      state.elfies = elfies || [];
      state.runtime = runtime;
      state.system.llm = llm;
      state.system.adoption = adoption;
      state.system.engine = engine;
      state.system.security = security;
      renderAll();
    } catch (error) {
      showToast(error.message || "加载数据失败", "error");
    } finally {
      showLoading(false);
    }
  }

  function renderAll() {
    renderOverview();
    renderSetup();
    renderElfies();
    renderProviders();
    renderModels();
    renderSystemForms();
    renderUsers();
    renderOperations();
    applyGlobalSearch();
  }

  function setPanel(panelId) {
    state.activePanel = panelId;
    els.pageTitle.textContent = TITLES[panelId] || "";
    document.querySelectorAll(".panel").forEach((panel) => {
      panel.classList.toggle("active", panel.dataset.panel === panelId);
    });
    document.querySelectorAll(".nav-item").forEach((button) => {
      button.classList.toggle("active", button.dataset.panel === panelId);
    });
  }

  function statusClass(status) {
    if (status === "active" || status === "ok" || status === true) return "success";
    if (status === "inactive" || status === false) return "warning";
    if (status === "error") return "error";
    return "info";
  }

  function statusLabel(status) {
    if (status === "active") return "可用";
    if (status === "inactive") return "未配置";
    if (status === "unverified") return "待验证";
    if (status === "ok") return "正常";
    if (status === true) return "已启用";
    if (status === false) return "未启用";
    return status || "未知";
  }

  function providerById(providerId) {
    return state.providers.find((provider) => provider.provider_id === providerId);
  }

  function activeProviders() {
    return state.providers.filter((provider) => provider.status === "active").length;
  }

  function visibleModels() {
    return state.models.filter((model) => model.visible !== false).length;
  }

  function renderOverview() {
    const ollama = providerById("ollama");
    const engineReady = Boolean(state.health && state.health.engine_ready);
    const roomLimit = state.system.engine ? state.system.engine.max_elfies_per_room : null;
    const runtimeProviders = state.runtime && state.runtime.providers ? state.runtime.providers : null;
    const runtimeModels = state.runtime && state.runtime.models ? state.runtime.models : null;
    const observer = state.runtime && state.runtime.observer ? state.runtime.observer : null;
    els.overviewMetrics.innerHTML = [
      metricCard("Web 管理", state.health && state.health.status === "ok" ? "正常" : "异常", engineReady ? "引擎已注入" : "管理 API 在线，仿真引擎未注入"),
      metricCard("Provider", String(runtimeProviders ? runtimeProviders.active : activeProviders()), `共 ${runtimeProviders ? runtimeProviders.total : state.providers.length} 个服务商`),
      metricCard("可见模型", String(runtimeModels ? runtimeModels.visible : visibleModels()), `目录总计 ${runtimeModels ? runtimeModels.total : state.models.length} 个模型`),
      metricCard("运行事件", String(observer ? observer.event_count : 0), observer && observer.last_event ? `最近：${observer.last_event.subject}` : "暂无模型或工具事件"),
    ].join("");

    els.providerHealthList.innerHTML = state.providers
      .slice(0, 6)
      .map((provider) => `<div><span>${escapeHtml(provider.name || provider.provider_id)}</span><mark class="status ${statusClass(provider.status)}">${statusLabel(provider.status)}</mark></div>`)
      .join("") || emptyInline("暂无供应商");

    const setupRows = [
      ["管理员账号", state.user ? "已创建" : "待创建", state.user ? "success" : "warning"],
      ["Ollama 兜底", ollama && ollama.status === "active" ? "可用" : "需检查", ollama && ollama.status === "active" ? "success" : "warning"],
      ["模型路由", state.system.llm ? `${state.system.llm.default_cheap_provider} / ${state.system.llm.default_cheap_model}` : "待配置", state.system.llm ? "success" : "warning"],
      ["安全策略", state.system.security ? `${state.system.security.session_ttl_days} 天会话` : "待配置", state.system.security ? "success" : "warning"],
    ];
    els.setupStatusList.innerHTML = setupRows
      .map(([label, value, klass]) => `<div><span>${label}</span><mark class="status ${klass}">${escapeHtml(value)}</mark></div>`)
      .join("");

    const notes = [];
    if (!engineReady) notes.push("[管理] Web 管理 API 已启动，但当前进程未注入仿真引擎；领养后不会自动进入运行房间。");
    if (!ollama || ollama.status !== "active") notes.push("[模型] Ollama 是兜底 Provider，请确认 runtime/setup_runtime.py 已执行。");
    if (!state.providers.some((provider) => provider.provider_id !== "ollama" && provider.status === "active")) notes.push("[订阅] 尚未配置云端 Provider，复杂推理会回落到本地模型。");
    if (state.runtime && Array.isArray(state.runtime.notes)) notes.push(...state.runtime.notes);
    notes.push("[权限] 管理员只能管理自己的精灵详情，不能读取其他用户主人聊天记录。");
    els.runtimeNotes.innerHTML = notes.map((note) => `<span>${escapeHtml(note)}</span>`).join("");
  }

  function metricCard(label, value, help) {
    return `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(help)}</small></article>`;
  }

  function emptyInline(text) {
    return `<div><span>${escapeHtml(text)}</span></div>`;
  }

  function renderSetup() {
    const steps = [
      {
        title: "创建管理员",
        body: "首启 setup 页面创建第一个管理员账号，之后所有系统设置都需要管理员权限。",
        state: state.user ? "完成" : "待完成",
        klass: state.user ? "success" : "warning",
      },
      {
        title: "配置模型供应商",
        body: "至少保留 Ollama；按需添加 OpenAI、DeepSeek、Gemini、Qwen 等订阅。",
        state: state.providers.length ? "已读取" : "待配置",
        klass: state.providers.length ? "success" : "warning",
      },
      {
        title: "设置房间容量",
        body: "当前后端支持单房间容量约束，多房间/床位拓扑等待后端数据模型。",
        state: state.system.engine && state.system.engine.max_elfies_per_room ? `${state.system.engine.max_elfies_per_room} 只` : "不限",
        klass: "info",
      },
      {
        title: "确认领养策略",
        body: "控制每个用户可领养数量、允许体型和性格预设。",
        state: state.system.adoption ? `${state.system.adoption.max_elfies_per_user} 只/用户` : "待配置",
        klass: state.system.adoption ? "success" : "warning",
      },
      {
        title: "启动服务",
        body: "CLI 负责重启和后台进程管理，网页端只展示明确命令，不伪造服务操作。",
        state: "CLI",
        klass: "info",
      },
      {
        title: "用户工作台",
        body: "普通用户登录后可领养、配置自己的精灵，并通过 WebSocket 聊天。",
        state: "可用",
        klass: "success",
      },
    ];
    els.setupTimeline.innerHTML = steps
      .map((step, index) => `
        <article class="setup-step">
          <span class="setup-step-number">${index + 1}</span>
          <div class="card-head">
            <h3>${escapeHtml(step.title)}</h3>
            <mark class="status ${step.klass}">${escapeHtml(step.state)}</mark>
          </div>
          <p class="card-meta">${escapeHtml(step.body)}</p>
        </article>
      `)
      .join("");
    if (state.system.engine) {
      els.setupRoomLimit.value = state.system.engine.max_elfies_per_room == null ? "" : state.system.engine.max_elfies_per_room;
    }
  }

  function anatomyLabel(type) {
    return type === "quadruped" ? "四足" : "双足";
  }

  function renderElfies() {
    if (!state.elfies.length) {
      els.myElfieGrid.innerHTML = `<div class="empty-state">还没有领养精灵。普通用户工作台提供完整领养和聊天流程。</div>`;
      return;
    }
    els.myElfieGrid.innerHTML = state.elfies.map((elfie) => `
      <article class="elfie-card">
        <div class="card-head">
          <h3>${escapeHtml(elfie.name)}</h3>
          <mark class="status info">${anatomyLabel(elfie.anatomy_type)}</mark>
        </div>
        <div class="card-meta">
          <span>性格：${escapeHtml(elfie.personality_style || "-")}</span>
          <span>外形：${escapeHtml(elfie.height || "standard")} / ${escapeHtml(elfie.build || "standard")}</span>
          <span>创建：${escapeHtml((elfie.created_at || "").slice(0, 19))}</span>
        </div>
        <div class="table-actions">
          <a class="ghost-button" href="/static/user.html">进入工作台</a>
        </div>
      </article>
    `).join("");
  }

  function renderProviders() {
    if (!state.providers.length) {
      els.providerGrid.innerHTML = `<div class="empty-state">暂无 Provider 配置。</div>`;
      return;
    }
    els.providerGrid.innerHTML = state.providers.map((provider) => {
      const isOllama = provider.provider_id === "ollama";
      return `
        <article class="provider-card" data-provider-id="${escapeHtml(provider.provider_id)}">
          <div class="card-head">
            <div>
              <h3>${escapeHtml(provider.name || provider.provider_id)}</h3>
              <p class="card-meta">${escapeHtml(provider.provider_id)}</p>
            </div>
            <mark class="status ${statusClass(provider.status)}">${statusLabel(provider.status)}</mark>
          </div>
          <div class="card-meta">
            <span>API：${escapeHtml(provider.api_base || "-")}</span>
            <span>模式：${escapeHtml(provider.api_mode || "-")}</span>
            <span>密钥：${provider.has_api_key ? "已保存" : isOllama ? "不需要" : "未配置"}</span>
          </div>
          <div class="table-actions">
            <button class="ghost-button" type="button" data-action="verify-provider" data-provider-id="${escapeHtml(provider.provider_id)}">验证</button>
            <button class="ghost-button" type="button" data-action="edit-provider" data-provider-id="${escapeHtml(provider.provider_id)}">配置</button>
            ${isOllama ? "" : `<button class="danger-button" type="button" data-action="delete-provider" data-provider-id="${escapeHtml(provider.provider_id)}">删除</button>`}
          </div>
        </article>
      `;
    }).join("");
    populateProviderSelects();
  }

  function renderModels() {
    const providers = Array.from(new Set(state.models.map((model) => model.provider))).sort();
    const currentProvider = els.modelProviderFilter.value || "all";
    els.modelProviderFilter.innerHTML = `<option value="all">全部供应商</option>${providers.map((provider) => `<option value="${escapeHtml(provider)}">${escapeHtml(provider)}</option>`).join("")}`;
    els.modelProviderFilter.value = providers.includes(currentProvider) ? currentProvider : "all";

    const providerFilter = els.modelProviderFilter.value;
    const visibleFilter = els.modelVisibleFilter.value;
    const rows = state.models.filter((model) => {
      if (providerFilter !== "all" && model.provider !== providerFilter) return false;
      if (visibleFilter === "visible" && model.visible === false) return false;
      if (visibleFilter === "hidden" && model.visible !== false) return false;
      return true;
    });

    if (!rows.length) {
      els.modelsTable.innerHTML = `<div class="empty-state">没有匹配的模型。</div>`;
      return;
    }
    els.modelsTable.innerHTML = `
      <div class="table-row table-head model-row">
        <span>模型</span><span>Provider</span><span>能力</span><span>成本</span><span>可见</span><span>操作</span>
      </div>
      ${rows.map((model) => `
        <div class="table-row model-row">
          <span><strong>${escapeHtml(model.display_name || model.model_id)}</strong><small>${escapeHtml(model.model_id)}</small></span>
          <span>${escapeHtml(model.provider)}</span>
          <span>${escapeHtml((model.capabilities || []).join(", ") || "-")}</span>
          <span>${escapeHtml(String(model.cost_tier))}</span>
          <span><mark class="status ${model.visible === false ? "warning" : "success"}">${model.visible === false ? "隐藏" : "可见"}</mark></span>
          <span class="table-actions">
            <button class="ghost-button" type="button" data-action="toggle-model" data-model-id="${escapeHtml(model.model_id)}">${model.visible === false ? "显示" : "隐藏"}</button>
          </span>
        </div>
      `).join("")}
    `;
  }

  function populateProviderSelects() {
    const options = state.providers.map((provider) => `<option value="${escapeHtml(provider.provider_id)}">${escapeHtml(provider.name || provider.provider_id)}</option>`).join("");
    ["llmCheapProvider", "llmDeepProvider", "llmMultimodalProvider"].forEach((id) => {
      const select = document.getElementById(id);
      const current = select.value;
      select.innerHTML = options;
      if (current) select.value = current;
    });
  }

  function renderSystemForms() {
    populateProviderSelects();
    const llm = state.system.llm || {};
    setValue("llmCheapProvider", llm.default_cheap_provider);
    setValue("llmCheapModel", llm.default_cheap_model);
    setValue("llmDeepProvider", llm.default_deep_provider);
    setValue("llmDeepModel", llm.default_deep_model);
    setValue("llmMultimodalProvider", llm.default_multimodal_provider);
    setValue("llmMultimodalModel", llm.default_multimodal_model);
    setValue("llmTemperature", llm.temperature);
    setValue("llmMaxTokens", llm.max_tokens);
    setValue("llmEnergyThreshold", llm.energy_threshold_fast);
    setValue("llmComplexityThreshold", llm.complexity_threshold_deep);

    const adoption = state.system.adoption || {};
    setValue("adoptionMaxElfies", adoption.max_elfies_per_user);
    document.getElementById("anatomyBiped").checked = (adoption.allowed_anatomy_types || []).includes("biped");
    document.getElementById("anatomyQuadruped").checked = (adoption.allowed_anatomy_types || []).includes("quadruped");
    const enabled = adoption.personality_presets_enabled || {};
    document.getElementById("personalityToggles").innerHTML = PERSONALITY_PRESETS.map((preset) => `
      <label class="toggle-card"><input type="checkbox" data-personality="${escapeHtml(preset)}" ${enabled[preset] !== false ? "checked" : ""} /> ${escapeHtml(preset)}</label>
    `).join("");

    const engine = state.system.engine || {};
    setValue("engineTickInterval", engine.tick_interval_sec);
    setValue("engineMaxElfiesPerRoom", engine.max_elfies_per_room == null ? "" : engine.max_elfies_per_room);
    setValue("engineDefaultTtsVoice", engine.default_tts_voice);
    document.getElementById("engineTtsEnabled").checked = engine.tts_enabled !== false;

    const security = state.system.security || {};
    const rateLimit = security.rate_limit || {};
    setValue("securitySessionTtl", security.session_ttl_days);
    setValue("securityMaxAttempts", rateLimit.max_attempts);
    setValue("securityWindowSeconds", rateLimit.window_seconds);
  }

  function setValue(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    el.value = value == null ? "" : value;
  }

  function renderUsers() {
    if (!state.users.length) {
      els.usersTable.innerHTML = `<div class="empty-state">暂无其他用户。</div>`;
      return;
    }
    els.usersTable.innerHTML = `
      <div class="table-row table-head">
        <span>用户</span><span>角色</span><span>精灵数</span><span>创建时间</span><span>操作</span>
      </div>
      ${state.users.map((user) => `
        <div class="table-row">
          <span><strong>${escapeHtml(user.username)}</strong><small>ID ${escapeHtml(user.id)}</small></span>
          <span><mark class="status ${user.role === "admin" ? "info" : "success"}">${user.role === "admin" ? "管理员" : "普通用户"}</mark></span>
          <span>${escapeHtml(user.elfie_count || 0)}</span>
          <span>${escapeHtml((user.created_at || "").slice(0, 19))}</span>
          <span class="table-actions"><button class="ghost-button" type="button" data-action="edit-user" data-user-id="${escapeHtml(user.id)}">编辑</button></span>
        </div>
      `).join("")}
    `;
  }

  function renderOperations() {
    els.commandGrid.innerHTML = COMMANDS.map((item) => `
      <article class="command-card">
        <div>
          <h3>${escapeHtml(item.title)}</h3>
          <p class="card-meta">${escapeHtml(item.body)}</p>
        </div>
        <div class="command-box">
          <code>${escapeHtml(item.command)}</code>
          <button class="icon-button" type="button" data-copy="${escapeHtml(item.command)}" aria-label="复制命令">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 8h11v11H8z"></path><path d="M5 15H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v1"></path></svg>
          </button>
        </div>
      </article>
    `).join("");
  }

  async function saveSystemSection(section) {
    const body = buildSystemPayload(section);
    showLoading(true);
    try {
      state.system[section] = await apiFetch(`/api/admin/system/${section}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      renderAll();
      showToast("配置已保存", "success");
    } catch (error) {
      showToast(`保存失败：${error.message}`, "error");
    } finally {
      showLoading(false);
    }
  }

  function buildSystemPayload(section) {
    if (section === "llm") {
      return {
        default_cheap_provider: valueOf("llmCheapProvider"),
        default_cheap_model: valueOf("llmCheapModel"),
        default_deep_provider: valueOf("llmDeepProvider"),
        default_deep_model: valueOf("llmDeepModel"),
        default_multimodal_provider: valueOf("llmMultimodalProvider"),
        default_multimodal_model: valueOf("llmMultimodalModel"),
        temperature: Number(valueOf("llmTemperature")),
        max_tokens: Number.parseInt(valueOf("llmMaxTokens"), 10),
        energy_threshold_fast: Number(valueOf("llmEnergyThreshold")),
        complexity_threshold_deep: Number.parseInt(valueOf("llmComplexityThreshold"), 10),
      };
    }
    if (section === "adoption") {
      const allowed = [];
      if (document.getElementById("anatomyBiped").checked) allowed.push("biped");
      if (document.getElementById("anatomyQuadruped").checked) allowed.push("quadruped");
      const personality = {};
      document.querySelectorAll("[data-personality]").forEach((input) => {
        personality[input.dataset.personality] = input.checked;
      });
      return {
        max_elfies_per_user: Number.parseInt(valueOf("adoptionMaxElfies"), 10),
        allowed_anatomy_types: allowed,
        personality_presets_enabled: personality,
      };
    }
    if (section === "engine") {
      const maxRoomRaw = valueOf("engineMaxElfiesPerRoom");
      return {
        tick_interval_sec: Number(valueOf("engineTickInterval")),
        tts_enabled: document.getElementById("engineTtsEnabled").checked,
        max_elfies_per_room: maxRoomRaw ? Number.parseInt(maxRoomRaw, 10) : null,
        default_tts_voice: valueOf("engineDefaultTtsVoice") || "zh-CN-XiaoxiaoNeural",
      };
    }
    return {
      session_ttl_days: Number.parseInt(valueOf("securitySessionTtl"), 10),
      rate_limit: {
        max_attempts: Number.parseInt(valueOf("securityMaxAttempts"), 10),
        window_seconds: Number.parseInt(valueOf("securityWindowSeconds"), 10),
      },
    };
  }

  function valueOf(id) {
    return document.getElementById(id).value.trim();
  }

  function encodePathId(value) {
    return String(value).split("/").map(encodeURIComponent).join("/");
  }

  function openModal(modal) {
    els.modalBackdrop.hidden = false;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeModals() {
    els.modalBackdrop.hidden = true;
    state.confirmAction = null;
    [els.providerModal, els.userModal, els.confirmModal, els.profileModal, els.passwordModal].forEach((modal) => {
      modal.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
    });
  }

  function openConfirmModal(title, body, onConfirm) {
    document.getElementById("confirmModalTitle").textContent = title;
    document.getElementById("confirmModalBody").textContent = body;
    state.confirmAction = onConfirm;
    openModal(els.confirmModal);
  }

  function openProviderModal(providerId) {
    const provider = providerId ? providerById(providerId) : null;
    state.editingProviderId = provider ? provider.provider_id : null;
    document.getElementById("providerModalTitle").textContent = provider ? "配置供应商" : "添加自定义供应商";
    setValue("providerIdInput", provider ? provider.provider_id : "");
    setValue("providerBaseInput", provider ? provider.api_base : "");
    setValue("providerKeyInput", "");
    setValue("providerModeInput", provider ? provider.api_mode : "chat_completions");
    document.getElementById("providerIdInput").disabled = Boolean(provider);
    document.getElementById("providerModeInput").disabled = false;
    openModal(els.providerModal);
  }

  async function saveProvider() {
    const providerId = valueOf("providerIdInput");
    const apiKey = valueOf("providerKeyInput");
    const body = {
      provider_id: providerId,
      api_base: valueOf("providerBaseInput"),
      api_mode: valueOf("providerModeInput"),
    };
    if (apiKey || !state.editingProviderId) {
      body.api_key = apiKey;
    }
    const isEdit = Boolean(state.editingProviderId);
    if (!providerId) {
      showToast("Provider ID 不能为空", "error");
      return;
    }
    showLoading(true);
    try {
      await apiFetch(isEdit ? `/api/admin/providers/${encodeURIComponent(state.editingProviderId)}` : "/api/admin/providers", {
        method: isEdit ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      state.providers = await apiFetch("/api/admin/providers");
      closeModals();
      renderProviders();
      renderOverview();
      showToast("供应商已保存", "success");
    } catch (error) {
      showToast(`保存失败：${error.message}`, "error");
    } finally {
      showLoading(false);
    }
  }

  async function verifyProvider(providerId) {
    showLoading(true);
    try {
      const result = await apiFetch(`/api/admin/providers/${encodeURIComponent(providerId)}/verify`, { method: "POST" });
      state.providers = await apiFetch("/api/admin/providers");
      renderProviders();
      renderOverview();
      showToast(`验证结果：${statusLabel(result.status)}`, result.status === "active" ? "success" : "warning");
    } catch (error) {
      showToast(`验证失败：${error.message}`, "error");
    } finally {
      showLoading(false);
    }
  }

  async function deleteProvider(providerId) {
    showLoading(true);
    try {
      await apiFetch(`/api/admin/providers/${encodeURIComponent(providerId)}`, { method: "DELETE" });
      state.providers = await apiFetch("/api/admin/providers");
      renderProviders();
      renderOverview();
      showToast("供应商已删除", "success");
    } catch (error) {
      showToast(`删除失败：${error.message}`, "error");
    } finally {
      showLoading(false);
    }
  }

  async function toggleModel(modelId) {
    const model = state.models.find((item) => item.model_id === modelId);
    if (!model) return;
    showLoading(true);
    try {
      await apiFetch(`/api/admin/models/${encodePathId(modelId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ visible: model.visible === false }),
      });
      state.models = await apiFetch("/api/admin/models");
      renderModels();
      renderOverview();
    } catch (error) {
      showToast(`更新模型失败：${error.message}`, "error");
    } finally {
      showLoading(false);
    }
  }

  async function scanModels() {
    showLoading(true);
    try {
      const result = await apiFetch("/api/admin/models/scan", { method: "POST" });
      state.models = await apiFetch("/api/admin/models");
      renderModels();
      renderOverview();
      showToast(`扫描完成，发现 ${result.total || 0} 个新模型`, "success");
    } catch (error) {
      showToast(`扫描失败：${error.message}`, "error");
    } finally {
      showLoading(false);
    }
  }

  function openUserModal(userId) {
    const user = userId ? state.users.find((item) => String(item.id) === String(userId)) : null;
    state.editingUserId = user ? user.id : null;
    document.getElementById("userModalTitle").textContent = user ? "编辑用户" : "创建用户";
    setValue("userNameInput", user ? user.username : "");
    setValue("userPasswordInput", "");
    setValue("userRoleInput", user ? user.role : "user");
    document.getElementById("deleteUserBtn").hidden = !user;
    openModal(els.userModal);
  }

  async function saveUser() {
    const username = valueOf("userNameInput");
    const password = valueOf("userPasswordInput");
    const role = valueOf("userRoleInput");
    if (!username) {
      showToast("用户名不能为空", "error");
      return;
    }
    const body = { username, role };
    if (password) body.password = password;
    if (!state.editingUserId && !password) {
      showToast("新用户需要密码", "error");
      return;
    }
    showLoading(true);
    try {
      await apiFetch(state.editingUserId ? `/api/admin/users/${state.editingUserId}` : "/api/admin/users", {
        method: state.editingUserId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      state.users = await apiFetch("/api/admin/users");
      closeModals();
      renderUsers();
      showToast("用户已保存", "success");
    } catch (error) {
      showToast(`保存失败：${error.message}`, "error");
    } finally {
      showLoading(false);
    }
  }

  async function deleteUser() {
    if (!state.editingUserId) return;
    showLoading(true);
    try {
      await apiFetch(`/api/admin/users/${state.editingUserId}`, { method: "DELETE" });
      state.users = await apiFetch("/api/admin/users");
      closeModals();
      renderUsers();
      showToast("用户已删除", "success");
    } catch (error) {
      showToast(`删除失败：${error.message}`, "error");
    } finally {
      showLoading(false);
    }
  }

  function openProfileModal() {
    const user = state.user || {};
    setValue("profileNicknameInput", user.nickname || user.username || "");
    state.selectedAvatarColor = Number.isInteger(user.avatar_color) ? user.avatar_color : 0;
    renderAvatarColors();
    openModal(els.profileModal);
    document.getElementById("profileNicknameInput").focus();
  }

  function renderAvatarColors() {
    document.getElementById("profileAvatarColors").innerHTML = AVATAR_COLORS.map((color, index) => `
      <button class="avatar-swatch ${index === state.selectedAvatarColor ? "active" : ""}" type="button" data-avatar-color="${index}" style="background:${color}" aria-label="头像颜色 ${index + 1}"></button>
    `).join("");
  }

  async function saveProfile() {
    const nickname = valueOf("profileNicknameInput");
    if (!nickname) {
      showToast("昵称不能为空", "error");
      return;
    }
    showLoading(true);
    try {
      const profile = await apiFetch("/api/auth/me/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nickname,
          avatar_color: state.selectedAvatarColor,
          avatar_kind: "initials",
        }),
      });
      state.user = { ...state.user, ...profile };
      ProfileDropdown.mount(document.getElementById("profileDropdown"), {
        userData: state.user,
        onLogout() {
          localStorage.removeItem("csrf_token");
          localStorage.removeItem("session_token");
        },
      });
      closeModals();
      showToast("资料已保存", "success");
    } catch (error) {
      showToast(`资料保存失败：${error.message}`, "error");
    } finally {
      showLoading(false);
    }
  }

  function openPasswordModal() {
    setValue("passwordUsernameInput", state.user ? state.user.username : "");
    setValue("oldPasswordInput", "");
    setValue("newPasswordInput", "");
    setValue("confirmPasswordInput", "");
    openModal(els.passwordModal);
    document.getElementById("oldPasswordInput").focus();
  }

  async function savePassword() {
    const oldPassword = valueOf("oldPasswordInput");
    const newPassword = valueOf("newPasswordInput");
    const confirmPassword = valueOf("confirmPasswordInput");
    if (!oldPassword || !newPassword || !confirmPassword) {
      showToast("请填写所有密码字段", "error");
      return;
    }
    if (newPassword.length < 6) {
      showToast("新密码至少需要 6 个字符", "error");
      return;
    }
    if (newPassword !== confirmPassword) {
      showToast("两次输入的新密码不一致", "error");
      return;
    }
    showLoading(true);
    try {
      await apiFetch("/api/auth/me/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
      });
      closeModals();
      showToast("密码已更新", "success");
    } catch (error) {
      showToast(`密码修改失败：${error.message}`, "error");
    } finally {
      showLoading(false);
    }
  }

  function applyGlobalSearch() {
    const term = els.globalSearch.value.trim().toLowerCase();
    document.querySelectorAll(".provider-card, .elfie-card, .command-card, .table-row:not(.table-head)").forEach((node) => {
      node.hidden = Boolean(term) && !node.textContent.toLowerCase().includes(term);
    });
  }

  function bindEvents() {
    els.nav.addEventListener("click", (event) => {
      const button = event.target.closest("[data-panel]");
      if (button) setPanel(button.dataset.panel);
    });

    document.addEventListener("click", (event) => {
      const jump = event.target.closest("[data-panel-jump]");
      if (jump) setPanel(jump.dataset.panelJump);

      const copy = event.target.closest("[data-copy]");
      if (copy) copyText(copy.dataset.copy);

      const close = event.target.closest("[data-close-modal]");
      if (close) closeModals();

      const action = event.target.closest("[data-action]");
      if (!action) return;
      const kind = action.dataset.action;
      if (kind === "edit-provider") openProviderModal(action.dataset.providerId);
      if (kind === "verify-provider") verifyProvider(action.dataset.providerId);
      if (kind === "delete-provider") {
        openConfirmModal("删除 Provider", `删除 Provider ${action.dataset.providerId}？已保存的 API Base 和密钥会从本地配置移除。`, () => deleteProvider(action.dataset.providerId));
      }
      if (kind === "toggle-model") toggleModel(action.dataset.modelId);
      if (kind === "edit-user") openUserModal(action.dataset.userId);
    });

    els.modalBackdrop.addEventListener("click", closeModals);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeModals();
    });

    els.refreshAllBtn.addEventListener("click", loadAllData);
    els.addProviderBtn.addEventListener("click", () => openProviderModal(null));
    document.getElementById("providerForm").addEventListener("submit", (event) => {
      event.preventDefault();
      saveProvider();
    });
    document.getElementById("confirmModalBtn").addEventListener("click", () => {
      const action = state.confirmAction;
      closeModals();
      if (action) action();
    });
    els.scanModelsBtn.addEventListener("click", scanModels);
    els.modelProviderFilter.addEventListener("change", renderModels);
    els.modelVisibleFilter.addEventListener("change", renderModels);
    els.saveActiveSystemBtn.addEventListener("click", () => saveSystemSection(state.activeSystemTab));
    els.newUserBtn.addEventListener("click", () => openUserModal(null));
    document.getElementById("userForm").addEventListener("submit", (event) => {
      event.preventDefault();
      saveUser();
    });
    document.getElementById("deleteUserBtn").addEventListener("click", () => {
      openConfirmModal("删除用户", "删除该用户及其精灵登记记录？精灵配置目录会保留以便恢复。", deleteUser);
    });
    document.getElementById("profileForm").addEventListener("submit", (event) => {
      event.preventDefault();
      saveProfile();
    });
    document.getElementById("passwordForm").addEventListener("submit", (event) => {
      event.preventDefault();
      savePassword();
    });
    document.getElementById("copyRestartHintBtn").addEventListener("click", () => copyText("python scripts/elfie.py restart"));
    els.saveSetupRoomBtn.addEventListener("click", async () => {
      const raw = els.setupRoomLimit.value.trim();
      document.getElementById("engineMaxElfiesPerRoom").value = raw;
      await saveSystemSection("engine");
    });

    document.querySelectorAll("[data-system-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        state.activeSystemTab = button.dataset.systemTab;
        document.querySelectorAll("[data-system-tab]").forEach((item) => {
          item.classList.toggle("active", item.dataset.systemTab === state.activeSystemTab);
        });
        document.querySelectorAll("[data-system-panel]").forEach((panel) => {
          panel.classList.toggle("active", panel.dataset.systemPanel === state.activeSystemTab);
        });
      });
    });

    els.globalSearch.addEventListener("input", applyGlobalSearch);

    document.getElementById("profileAvatarColors").addEventListener("click", (event) => {
      const swatch = event.target.closest("[data-avatar-color]");
      if (!swatch) return;
      state.selectedAvatarColor = Number.parseInt(swatch.dataset.avatarColor, 10);
      renderAvatarColors();
    });

    document.getElementById("profileDropdown").addEventListener("profile-dropdown:change-password", () => {
      openPasswordModal();
    });
    document.getElementById("profileDropdown").addEventListener("profile-dropdown:edit-profile", () => {
      openProfileModal();
    });
  }

  bindEvents();
  loadAllData();
})();
