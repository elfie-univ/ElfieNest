const state = {
  elfies: [],
  currentId: null,
  session: null,
  selectedTurn: null,
  selectedFocus: "summary",
  detailTab: "summary",
  sending: false,
  foods: [],
  configurationCommand: "",
  previewReady: false,
};

const el = (id) => document.getElementById(id);
const ui = {
  shell: el("labShell"), elfieEmpty: el("elfieEmpty"), elfieContent: el("elfieContent"),
  switcherWrap: el("switcherWrap"), elfieMenu: el("elfieMenu"), switcher: el("elfieSwitcher"),
  timeline: el("timeline"), placeholder: el("timelinePlaceholder"), composer: el("composer"),
  message: el("messageInput"), send: el("sendButton"), detail: el("detailPanel"),
  detailContent: el("detailContent"), modal: el("createModal"), createForm: el("createForm"),
  toast: el("toast"), stimulusDrawer: el("stimulusDrawer"), stimulusToggle: el("stimulusToggle"),
  elfieError: el("elfieError"),
};

const emotionLabels = { happiness: "快乐", sadness: "悲伤", fear: "恐惧", anger: "愤怒", surprise: "惊讶", disgust: "厌恶", boredom: "无聊", jealousy: "嫉妒", calm: "平静" };

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `请求失败 (${response.status})`);
  return payload;
}

async function boot() {
  bindEvents();
  try {
    const [data, foodsData] = await Promise.all([api("/api/elfies"), api("/api/runtime/foods")]);
    state.foods = foodsData.items || [];
    state.configurationCommand = foodsData.configuration_command || "";
    populateFoodSelect();
    updateModelHint();
    state.elfies = data.items || [];
    if (!state.elfies.length) return showEmpty();
    const remembered = localStorage.getItem("elfieLab.currentElfie");
    const first = state.elfies.find((item) => item.elfie_id === remembered) || state.elfies[0];
    await selectElfie(first.elfie_id);
  } catch (error) {
    const errorMessage = error.message.toLowerCase();
    if (error.message.includes("503") ||
        errorMessage.includes("粮食") ||
        errorMessage.includes("food")) {
      showError();
      return;
    }
    showToast(error.message, true);
  }
}

function bindEvents() {
  el("emptyCreate").addEventListener("click", openCreate);
  el("createClose").addEventListener("click", closeCreate);
  el("createCancel").addEventListener("click", closeCreate);
  if (el("errorReload")) {
    el("errorReload").addEventListener("click", () => window.location.reload());
  }
  ui.modal.addEventListener("click", (event) => { if (event.target === ui.modal) closeCreate(); });
  ui.createForm.addEventListener("submit", createElfie);
  ui.switcher.addEventListener("click", toggleElfieMenu);
  el("leftCollapse").addEventListener("click", () => ui.shell.classList.toggle("left-closed"));
  el("detailClose").addEventListener("click", closeDetail);
  document.querySelectorAll(".detail-tabs button").forEach((button) => button.addEventListener("click", () => {
    state.detailTab = button.dataset.tab;
    document.querySelectorAll(".detail-tabs button").forEach((item) => item.classList.toggle("active", item === button));
    renderDetail();
  }));
  ui.stimulusToggle.addEventListener("click", () => {
    const open = ui.stimulusDrawer.hidden;
    ui.stimulusDrawer.hidden = !open;
    ui.stimulusToggle.classList.toggle("active", open);
    ui.stimulusToggle.setAttribute("aria-expanded", String(open));
    updateChannelHint();
  });
  el("salienceInput").addEventListener("input", (event) => { el("salienceOutput").value = event.target.value; updateChannelHint(); });
  ["impactInput", "strokeInput", "injectEnergy", "injectFatigue"].forEach((id) => el(id).addEventListener("input", updateChannelHint));
  el("foodSelect").addEventListener("change", updateModelHint);
  ui.composer.addEventListener("submit", sendTurn);
  ui.message.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); ui.composer.requestSubmit(); }
  });
  ui.message.addEventListener("input", autoGrow);
  document.addEventListener("click", (event) => {
    if (!ui.switcherWrap.contains(event.target)) closeElfieMenu();
  });
  window.addEventListener("message", handlePreviewMessage);
  el("appearanceFrame").addEventListener("load", () => {
    state.previewReady = false;
    window.setTimeout(syncAppearancePreview, 800);
  });
  el("previewRotateLeft").addEventListener("click", () => sendPreview("rotate", { delta: -0.28 }));
  el("previewRotateRight").addEventListener("click", () => sendPreview("rotate", { delta: 0.28 }));
  el("previewZoomOut").addEventListener("click", () => sendPreview("zoom", { delta: 0.18 }));
  el("previewZoomIn").addEventListener("click", () => sendPreview("zoom", { delta: -0.18 }));
  el("previewReset").addEventListener("click", () => sendPreview("reset"));
  el("previewCapture").addEventListener("click", () => sendPreview("capture"));
}

