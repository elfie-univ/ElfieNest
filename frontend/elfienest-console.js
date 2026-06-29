const currentUser = "林澈";

const elves = [
  {
    id: "mika",
    name: "米卡",
    owner: "林澈",
    status: "online",
    statusLabel: "在线",
    model: "Ollama · qwen3.5:0.8b",
    role: "家庭提醒与日程陪伴",
    energy: 82,
    mood: "好奇",
    room: "潮馆主房间",
    bed: "床位 A",
  },
  {
    id: "nora",
    name: "诺拉",
    owner: "林澈",
    status: "resting",
    statusLabel: "休眠",
    model: "DeepSeek · 中文任务",
    role: "学习资料整理",
    energy: 54,
    mood: "专注",
    room: "潮馆主房间",
    bed: "床位 B",
  },
  {
    id: "lan",
    name: "岚岚",
    owner: "林澈",
    status: "setup",
    statusLabel: "未配置",
    model: "待配置",
    role: "新领养精灵",
    energy: 0,
    mood: "待激活",
    room: "未分配",
    bed: "未分配",
  },
  {
    id: "bai",
    name: "白栖",
    owner: "周予安",
    status: "online",
    statusLabel: "在线",
    model: "OpenAI · 高复杂度推理",
    role: "写作和对话伙伴",
    energy: 77,
    mood: "平静",
    room: "潮馆主房间",
    bed: "床位 D",
  },
  {
    id: "qiao",
    name: "乔木",
    owner: "周予安",
    status: "resting",
    statusLabel: "休眠",
    model: "Ollama · qwen3.5:0.8b",
    role: "家务清单提醒",
    energy: 43,
    mood: "安静",
    room: "潮馆主房间",
    bed: "床位 E",
  },
  {
    id: "rhea",
    name: "瑞娅",
    owner: "沈听",
    status: "online",
    statusLabel: "在线",
    model: "Qwen · 轻量推理",
    role: "实验室任务观察",
    energy: 69,
    mood: "警觉",
    room: "未分配",
    bed: "未分配",
  },
];

let role = "admin";
let activeView = "overview";
let previousView = "overview";
let wizardStep = 0;

const shell = document.querySelector(".app-shell");
const pageTitle = document.querySelector("#page-title");
const profileRole = document.querySelector("#profile-role");
const elvesCopy = document.querySelector("#elves-copy");
const elfGrid = document.querySelector("#elf-grid");
const scopeFilter = document.querySelector("#scope-filter");
const ownerFilter = document.querySelector("#owner-filter");
const statusFilter = document.querySelector("#status-filter");
const roomFilter = document.querySelector("#room-filter");
const backdrop = document.querySelector(".drawer-backdrop");
const adoptionDrawer = document.querySelector("#adoption-drawer");
const profileDrawer = document.querySelector("#profile-drawer");
const profileMenu = document.querySelector("#profile-menu");
const alertsMenu = document.querySelector("#alerts-menu");
const detailContent = document.querySelector("#elf-detail-content");
const detailHeading = document.querySelector("#elf-detail-heading");

function statusClass(status) {
  if (status === "online") return "success";
  if (status === "setup") return "warning";
  return "info";
}

function isOwned(elf) {
  return elf.owner === currentUser;
}

function visibleElves() {
  let list = elves.slice();

  if (role === "user") {
    list = list.filter(isOwned);
  } else if (scopeFilter.value === "mine") {
    list = list.filter(isOwned);
  } else if (scopeFilter.value === "others") {
    list = list.filter((elf) => !isOwned(elf));
  }

  if (role === "admin" && ownerFilter.value !== "all") {
    list = list.filter((elf) => elf.owner === ownerFilter.value);
  }

  if (statusFilter.value !== "all") {
    list = list.filter((elf) => elf.status === statusFilter.value);
  }

  if (roomFilter.value === "dorm") {
    list = list.filter((elf) => elf.room === "潮馆主房间");
  } else if (roomFilter.value === "none") {
    list = list.filter((elf) => elf.room === "未分配");
  }

  return list;
}

