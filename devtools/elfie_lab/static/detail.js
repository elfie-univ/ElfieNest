import { el, ui } from "./dom.js";
import { compact, formatTime, signed } from "./detail-format.js";
import { previewResultSection } from "./detail-preview.js";
import { emotionLabels, state } from "./store.js";

export function bindDetailTabs() {
  document.querySelectorAll(".detail-tabs button").forEach((button) => {
    button.addEventListener("click", () => {
      state.detailTab = button.dataset.tab;
      document.querySelectorAll(".detail-tabs button").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      renderDetail();
    });
  });
  document.addEventListener("elfie-lab:preview-result", () => {
    if (state.selectedTurn) renderDetail();
  });
}

export function openDetail(turn, focus) {
  state.selectedTurn = turn;
  state.selectedFocus = focus;
  state.detailTab = focus === "chain" ? "chain" : "summary";
  document.querySelectorAll(".detail-tabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === state.detailTab);
  });
  ui.shell.classList.add("detail-open");
  ui.detail.classList.remove("is-closed");
  ui.detail.setAttribute("aria-hidden", "false");
  el("detailKicker").textContent = `历史回合 · ${formatTime(turn.timestamp)} · 只读`;
  el("detailTitle").textContent = focus === "input" ? "输入与感知" : focus === "chain" ? "完整处理链路" : "决策与执行";
  renderDetail();
}

export function closeDetail() {
  if (state.session) {
    renderCurrentState(state.session.current_state);
    return;
  }
  ui.shell.classList.remove("detail-open");
  ui.detail.classList.add("is-closed");
  ui.detail.setAttribute("aria-hidden", "true");
}

export function renderCurrentState(currentState) {
  state.selectedTurn = null;
  ui.shell.classList.add("detail-open");
  ui.detail.classList.remove("is-closed");
  ui.detail.setAttribute("aria-hidden", "false");
  el("detailKicker").textContent = "实时 · 未选择历史回合";
  el("detailTitle").textContent = "当前状态";
  ui.detailContent.replaceChildren();
  const section = detailSection("实时快照");
  section.append(detailList(flattenSnapshot(currentState)));
  ui.detailContent.append(section);
}

function renderDetail() {
  const turn = state.selectedTurn;
  if (!turn) {
    ui.detailContent.replaceChildren();
    return;
  }
  ui.detailContent.replaceChildren();
  if (state.detailTab === "summary") renderSummary(turn);
  if (state.detailTab === "chain") renderChain(turn);
  if (state.detailTab === "snapshot") renderSnapshot(turn);
  if (state.detailTab === "raw") renderRaw(turn);
}

function renderSummary(turn) {
  const stimulus = detailSection("本轮输入");
  stimulus.append(detailCard("开发者刺激", turn.stimulus_bundle.message || "非文字刺激", turn.food_key || "mock"));
  if (turn.used_state_injection) {
    stimulus.append(detailCard("状态注入", JSON.stringify(turn.stimulus_bundle.state_injection, null, 2), "已永久标记"));
  }
  const history = detailSection("历史状态");
  history.append(detailCard("处理前", compact(turn.state_before), "state_before"));
  history.append(detailCard("字段变化", compact(turn.state_diff), "state_diff"));
  history.append(detailCard("处理后", compact(turn.state_after), "state_after"));
  ui.detailContent.append(
    stimulus,
    history,
    decisionSection(turn.decision),
    previewResultSection(turn),
    receiptSection(turn),
  );
}

function decisionSection(decision = {}) {
  const section = detailSection("决策意图");
  const groups = [
    ["Speech", decision.speech_intents || []],
    ["Message", decision.message_intents || []],
    ["Motion", decision.motion_intents || []],
    ["Expression", decision.expression_intents || []],
    ["Internal", decision.internal_intents || []],
    ["No-op", decision.noop_intents || []],
  ];
  groups.forEach(([label, intents]) => {
    intents.forEach((intent) => {
      section.append(detailCard(label, compact(intent), intent.status || "pending"));
    });
  });
  if (!section.querySelector("article")) {
    section.append(detailCard("无决策计划", "本轮没有持久化 typed intent", "只读"));
  }
  return section;
}