function showEmpty() {
  ui.elfieEmpty.hidden = false; ui.elfieContent.hidden = true; ui.switcherWrap.hidden = true;
  ui.message.disabled = true; ui.send.disabled = true;
}

function showError() {
  ui.elfieError.hidden = false;
  ui.elfieEmpty.hidden = true;
  ui.elfieContent.hidden = true;
  ui.switcherWrap.hidden = true;
}

async function selectElfie(id) {
  closeElfieMenu();
  const session = await api(`/api/elfies/${encodeURIComponent(id)}`);
  state.currentId = id; state.session = session; state.selectedTurn = null;
  localStorage.setItem("elfieLab.currentElfie", id);
  ui.elfieEmpty.hidden = true; ui.elfieContent.hidden = false; ui.switcherWrap.hidden = false;
  ui.elfieError.hidden = true;
  ui.message.disabled = false; ui.send.disabled = false;
  ensurePreviewFrame();
  renderProfile(); renderTimeline(); closeDetail();
}

function renderProfile() {
  const profile = state.session.profile; const current = state.session.current_state;
  const glyph = profile.name.trim().slice(0, 1) || "艾";
  el("avatarGlyph").textContent = glyph; el("miniAvatar").textContent = glyph;
  el("elfieName").textContent = profile.name; el("switcherName").textContent = profile.name;
  el("elfieDescription").textContent = profile.description || profile.personality_summary;
  el("speciesLabel").textContent = profile.species_label || profile.species_id;
  el("lifeStage").textContent = profile.life_stage || "青年";
  el("elfieId").textContent = profile.elfie_id;
  el("wakeStatus").textContent = current.is_sleeping ? "睡眠中" : "清醒";
  el("dominantEmotion").textContent = emotionLabels[current.dominant_emotion] || current.dominant_emotion;
  el("memoryCount").textContent = current.memory_count;
  const avatar = el("avatarImage");
  avatar.hidden = !profile.portrait_url;
  el("avatarGlyph").hidden = Boolean(profile.portrait_url);
  if (profile.portrait_url) avatar.src = `${profile.portrait_url}?v=${Date.now()}`;
  renderPersonalityRadar(profile.big_five || {});
  renderPersonalityTags(profile.personality_tags || []);
  renderStateMetrics(current);
  renderMemoryCognition(profile.memory_cognition || {});
  syncAppearancePreview();
  updateModelHint();
  renderElfieMenu();
}

function ensurePreviewFrame() {
  const frame = el("appearanceFrame");
  if (frame.src === "about:blank" || !frame.src.includes("/godot-web/")) {
    frame.src = "/godot-web/elfienest.html?mode=elfie_lab";
  }
}

function sendPreview(action, payload = {}) {
  const target = el("appearanceFrame").contentWindow;
  if (!target) return;
  target.postMessage(
    JSON.stringify({ channel: "elfie-lab", action, ...payload }),
    window.location.origin,
  );
}

function syncAppearancePreview() {
  if (!state.session) return;
  const profile = state.session.profile;
  sendPreview("configure", {
    elfie_id: profile.elfie_id,
    species_id: profile.species_id,
    appearance: profile.appearance || {},
  });
}