function renderElves() {
  if (!elfGrid) return;
  const list = visibleElves();
  document.querySelector("#metric-active").textContent = String(
    elves.filter((elf) => elf.status === "online").length,
  );

  if (list.length === 0) {
    elfGrid.innerHTML = `
      <article class="drawer-section">
        <h3>没有匹配的精灵</h3>
        <p>调整过滤条件，或从“领养新精灵”开始创建一个新的 Agent。</p>
      </article>
    `;
    return;
  }

  elfGrid.innerHTML = list
    .map((elf) => {
      const owned = isOwned(elf);
      const cardClass = `${owned ? "own" : "other"} ${elf.status === "setup" ? "review" : ""}`;
      const ownerTag = owned
        ? `<span class="tag own">我的精灵</span>`
        : `<span class="tag admin">归属：${elf.owner}</span>`;
      const action = owned
        ? `<button class="ghost-button" type="button" data-open-elf="${elf.id}">进入详情</button>`
        : `<span class="privacy-note">仅基础信息</span>`;

      return `
        <article class="elf-card ${cardClass}">
          <div class="elf-top">
            <div class="elf-avatar" aria-hidden="true"></div>
            <mark class="status ${statusClass(elf.status)}">${elf.statusLabel}</mark>
          </div>
          <div>
            <h3>${elf.name}</h3>
            <p>${elf.role}</p>
          </div>
          <div class="tag-row">
            ${ownerTag}
            <span class="tag">${elf.model}</span>
            <span class="tag">${elf.bed}</span>
          </div>
          <div class="metric-mini-row">
            <div class="metric-mini"><span>能量</span><strong>${elf.energy}%</strong></div>
            <div class="metric-mini"><span>情绪</span><strong>${elf.mood}</strong></div>
          </div>
          <div class="elf-actions">
            <span class="privacy-note">${elf.room}</span>
            ${action}
          </div>
        </article>
      `;
    })
    .join("");
}

function setRole(nextRole) {
  role = nextRole;
  shell.dataset.role = role;
  profileRole.textContent = role === "admin" ? "管理员" : "普通用户";
  elvesCopy.textContent =
    role === "admin"
      ? "管理员可看全部精灵卡片；只有拥有者能进入详情、配置和聊天。"
      : "这里只显示你的精灵，可直接领养并进入详情。";

  setView(role === "admin" ? "overview" : "elves");
  renderElves();
}

function setView(view) {
  previousView = activeView === "elf-detail" ? previousView : activeView;
  activeView = view;
  const titles = {
    overview: "综合监控",
    elves: "精灵管理",
    "elf-detail": "精灵详情",
    rooms: "房间管理",
    users: "用户管理",
    config: "系统配置",
  };
  pageTitle.textContent = titles[view] || "";

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.viewPanel === view);
  });
}

function openDrawer(drawer) {
  closeMenus();
  closeDrawers();
  backdrop.hidden = false;
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
}

function closeDrawers() {
  backdrop.hidden = true;
  document.querySelectorAll(".drawer").forEach((drawer) => {
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
  });
}

function togglePopover(popover, anchor) {
  const wasHidden = popover.hidden;
  closeMenus();
  if (!wasHidden) return;
  const rect = anchor.getBoundingClientRect();
  popover.hidden = false;
  popover.style.top = `${rect.bottom + 8}px`;
  popover.style.right = `${window.innerWidth - rect.right}px`;
}

function closeMenus() {
  profileMenu.hidden = true;
  alertsMenu.hidden = true;
}

function renderElfDetail(id) {
  const elf = elves.find((item) => item.id === id);
  if (!elf || !isOwned(elf)) return;

  detailHeading.textContent = `精灵详情：${elf.name}`;
  detailContent.innerHTML = `
    <div class="elf-detail-layout">
      <section class="config-card detail-config">
        <div class="elf-detail-head">
          <div class="elf-avatar large" aria-hidden="true"></div>
          <div>
            <h3>${elf.name}</h3>
            <p>${elf.model}</p>
          </div>
        </div>
        <label class="form-row">
          <span>精灵名称</span>
          <input type="text" value="${elf.name}" />
        </label>
        <label class="form-row">
          <span>挂载大模型</span>
          <select>
            <option>${elf.model}</option>
            <option>Ollama · qwen3.5:0.8b</option>
            <option>OpenAI · 高复杂度推理</option>
            <option>DeepSeek · 中文任务</option>
          </select>
        </label>
        <label class="form-row">
          <span>人格设定</span>
          <textarea rows="5">你是一个名为 ${elf.name} 的精灵。你的定位是：${elf.role}。</textarea>
        </label>
        <label class="form-row">
          <span>所在房间</span>
          <input type="text" value="${elf.room} · ${elf.bed}" readonly />
        </label>
        <div class="metric-mini-row">
          <div class="metric-mini"><span>能量</span><strong>${elf.energy}%</strong></div>
          <div class="metric-mini"><span>情绪</span><strong>${elf.mood}</strong></div>
        </div>
      </section>

      <section class="chat-panel">
        <div class="chat-toolbar">
          <div>
            <h3>主人聊天记录</h3>
            <p>只显示你和 ${elf.name} 的聊天；其他用户、精灵间对话和系统内部记录不在这里展示。</p>
          </div>
          <div class="chat-filters">
            <select>
              <option>全部时间</option>
              <option>今天</option>
              <option>最近 7 天</option>
              <option>最近 30 天</option>
            </select>
            <input type="search" placeholder="搜索聊天内容" />
          </div>
        </div>
        <div class="chat-history" aria-label="主人聊天历史">
          <div class="history-divider">今天 09:18</div>
          <div class="chat-bubble user">今天家里的电脑还在线吗？</div>
          <div class="chat-bubble">在线。WebSocket 服务连接正常，最近一次心跳在 09:18。</div>
          <div class="chat-bubble user">帮我记一下晚上检查模型配置。</div>
          <div class="chat-bubble">已记录。我会在晚间例行检查前提醒你。</div>
          <div class="history-divider">昨天 22:40</div>
          <div class="chat-bubble user">你今天在房间里做什么？</div>
          <div class="chat-bubble">我主要在床位附近待机，偶尔去书桌互动点观察任务清单。</div>
        </div>
        <div class="chat-input-row">
          <input type="text" placeholder="和 ${elf.name} 说点什么..." />
          <button class="primary-button" type="button">发送</button>
        </div>
      </section>
    </div>
  `;
  setView("elf-detail");
}

