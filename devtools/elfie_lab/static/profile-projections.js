import { el } from "./dom.js";

export function renderPersonalityRadar(values) {
  const svg = el("personalityRadar");
  const axes = [
    ["开放", "openness"], ["尽责", "conscientiousness"], ["外向", "extraversion"],
    ["亲和", "agreeableness"], ["敏感", "neuroticism"],
  ];
  const center = [105, 82]; const radius = 58;
  const point = (index, scale) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / axes.length;
    return [center[0] + Math.cos(angle) * radius * scale, center[1] + Math.sin(angle) * radius * scale];
  };
  svg.replaceChildren();
  [0.25, 0.5, 0.75, 1].forEach((scale) => appendSvg(svg, "polygon", {
    points: axes.map((_, index) => point(index, scale).join(",")).join(" "), class: "radar-grid",
  }));
  axes.forEach(([label], index) => {
    const edge = point(index, 1); const textPoint = point(index, 1.28);
    appendSvg(svg, "line", { x1: center[0], y1: center[1], x2: edge[0], y2: edge[1], class: "radar-axis" });
    const text = appendSvg(svg, "text", { x: textPoint[0], y: textPoint[1], class: "radar-label", "text-anchor": "middle" });
    text.textContent = label;
  });
  const profilePoints = axes.map(([, key], index) => point(index, Math.max(0, Math.min(1, Number(values[key] ?? 0.5)))));
  appendSvg(svg, "polygon", { points: profilePoints.map((item) => item.join(",")).join(" "), class: "radar-profile" });
  profilePoints.forEach(([x, y]) => appendSvg(svg, "circle", { cx: x, cy: y, r: 3, class: "radar-point" }));
}

export function renderPersonalityTags(tags) {
  el("personalityTags").replaceChildren(...tags.slice(0, 3).map((label) => {
    const span = document.createElement("span"); span.textContent = label; return span;
  }));
}

export function renderMemoryCognition(memory) {
  renderTopicCloud(memory.topics || []);
  renderImportantEvents(memory.important_events || []);
  renderGraph(el("relationGraph"), memory.relations || {}, true);
  renderGraph(el("knowledgeGraph"), memory.knowledge || {}, false);
  el("worldUnderstanding").textContent = memory.world_understanding || "尚未形成稳定的世界理解";
}

function renderTopicCloud(topics) {
  const max = Math.max(1, ...topics.map((item) => Number(item.weight || 1)));
  const nodes = topics.map((item, index) => {
    const span = document.createElement("span"); span.textContent = item.label;
    span.style.fontSize = `${10 + 8 * Number(item.weight || 1) / max}px`; span.className = `topic-${index % 4}`;
    return span;
  });
  if (!nodes.length) { const empty = document.createElement("small"); empty.textContent = "互动后将在这里形成记忆主题"; nodes.push(empty); }
  el("topicCloud").replaceChildren(...nodes);
}

function renderImportantEvents(events) {
  const nodes = events.map((event) => {
    const article = document.createElement("article"); const time = document.createElement("time");
    time.textContent = event.timestamp ? new Date(event.timestamp).toLocaleDateString("zh-CN") : "未标记日期";
    const copy = document.createElement("p"); copy.textContent = event.content; article.append(time, copy); return article;
  });
  if (!nodes.length) { const empty = document.createElement("p"); empty.className = "projection-empty"; empty.textContent = "尚无重要经历"; nodes.push(empty); }
  el("importantEvents").replaceChildren(...nodes);
}

function renderGraph(svg, graph, relations) {
  const nodes = (graph.nodes || []).slice(0, relations ? 9 : 12); const links = graph.links || [];
  svg.replaceChildren();
  if (!nodes.length || (relations && nodes.length === 1)) {
    const text = appendSvg(svg, "text", { x: 170, y: 108, class: "graph-empty", "text-anchor": "middle" });
    text.textContent = relations ? "互动后将形成关系网络" : "尚未沉淀知识与信念"; return;
  }
  const positions = new Map();
  nodes.forEach((node, index) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / nodes.length; const centerNode = relations && index === 0;
    positions.set(node.id, centerNode ? [170, 105] : [170 + Math.cos(angle) * 112, 105 + Math.sin(angle) * 72]);
  });
  links.forEach((link) => {
    const from = positions.get(link.source); const to = positions.get(link.target);
    if (from && to) appendSvg(svg, "line", { x1: from[0], y1: from[1], x2: to[0], y2: to[1], class: "graph-link" });
  });
  if (relations) nodes.slice(1).forEach((node) => {
    if (!links.some((link) => link.source === node.id || link.target === node.id)) {
      const from = positions.get(nodes[0].id); const to = positions.get(node.id);
      appendSvg(svg, "line", { x1: from[0], y1: from[1], x2: to[0], y2: to[1], class: "graph-link muted" });
    }
  });
  nodes.forEach((node, index) => {
    const [x, y] = positions.get(node.id); const centerNode = relations && index === 0;
    appendSvg(svg, "circle", { cx: x, cy: y, r: centerNode ? 24 : 15 + Math.min(7, Number(node.weight || 0.4) * 7), class: centerNode ? "graph-node self" : "graph-node" });
    const text = appendSvg(svg, "text", { x, y: y + (centerNode ? 34 : 29), class: "graph-label", "text-anchor": "middle" });
    text.textContent = String(node.label || "").slice(0, 10);
  });
}

function appendSvg(parent, tag, attrs) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  parent.append(node); return node;
}