async function handlePreviewMessage(event) {
  if (
    event.origin !== window.location.origin
    || event.source !== el("appearanceFrame").contentWindow
  ) return;
  let message = event.data;
  if (typeof message === "string") {
    if (message === "elfienest:godot-web-ready") {
      syncAppearancePreview();
      return;
    }
    try { message = JSON.parse(message); } catch { return; }
  }
  if (message?.channel !== "elfie-lab") return;
  if (message.event === "ready") {
    state.previewReady = true;
    el("appearanceLoading").hidden = true;
    el("appearanceStatus").textContent = "idle · 可交互";
    syncAppearancePreview();
  }
  if (message.event === "portrait" && message.data_url) {
    try {
      const result = await api(
        `/api/elfies/${encodeURIComponent(state.currentId)}/portrait`,
        { method: "PUT", body: JSON.stringify({ data_url: message.data_url }) },
      );
      state.session.profile.portrait_url = result.portrait_url;
      renderProfile();
      showToast("头像已保存");
    } catch (error) { showToast(error.message, true); }
  }
}

function renderPersonalityRadar(values) {
  const svg = el("personalityRadar");
  const axes = [
    ["开放", "openness"],
    ["尽责", "conscientiousness"],
    ["外向", "extraversion"],
    ["亲和", "agreeableness"],
    ["敏感", "neuroticism"],
  ];
  const center = [105, 82];
  const radius = 58;
  const point = (index, scale) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / axes.length;
    return [
      center[0] + Math.cos(angle) * radius * scale,
      center[1] + Math.sin(angle) * radius * scale,
    ];
  };
  svg.replaceChildren();
  [0.25, 0.5, 0.75, 1].forEach((scale) => appendSvg(svg, "polygon", {
    points: axes.map((_, index) => point(index, scale).join(",")).join(" "),
    class: "radar-grid",
  }));
  axes.forEach(([label], index) => {
    const edge = point(index, 1);
    const textPoint = point(index, 1.28);
    appendSvg(svg, "line", {
      x1: center[0], y1: center[1], x2: edge[0], y2: edge[1], class: "radar-axis",
    });
    const text = appendSvg(svg, "text", {
      x: textPoint[0], y: textPoint[1], class: "radar-label", "text-anchor": "middle",
    });
    text.textContent = label;
  });
  const profilePoints = axes.map(([, key], index) => point(
    index,
    Math.max(0, Math.min(1, Number(values[key] ?? 0.5))),
  ));
  appendSvg(svg, "polygon", {
    points: profilePoints.map((item) => item.join(",")).join(" "), class: "radar-profile",
  });
  profilePoints.forEach(([x, y]) => appendSvg(svg, "circle", {
    cx: x, cy: y, r: 3, class: "radar-point",
  }));
}

function renderPersonalityTags(tags) {
  el("personalityTags").replaceChildren(...tags.slice(0, 3).map((label) => {
    const span = document.createElement("span");
    span.textContent = label;
    return span;
  }));
}

function renderStateMetrics(current) {
  const emotionValues = Object.values(current.emotions || { calm: 0 }).map(Number);
  const metrics = [
    ["能量", current.energy, "energy"],
    ["疲劳", current.fatigue, "fatigue"],
    ["注意力", current.attention_network === "CEN" ? 78 : 42, "attention"],
    ["情绪强度", Math.max(...emotionValues), "emotion"],
  ];
  el("stateMetrics").replaceChildren(...metrics.map(([label, raw, kind]) => {
    const value = Math.max(0, Math.min(100, Number(raw || 0)));
    const row = document.createElement("div");
    row.className = `state-metric ${kind}`;
    const labelNode = document.createElement("span"); labelNode.textContent = label;
    const track = document.createElement("i");
    const bar = document.createElement("b"); bar.style.width = `${value}%`; track.append(bar);
    const output = document.createElement("strong"); output.textContent = String(Math.round(value));
    row.append(labelNode, track, output);
    return row;
  }));
}

function renderMemoryCognition(memory) {
  renderTopicCloud(memory.topics || []);
  renderImportantEvents(memory.important_events || []);
  renderGraph(el("relationGraph"), memory.relations || {}, true);
  renderGraph(el("knowledgeGraph"), memory.knowledge || {}, false);
  el("worldUnderstanding").textContent = (
    memory.world_understanding || "尚未形成稳定的世界理解"
  );
}

function renderTopicCloud(topics) {
  const max = Math.max(1, ...topics.map((item) => Number(item.weight || 1)));
  const nodes = topics.map((item, index) => {
    const span = document.createElement("span");
    span.textContent = item.label;
    span.style.fontSize = `${10 + 8 * Number(item.weight || 1) / max}px`;
    span.className = `topic-${index % 4}`;
    return span;
  });
  if (!nodes.length) {
    const empty = document.createElement("small");
    empty.textContent = "互动后将在这里形成记忆主题";
    nodes.push(empty);
  }
  el("topicCloud").replaceChildren(...nodes);
}

