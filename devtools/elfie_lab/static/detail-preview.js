import { state } from "./store.js";

export function recordPreviewResult(result) {
  const intentId = result.intent?.intent_id;
  if (!intentId) return;
  state.previewResults.set(intentId, result);
  document.dispatchEvent(new CustomEvent("elfie-lab:preview-result", { detail: result }));
}

export function previewResultSection(turn) {
  const section = document.createElement("section");
  section.className = "detail-section";
  const heading = document.createElement("h3");
  heading.textContent = "动作回放";
  section.append(heading);
  const intents = turn.decision?.action_intents || [];
  const results = intents
    .map((intent) => state.previewResults.get(intent.intent_id))
    .filter(Boolean);
  if (!results.length) {
    section.append(resultCard("尚未回放", "点击消息下方的具体动作按钮后才会播放", "等待操作"));
    return section;
  }
  results.forEach((result) => {
    const label = result.intent.motion || result.intent.expression || result.intent.intent_id;
    const status = result.event === "completed" ? "已播放" : "不支持";
    section.append(resultCard(label, result.reason || "Godot 已接受该动作", status));
  });
  return section;
}

function resultCard(title, body, status) {
  const article = document.createElement("article");
  article.className = "detail-card preview-result-card";
  const header = document.createElement("header");
  const heading = document.createElement("b");
  const badge = document.createElement("span");
  heading.textContent = title;
  badge.textContent = status;
  header.append(heading, badge);
  const copy = document.createElement("p");
  copy.textContent = body;
  article.append(header, copy);
  return article;
}
