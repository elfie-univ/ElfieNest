import { el, ui } from "./dom.js";
import { openDetail } from "./detail.js";
import { formatTime, signed } from "./detail-format.js";
import { emotionLabels, state } from "./store.js";

let onPreviewIntent = () => {};

export function configureTimeline(callbacks) {
  onPreviewIntent = callbacks.onPreviewIntent;
}

export function renderTimeline() {
  const turns = state.session.turns || [];
  el("turnCount").textContent = `${turns.length} 轮`;
  ui.timeline.replaceChildren();
  if (!turns.length) {
    ui.placeholder.hidden = false;
    ui.timeline.append(ui.placeholder);
    return;
  }
  turns.forEach((turn, index) => ui.timeline.append(createTurnNode(turn, index)));
  requestAnimationFrame(() => { ui.timeline.scrollTop = ui.timeline.scrollHeight; });
}

function createTurnNode(turn, index) {
  const wrap = document.createElement("article");
  wrap.className = "turn";
  wrap.dataset.turnId = turn.turn_id;
  const meta = document.createElement("div");
  meta.className = "turn-meta";
  meta.textContent = `TURN ${String(index + 1).padStart(2, "0")}  ·  ${formatTime(turn.timestamp)}`;
  const userRow = document.createElement("div");
  userRow.className = "bubble-row user";
  const userBubble = bubbleNode(
    "开发者刺激",
    turn.stimulus_bundle.message || "非文字刺激",
    turn.used_state_injection ? ["状态注入"] : [],
    "user",
  );
  userBubble.addEventListener("click", () => openDetail(turn, "input"));
  userRow.append(userBubble);
  const process = document.createElement("button");
  process.type = "button";
  process.className = "process-line";
  const attention = turn.trace?.stages?.decision?.attention_mode || "无模型路径";
  process.append(
    document.createTextNode("感知"),
    dot(),
    document.createTextNode(attention),
    dot(),
    document.createTextNode(`${turn.duration_ms}ms`),
  );
  process.addEventListener("click", () => openDetail(turn, "chain"));
  const elfieRow = document.createElement("div");
  elfieRow.className = "bubble-row elfie";
  const result = turn.result || {};
  const decision = turn.decision || {};
  const responseTexts = [
    ...(decision.spoken_texts || []),
    ...(decision.message_texts || []),
  ];
  const tags = [];
  if (turn.state_after?.dominant_emotion) {
    tags.push(emotionLabels[turn.state_after.dominant_emotion] || turn.state_after.dominant_emotion);
  }
  if (turn.state_diff?.energy) {
    tags.push(`能量 ${signed(turn.state_diff.energy.before, turn.state_diff.energy.after)}`);
  }
  const elfieBubble = bubbleNode(
    state.session.profile.name,
    responseTexts.join("\n") || "本轮无文字输出",
    tags,
    result.success === false ? "error" : "elfie",
  );
  elfieBubble.addEventListener("click", () => openDetail(turn, "output"));
  appendActionButtons(elfieBubble, decision);
  elfieRow.append(elfieBubble);
  wrap.append(meta, userRow, process, elfieRow);
  return wrap;
}

function appendActionButtons(bubble, decision) {
  const intents = actionIntents(decision);
  if (!intents.length) return;
  const actions = document.createElement("div");
  actions.className = "turn-actions";
  intents.forEach((intent) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "turn-action";
    button.dataset.intentId = intent.intent_id;
    button.textContent = intentLabel(intent);
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      onPreviewIntent(intent);
    });
    actions.append(button);
  });
  bubble.append(actions);
}

function actionIntents(decision) {
  if (Array.isArray(decision.action_intents)) return decision.action_intents;
  return [
    ...(decision.motion_intents || []),
    ...(decision.expression_intents || []),
  ];
}

function intentLabel(intent) {
  if (intent.motion) return `动作 · ${intent.motion}`;
  const intensity = intent.intensity == null ? "" : ` · ${intent.intensity}`;
  return `表情 · ${intent.expression}${intensity}`;
}

function bubbleNode(label, text, tags, kind) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${kind === "error" ? "error" : ""}`;
  const header = document.createElement("div");
  header.className = "bubble-label";
  const name = document.createElement("span");
  name.textContent = label;
  header.append(name);
  if (kind === "user") {
    const channel = document.createElement("span");
    channel.className = "channel";
    channel.textContent = "文字";
    header.append(channel);
  }
  const copy = document.createElement("p");
  copy.textContent = text;
  bubble.append(header, copy);
  if (tags.length) {
    const row = document.createElement("div");
    row.className = "bubble-tags";
    tags.forEach((tag) => {
      const item = document.createElement("span");
      item.textContent = tag;
      if (tag === "状态注入") item.className = "warning";
      row.append(item);
    });
    bubble.append(row);
  }
  return bubble;
}

function dot() {
  return document.createElement("i");
}