function renderImportantEvents(events) {
  const nodes = events.map((event) => {
    const article = document.createElement("article");
    const time = document.createElement("time");
    time.textContent = event.timestamp
      ? new Date(event.timestamp).toLocaleDateString("zh-CN")
      : "未标记日期";
    const copy = document.createElement("p"); copy.textContent = event.content;
    article.append(time, copy);
    return article;
  });
  if (!nodes.length) {
    const empty = document.createElement("p");
    empty.className = "projection-empty";
    empty.textContent = "尚无重要经历";
    nodes.push(empty);
  }
  el("importantEvents").replaceChildren(...nodes);
}

function renderGraph(svg, graph, relations) {
  const nodes = (graph.nodes || []).slice(0, relations ? 9 : 12);
  const links = graph.links || [];
  svg.replaceChildren();
  if (!nodes.length || (relations && nodes.length === 1)) {
    const text = appendSvg(svg, "text", {
      x: 170, y: 108, class: "graph-empty", "text-anchor": "middle",
    });
    text.textContent = relations ? "互动后将形成关系网络" : "尚未沉淀知识与信念";
    return;
  }
  const positions = new Map();
  nodes.forEach((node, index) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / nodes.length;
    const centerNode = relations && index === 0;
    positions.set(node.id, centerNode
      ? [170, 105]
      : [170 + Math.cos(angle) * 112, 105 + Math.sin(angle) * 72]);
  });
  links.forEach((link) => {
    const from = positions.get(link.source); const to = positions.get(link.target);
    if (from && to) appendSvg(svg, "line", {
      x1: from[0], y1: from[1], x2: to[0], y2: to[1], class: "graph-link",
    });
  });
  if (relations) nodes.slice(1).forEach((node) => {
    if (!links.some((link) => link.source === node.id || link.target === node.id)) {
      const from = positions.get(nodes[0].id); const to = positions.get(node.id);
      appendSvg(svg, "line", {
        x1: from[0], y1: from[1], x2: to[0], y2: to[1], class: "graph-link muted",
      });
    }
  });
  nodes.forEach((node, index) => {
    const [x, y] = positions.get(node.id);
    const centerNode = relations && index === 0;
    appendSvg(svg, "circle", {
      cx: x,
      cy: y,
      r: centerNode ? 24 : 15 + Math.min(7, Number(node.weight || 0.4) * 7),
      class: centerNode ? "graph-node self" : "graph-node",
    });
    const text = appendSvg(svg, "text", {
      x, y: y + (centerNode ? 34 : 29), class: "graph-label", "text-anchor": "middle",
    });
    text.textContent = String(node.label || "").slice(0, 10);
  });
}

function appendSvg(parent, tag, attrs) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  parent.append(node);
  return node;
}

function populateFoodSelect(preferredKey = null) {
  const select = el("foodSelect");
  const desiredValue = preferredKey || localStorage.getItem("elfieLab.foodKey") || select.value;
  select.replaceChildren();
  state.foods.forEach((food) => {
    const option = document.createElement("option");
    option.value = food.key;
    option.disabled = food.key !== "mock" && !food.ready_for_attempt;
    const statusMark = !food.ready_for_attempt
      ? " · 未就绪"
      : !food.primary_ready && food.fallback_ready
        ? " · 可降级"
        : "";
    option.textContent = `${food.display_name}${statusMark}`;
    select.append(option);
  });
  const desiredFood = state.foods.find((food) => food.key === desiredValue && food.ready_for_attempt);
  const fallbackFood = state.foods.find((food) => food.ready_for_attempt);
  select.value = (desiredFood || fallbackFood)?.key || "";
  localStorage.setItem("elfieLab.foodKey", select.value);
  renderFoodSetupList();
}

