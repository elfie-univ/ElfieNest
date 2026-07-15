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
};

const el = (id) => document.getElementById(id);
const ui = {
  shell: el("labShell"), elfieEmpty: el("elfieEmpty"), elfieContent: el("elfieContent"),
  switcherWrap: el("switcherWrap"), elfieMenu: el("elfieMenu"), switcher: el("elfieSwitcher"),
  timeline: el("timeline"), placeholder: el("timelinePlaceholder"), composer: el("composer"),
  message: el("messageInput"), send: el("sendButton"), detail: el("detailPanel"),
  detailContent: el("detailContent"), modal: el("createModal"), createForm: el("createForm"),
  toast: el("toast"), stimulusDrawer: el("stimulusDrawer"), stimulusToggle: el("stimulusToggle"),
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
  } catch (error) { showToast(error.message, true); }
}

function bindEvents() {
  el("emptyCreate").addEventListener("click", openCreate);
  el("createClose").addEventListener("click", closeCreate);
  el("createCancel").addEventListener("click", closeCreate);
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
}

function showEmpty() {
  ui.elfieEmpty.hidden = false; ui.elfieContent.hidden = true; ui.switcherWrap.hidden = true;
  ui.message.disabled = true; ui.send.disabled = true;
}

async function selectElfie(id) {
  closeElfieMenu();
  const session = await api(`/api/elfies/${encodeURIComponent(id)}`);
  state.currentId = id; state.session = session; state.selectedTurn = null;
  localStorage.setItem("elfieLab.currentElfie", id);
  ui.elfieEmpty.hidden = true; ui.elfieContent.hidden = false; ui.switcherWrap.hidden = false;
  ui.message.disabled = false; ui.send.disabled = false;
  renderProfile(); renderTimeline(); closeDetail();
}

function renderProfile() {
  const profile = state.session.profile; const current = state.session.current_state;
  const glyph = profile.name.trim().slice(0, 1) || "艾";
  el("avatarGlyph").textContent = glyph; el("miniAvatar").textContent = glyph;
  el("elfieName").textContent = profile.name; el("switcherName").textContent = profile.name;
  el("elfieDescription").textContent = profile.description || profile.personality_summary;
  el("energyValue").textContent = `${current.energy.toFixed(1)}%`; el("energyBar").style.width = `${current.energy}%`;
  el("fatigueValue").textContent = `${current.fatigue.toFixed(1)}%`; el("fatigueBar").style.width = `${current.fatigue}%`;
  el("wakeStatus").textContent = current.is_sleeping ? "正在睡眠" : "清醒 · 实时状态";
  el("dominantEmotion").textContent = emotionLabels[current.dominant_emotion] || current.dominant_emotion;
  el("memoryCount").textContent = current.memory_count;
  renderGrid(el("basicProfile"), [["身体", profile.anatomy_type === "biped" ? "双足直立" : "四足动物"], ["画像", profile.personality_summary], ["注意力", current.attention_network], ["当前动作", current.action_intent]]);
  const five = profile.big_five || {};
  renderGrid(el("personalityProfile"), Object.entries(five).map(([key, value]) => [({openness:"开放度", conscientiousness:"尽责度", extraversion:"外向度", agreeableness:"宜人性", neuroticism:"敏感度"}[key] || key), Number(value).toFixed(2)]));
  renderStack(el("cognitionProfile"), Object.entries(profile.core_cognition || {}).map(([key, value]) => [({identity:"自我认知", relation:"主人关系", world:"世界观", tendency:"行为倾向"}[key] || key), value]));
  const actions = profile.capabilities?.actuators?.motion?.supported_actions || [];
  renderStack(el("bodyProfile"), [["允许动作", actions.join("、") || "未配置"], ["关节数", String(Object.keys(current.joint_angles || {}).length)], ["当前表情", current.expression?.expression || "平静"]]);
  updateModelHint();
  renderElfieMenu();
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
    const session = await api("/api/elfies", { method: "POST", body: JSON.stringify({ name: el("createName").value, anatomy_type: el("createAnatomy").value, description: el("createDescription").value }) });
    const data = await api("/api/elfies"); state.elfies = data.items || []; closeCreate(); await selectElfie(session.elfie_id); showToast("测试精灵已创建");
  } catch (error) { errorBox.textContent = error.message; errorBox.hidden = false; }
}

let toastTimer;
function showToast(message, error = false) { clearTimeout(toastTimer); ui.toast.textContent = message; ui.toast.style.color = error ? "var(--status-error)" : "var(--text-secondary)"; ui.toast.hidden = false; toastTimer = setTimeout(() => { ui.toast.hidden = true; }, 3200); }

boot();