function setWizardStep(step) {
  wizardStep = Math.max(0, Math.min(2, step));
  document.querySelectorAll(".wizard-step").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.step) === wizardStep);
  });
  document.querySelectorAll(".wizard-panel").forEach((panel) => {
    panel.classList.toggle("active", Number(panel.dataset.wizardPanel) === wizardStep);
  });
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("button, [data-close-drawer]");
  if (!target) {
    if (!event.target.closest(".popover")) closeMenus();
    return;
  }

  if (target.matches("[data-view]")) {
    if (role === "user" && target.dataset.view !== "elves") return;
    setView(target.dataset.view);
  }

  if (target.matches("[data-open-elf]")) {
    renderElfDetail(target.dataset.openElf);
  }

  if (target.matches("[data-back-to-elves]")) {
    setView("elves");
  }

  if (target.matches("[data-open-adoption]")) {
    setWizardStep(0);
    openDrawer(adoptionDrawer);
  }

  if (target.matches("[data-open-profile-menu]")) {
    togglePopover(profileMenu, target);
  }

  if (target.matches("[data-open-alerts]")) {
    togglePopover(alertsMenu, target);
  }

  if (target.matches("[data-open-profile]")) {
    openDrawer(profileDrawer);
  }

  if (target.matches("[data-close-drawer]")) {
    closeDrawers();
  }

  if (target.matches("[data-step]")) {
    setWizardStep(Number(target.dataset.step));
  }

  if (target.matches("[data-next-step]")) {
    setWizardStep(wizardStep + 1);
  }

  if (target.matches("[data-prev-step]")) {
    setWizardStep(wizardStep - 1);
  }

  if (target.matches("[data-config-tab]")) {
    const tab = target.dataset.configTab;
    document.querySelectorAll("[data-config-tab]").forEach((button) => {
      button.classList.toggle("active", button.dataset.configTab === tab);
    });
    document.querySelectorAll("[data-config-panel]").forEach((panel) => {
      panel.classList.toggle("active", panel.dataset.configPanel === tab);
    });
  }

  if (target.matches(".option-card")) {
    const group = target.parentElement;
    group.querySelectorAll(".option-card").forEach((button) => button.classList.remove("active"));
    target.classList.add("active");
  }
});

function syncFiltersFromOwner() {
  if (ownerFilter.value !== "all") {
    scopeFilter.value = ownerFilter.value === currentUser ? "mine" : "others";
  }
  renderElves();
}

scopeFilter.addEventListener("change", () => {
  if (scopeFilter.value === "mine") ownerFilter.value = currentUser;
  if (scopeFilter.value === "all") ownerFilter.value = "all";
  renderElves();
});
ownerFilter.addEventListener("change", syncFiltersFromOwner);
statusFilter.addEventListener("change", renderElves);
roomFilter.addEventListener("change", renderElves);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeDrawers();
    closeMenus();
  }
});

function applyInitialRoute() {
  const params = new URLSearchParams(window.location.search);
  const initialRole = params.get("role") === "user" ? "user" : "admin";
  setRole(initialRole);

  const route = window.location.hash.replace("#", "");
  if (!route) return;

  if (["overview", "elves", "rooms", "users", "config"].includes(route)) {
    if (initialRole === "user" && route !== "elves") return;
    setView(route);
    return;
  }

  if (route.startsWith("elf-")) {
    renderElfDetail(route.replace("elf-", ""));
  }
}

applyInitialRoute();