function updateModelHint() {
  const hint = el("modelHint");
  hint.classList.remove("is-ready", "is-error");
  const selectedKey = el("foodSelect").value;
  const food = state.foods.find((f) => f.key === selectedKey);
  if (!food) { hint.textContent = "没有已就绪的粮食"; hint.classList.add("is-error"); return; }
  localStorage.setItem("elfieLab.foodKey", selectedKey);
  if (food.key === "mock") {
    hint.textContent = "elfie-mock · 不调用外部服务"; return;
  }
  const readiness = !food.ready_for_attempt
    ? food.unavailable_reason
    : food.primary_ready
    ? "主模型已就绪"
    : food.fallback_ready
      ? "主模型未就绪，将尝试降级模型"
      : "没有可用模型";
  hint.textContent = `${food.model} · ${food.description} · ${readiness}`;
  hint.classList.add(food.ready_for_attempt ? "is-ready" : "is-error");
}

function renderFoodSetupList() {
  const container = el("foodSetupList");
  const commandFoods = new Map();
  const configureCommand = state.configurationCommand;
  state.foods.forEach((food) => {
    (food.setup_commands || []).forEach((command) => {
      if (!commandFoods.has(command)) commandFoods.set(command, []);
      commandFoods.get(command).push(food.display_name);
    });
  });
  container.replaceChildren();
  if (commandFoods.size && configureCommand) appendSetupCommand(container, "完整 Runtime Lab：", configureCommand);
  commandFoods.forEach((names, command) => {
    if (command !== configureCommand) {
      appendSetupCommand(container, `${[...new Set(names)].join("、")}：`, command);
    }
  });
  container.hidden = commandFoods.size === 0;
}

function appendSetupCommand(container, labelText, command) {
  const row = document.createElement("div");
  const label = document.createElement("span"); label.textContent = labelText;
  const code = document.createElement("code"); code.textContent = command;
  row.append(label, code); container.append(row);
}

async function refreshFoods(preferredKey = null) {
  try {
    const data = await api("/api/runtime/foods");
    state.foods = data.items || [];
    state.configurationCommand = data.configuration_command || "";
    populateFoodSelect(preferredKey);
    updateModelHint();
    return true;
  } catch (error) {
    showToast(error.message, true);
    return false;
  }
}

function renderGrid(container, rows) {
  container.replaceChildren(...rows.map(([label, value]) => {
    const box = document.createElement("div"); box.className = "kv";
    const span = document.createElement("span"); span.textContent = label;
    const strong = document.createElement("strong"); strong.textContent = value ?? "—";
    box.append(span, strong); return box;
  }));
}

function renderStack(container, rows) {
  container.replaceChildren(...rows.map(([label, value]) => {
    const box = document.createElement("div"); box.className = "stack-item";
    const title = document.createElement("b"); title.textContent = label;
    const copy = document.createElement("p"); copy.textContent = String(value || "暂无数据");
    box.append(title, copy); return box;
  }));
}

function renderElfieMenu() {
  ui.elfieMenu.replaceChildren();
  state.elfies.forEach((elfie) => {
    const button = document.createElement("button"); button.type = "button"; button.classList.toggle("active", elfie.elfie_id === state.currentId);
    button.textContent = `${elfie.elfie_id === state.currentId ? "✓" : " "}  ${elfie.name}`;
    button.addEventListener("click", () => selectElfie(elfie.elfie_id).catch((error) => showToast(error.message, true)));
    ui.elfieMenu.append(button);
  });
  const rule = document.createElement("hr"); ui.elfieMenu.append(rule);
  const create = document.createElement("button"); create.type = "button"; create.textContent = "＋  新建测试精灵"; create.addEventListener("click", openCreate); ui.elfieMenu.append(create);
}

function toggleElfieMenu() { const open = ui.elfieMenu.hidden; ui.elfieMenu.hidden = !open; ui.switcher.setAttribute("aria-expanded", String(open)); }
function closeElfieMenu() { ui.elfieMenu.hidden = true; ui.switcher.setAttribute("aria-expanded", "false"); }

function renderTimeline() {
  const turns = state.session.turns || []; el("turnCount").textContent = `${turns.length} 轮`;
  ui.timeline.replaceChildren();
  if (!turns.length) { ui.placeholder.hidden = false; ui.timeline.append(ui.placeholder); return; }
  turns.forEach((turn, index) => ui.timeline.append(createTurnNode(turn, index)));
  requestAnimationFrame(() => { ui.timeline.scrollTop = ui.timeline.scrollHeight; });
}