function receiptSection(turn) {
  const section = detailSection("执行回执");
  const receipts = turn.trace?.stages?.output_receipts || [];
  receipts.forEach((receipt) => {
    const error = receipt.error?.message || receipt.error?.code || "无错误";
    section.append(detailCard(
      receipt.intent_id || "未知 intent",
      error,
      receipt.status || "unknown",
    ));
  });
  if (!receipts.length) section.append(detailCard("无执行回执", "本轮没有持久化回执", "只读"));
  return section;
}

function renderChain(turn) {
  const stages = turn.trace?.stages || {};
  const section = detailSection("执行阶段");
  const labels = {
    state_injection: "状态注入",
    sleep_gate: "睡眠门控",
    brainstem_reflex: "脑干反射",
    sensory_filter: "感知过滤",
    thalamus_context: "丘脑上下文",
    decision: "注意力与决策",
    action_validation: "动作校验",
    execution: "身体执行",
    memory_write: "记忆写入",
  };
  Object.entries(stages).forEach(([key, value]) => {
    section.append(detailCard(labels[key] || key, compact(value), key));
  });
  const model = detailSection("模型调用");
  const modelTitle = turn.model_call.skipped ? "未调用模型" : `${turn.model_call.provider} · ${turn.model_call.model}`;
  model.append(detailCard(modelTitle, turn.model_call.skipped ? turn.model_call.reason : turn.model_call.prompt, turn.model_call.duration_ms ? `${turn.model_call.duration_ms} ms` : "跳过"));
  ui.detailContent.append(section, model);
}

function renderSnapshot(turn) {
  const before = detailSection("处理前");
  before.append(detailList(flattenSnapshot(turn.state_before)));
  const diff = detailSection("字段变化");
  diff.append(detailList(flattenDiff(turn.state_diff), true));
  const after = detailSection("处理后");
  after.append(detailList(flattenSnapshot(turn.state_after)));
  ui.detailContent.append(before, diff, after);
}

function renderRaw(turn) {
  const section = detailSection("TurnRecord · 已脱敏");
  const pre = document.createElement("pre");
  pre.className = "raw-block";
  pre.textContent = JSON.stringify(turn, null, 2);
  section.append(pre);
  ui.detailContent.append(section);
}

function detailSection(title) {
  const section = document.createElement("section");
  section.className = "detail-section";
  const heading = document.createElement("h3");
  heading.textContent = title;
  section.append(heading);
  return section;
}

function detailCard(title, copy, meta) {
  const card = document.createElement("article");
  card.className = "detail-card";
  const header = document.createElement("header");
  const strong = document.createElement("b");
  strong.textContent = title;
  const span = document.createElement("span");
  span.textContent = meta || "";
  header.append(strong, span);
  const paragraph = document.createElement("p");
  paragraph.textContent = copy || "—";
  card.append(header, paragraph);
  return card;
}

function detailList(values, diff = false) {
  const list = document.createElement("div");
  list.className = "detail-card detail-list";
  Object.entries(values).forEach(([label, value]) => {
    const row = document.createElement("div");
    const span = document.createElement("span");
    span.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = String(value ?? "—");
    if (diff) strong.className = String(value).includes("+") ? "diff-positive" : "diff-negative";
    row.append(span, strong);
    list.append(row);
  });
  if (!Object.keys(values).length) {
    const paragraph = document.createElement("p");
    paragraph.textContent = "本轮没有状态变化";
    list.append(paragraph);
  }
  return list;
}

function flattenSnapshot(snapshot) {
  return {
    "能量": snapshot.energy,
    "疲劳": snapshot.fatigue,
    "睡眠": snapshot.is_sleeping ? "是" : "否",
    "主导情绪": emotionLabels[snapshot.dominant_emotion] || snapshot.dominant_emotion,
    "注意力": snapshot.attention_network,
    "动作意图": snapshot.action_intent,
    "记忆数": snapshot.memory_count,
    "情绪全景": compact(snapshot.emotions),
  };
}

function flattenDiff(diff, prefix = "") {
  const result = {};
  Object.entries(diff || {}).forEach(([key, value]) => {
    const label = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object" && "before" in value && "after" in value) {
      const delta = typeof value.before === "number" && typeof value.after === "number"
        ? ` (${signed(value.before, value.after)})`
        : "";
      result[label] = `${value.before} → ${value.after}${delta}`;
    } else if (value && typeof value === "object") {
      Object.assign(result, flattenDiff(value, label));
    }
  });
  return result;
}