function createTurnNode(turn, index) {
  const wrap = document.createElement("article"); wrap.className = "turn"; wrap.dataset.turnId = turn.turn_id;
  const meta = document.createElement("div"); meta.className = "turn-meta"; meta.textContent = `TURN ${String(index + 1).padStart(2, "0")}  ·  ${formatTime(turn.timestamp)}`;
  const userRow = document.createElement("div"); userRow.className = "bubble-row user";
  const userBubble = bubbleNode("开发者刺激", turn.stimulus_bundle.message || "非文字刺激", turn.used_state_injection ? ["状态注入"] : [], "user");
  userBubble.addEventListener("click", () => openDetail(turn, "input")); userRow.append(userBubble);
  const process = document.createElement("button"); process.type = "button"; process.className = "process-line";
  const attention = turn.trace?.stages?.decision?.attention_mode || "无模型路径";
  process.append(document.createTextNode("感知"), dot(), document.createTextNode(attention), dot(), document.createTextNode(`${turn.duration_ms}ms`));
  process.addEventListener("click", () => openDetail(turn, "chain"));
  const elfieRow = document.createElement("div"); elfieRow.className = "bubble-row elfie";
  const result = turn.result || {}; const tags = [];
  if (result.action) tags.push(result.action); if (turn.state_after?.dominant_emotion) tags.push(emotionLabels[turn.state_after.dominant_emotion] || turn.state_after.dominant_emotion);
  if (turn.state_diff?.energy) tags.push(`能量 ${signed(turn.state_diff.energy.before, turn.state_diff.energy.after)}`);
  const elfieBubble = bubbleNode(state.session.profile.name, result.speech || result.mutter || result.reason || result.error || "本轮无文字输出", tags, result.success === false ? "error" : "elfie");
  elfieBubble.addEventListener("click", () => openDetail(turn, "output")); elfieRow.append(elfieBubble);
  wrap.append(meta, userRow, process, elfieRow); return wrap;
}

function bubbleNode(label, text, tags, kind) {
  const bubble = document.createElement("div"); bubble.className = `bubble ${kind === "error" ? "error" : ""}`;
  const header = document.createElement("div"); header.className = "bubble-label";
  const name = document.createElement("span"); name.textContent = label; header.append(name);
  if (kind === "user") { const channel = document.createElement("span"); channel.className = "channel"; channel.textContent = "文字"; header.append(channel); }
  const copy = document.createElement("p"); copy.textContent = text;
  bubble.append(header, copy);
  if (tags.length) { const row = document.createElement("div"); row.className = "bubble-tags"; tags.forEach((tag) => { const item = document.createElement("span"); item.textContent = tag; if (tag === "状态注入") item.className = "warning"; row.append(item); }); bubble.append(row); }
  return bubble;
}

function dot() { const item = document.createElement("i"); return item; }

async function sendTurn(event) {
  event.preventDefault(); if (!state.currentId || state.sending) return;
  const selectedBeforeRefresh = el("foodSelect").value;
  if (!await refreshFoods(selectedBeforeRefresh)) return;
  const foodKey = el("foodSelect").value;
  const food = state.foods.find((f) => f.key === foodKey);
  if (!food || !food.ready_for_attempt) return showToast(`粮食「${food?.display_name || foodKey}」尚未就绪`, true);
  const message = ui.message.value.trim(); const injection = {};
  if (el("injectEnergy").value !== "") injection.energy = Number(el("injectEnergy").value);
  if (el("injectFatigue").value !== "") injection.fatigue = Number(el("injectFatigue").value);
  const body = { message, food_key: foodKey, temperature: Number(el("temperatureInput").value), salience_score: Number(el("salienceInput").value), impact_force: Number(el("impactInput").value), gentle_stroke: Number(el("strokeInput").value), state_injection: injection };
  if (!message && !body.impact_force && !body.gentle_stroke && !Object.keys(injection).length && body.salience_score < 70) return showToast("请输入消息或添加有效刺激", true);
  setSending(true);
  try {
    const turn = await api(`/api/elfies/${encodeURIComponent(state.currentId)}/turns`, { method: "POST", body: JSON.stringify(body) });
    state.session.turns.push(turn); state.session.current_state = turn.state_after;
    ui.message.value = ""; autoGrow(); clearInjection(); renderProfile(); renderTimeline(); openDetail(turn, "output");
  } catch (error) { showToast(error.message, true); }
  finally { setSending(false); }
}

function setSending(value) { state.sending = value; ui.send.disabled = value || !state.currentId; ui.message.disabled = value || !state.currentId; ui.send.querySelector("span").textContent = value ? "思考中" : "发送"; }
function clearInjection() { el("injectEnergy").value = ""; el("injectFatigue").value = ""; updateChannelHint(); }
function autoGrow() { ui.message.style.height = "auto"; ui.message.style.height = `${Math.min(ui.message.scrollHeight, 140)}px`; }
function updateChannelHint() {
  const tags = ["文字"];
  if (Number(el("impactInput").value) || Number(el("strokeInput").value)) tags.push("触觉");
  if (Number(el("salienceInput").value) !== 20 || Number(el("temperatureInput").value) !== 24) tags.push("环境");
  if (el("injectEnergy").value !== "" || el("injectFatigue").value !== "") tags.push("注入");
  el("channelHint").textContent = tags.map((tag) => `[${tag}]`).join("");
}

function openDetail(turn, focus) {
  state.selectedTurn = turn; state.selectedFocus = focus;
  state.detailTab = focus === "chain" ? "chain" : "summary";
  document.querySelectorAll(".detail-tabs button").forEach((button) => button.classList.toggle("active", button.dataset.tab === state.detailTab));
  ui.shell.classList.add("detail-open"); ui.detail.classList.remove("is-closed"); ui.detail.setAttribute("aria-hidden", "false");
  el("detailKicker").textContent = `历史回合 · ${formatTime(turn.timestamp)} · 只读`;
  el("detailTitle").textContent = focus === "input" ? "输入与感知" : focus === "chain" ? "完整处理链路" : "决策与执行";
  renderDetail();
}

function closeDetail() { ui.shell.classList.remove("detail-open"); ui.detail.classList.add("is-closed"); ui.detail.setAttribute("aria-hidden", "true"); }

function renderDetail() {
  const turn = state.selectedTurn; if (!turn) { ui.detailContent.replaceChildren(); return; }
  ui.detailContent.replaceChildren();
  if (state.detailTab === "summary") renderSummary(turn);
  if (state.detailTab === "chain") renderChain(turn);
  if (state.detailTab === "snapshot") renderSnapshot(turn);
  if (state.detailTab === "raw") renderRaw(turn);
}

function renderSummary(turn) {
  const stimulus = detailSection("本轮输入"); stimulus.append(detailCard("开发者刺激", turn.stimulus_bundle.message || "非文字刺激", turn.food_key || "mock"));
  if (turn.used_state_injection) stimulus.append(detailCard("状态注入", JSON.stringify(turn.stimulus_bundle.state_injection, null, 2), "已永久标记"));
  const foodUsed = turn.model_call?.food_used;
  const foodLabel = foodUsed && foodUsed !== turn.food_key ? `${turn.food_key} → ${foodUsed}` : (turn.food_key || "—");
  const result = detailSection("精灵结果"); result.append(detailList({ "回复": turn.result.speech || turn.result.mutter || turn.result.reason || "—", "动作": turn.result.action || "—", "注意力": turn.trace?.stages?.decision?.attention_mode || "未进入皮层决策", "粮食": foodLabel, "模型": turn.model_call?.model || "未调用", "总耗时": `${turn.duration_ms} ms`, "状态": turn.error ? turn.error : (turn.result.success === false ? "未完成" : "已完成") }));
  ui.detailContent.append(stimulus, result);
}

function renderChain(turn) {
  const stages = turn.trace?.stages || {}; const section = detailSection("执行阶段");
  const labels = { state_injection: "状态注入", sleep_gate: "睡眠门控", brainstem_reflex: "脑干反射", sensory_filter: "感知过滤", thalamus_context: "丘脑上下文", decision: "注意力与决策", action_validation: "动作校验", execution: "身体执行", memory_write: "记忆写入" };
  Object.entries(stages).forEach(([key, value]) => section.append(detailCard(labels[key] || key, compact(value), key)));
  const model = detailSection("模型调用"); model.append(detailCard(turn.model_call.skipped ? "未调用模型" : `${turn.model_call.provider} · ${turn.model_call.model}`, turn.model_call.skipped ? turn.model_call.reason : turn.model_call.prompt, turn.model_call.duration_ms ? `${turn.model_call.duration_ms} ms` : "跳过"));
  ui.detailContent.append(section, model);
}

function renderSnapshot(turn) {
  const before = detailSection("处理前"); before.append(detailList(flattenSnapshot(turn.state_before)));
  const diff = detailSection("字段变化"); diff.append(detailList(flattenDiff(turn.state_diff), true));
  const after = detailSection("处理后"); after.append(detailList(flattenSnapshot(turn.state_after)));
  ui.detailContent.append(before, diff, after);
}

function renderRaw(turn) { const section = detailSection("TurnRecord · 已脱敏"); const pre = document.createElement("pre"); pre.className = "raw-block"; pre.textContent = JSON.stringify(turn, null, 2); section.append(pre); ui.detailContent.append(section); }
function detailSection(title) { const section = document.createElement("section"); section.className = "detail-section"; const heading = document.createElement("h3"); heading.textContent = title; section.append(heading); return section; }
function detailCard(title, copy, meta) { const card = document.createElement("article"); card.className = "detail-card"; const header = document.createElement("header"); const strong = document.createElement("b"); strong.textContent = title; const span = document.createElement("span"); span.textContent = meta || ""; header.append(strong, span); const p = document.createElement("p"); p.textContent = copy || "—"; card.append(header, p); return card; }
function detailList(values, diff = false) { const list = document.createElement("div"); list.className = "detail-card detail-list"; Object.entries(values).forEach(([label, value]) => { const row = document.createElement("div"); const span = document.createElement("span"); span.textContent = label; const strong = document.createElement("strong"); strong.textContent = String(value ?? "—"); if (diff) strong.className = String(value).includes("+") ? "diff-positive" : "diff-negative"; row.append(span, strong); list.append(row); }); if (!Object.keys(values).length) { const p = document.createElement("p"); p.textContent = "本轮没有状态变化"; list.append(p); } return list; }
function flattenSnapshot(snapshot) { return { "能量": snapshot.energy, "疲劳": snapshot.fatigue, "睡眠": snapshot.is_sleeping ? "是" : "否", "主导情绪": emotionLabels[snapshot.dominant_emotion] || snapshot.dominant_emotion, "注意力": snapshot.attention_network, "动作意图": snapshot.action_intent, "记忆数": snapshot.memory_count, "情绪全景": compact(snapshot.emotions) }; }
function flattenDiff(diff, prefix = "") { const result = {}; Object.entries(diff || {}).forEach(([key, value]) => { const label = prefix ? `${prefix}.${key}` : key; if (value && typeof value === "object" && "before" in value && "after" in value) result[label] = `${value.before} → ${value.after}${typeof value.before === "number" && typeof value.after === "number" ? ` (${signed(value.before, value.after)})` : ""}`; else if (value && typeof value === "object") Object.assign(result, flattenDiff(value, label)); }); return result; }
function compact(value) { const text = JSON.stringify(value, null, 2); return text.length > 1800 ? `${text.slice(0, 1800)}\n…` : text; }
function signed(before, after) { const value = Number(after) - Number(before); return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`; }
function formatTime(value) { try { return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value)); } catch { return "—"; } }

function openCreate() { closeElfieMenu(); ui.modal.hidden = false; requestAnimationFrame(() => el("createName").focus()); }
function closeCreate() { ui.modal.hidden = true; el("createError").hidden = true; }
async function createElfie(event) {
  event.preventDefault(); const errorBox = el("createError"); errorBox.hidden = true;
  try {
    const session = await api("/api/elfies", { method: "POST", body: JSON.stringify({ name: el("createName").value, species_id: el("createSpecies").value, description: el("createDescription").value }) });
    const data = await api("/api/elfies"); state.elfies = data.items || []; closeCreate(); await selectElfie(session.elfie_id); showToast("测试精灵已创建");
  } catch (error) { errorBox.textContent = error.message; errorBox.hidden = false; }
}

let toastTimer;
function showToast(message, error = false) { clearTimeout(toastTimer); ui.toast.textContent = message; ui.toast.style.color = error ? "var(--status-error)" : "var(--text-secondary)"; ui.toast.hidden = false; toastTimer = setTimeout(() => { ui.toast.hidden = true; }, 3200); }

boot();
