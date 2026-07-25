const $ = (selector) => document.querySelector(selector);

const controls = [
  "#applyBeds",
  "#addFox",
  "#addDog",
  "#wanderToggle",
  "#pauseSimulation",
  "#resumeSimulation",
  "#resetSimulation",
];

async function request(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "操作未完成");
  return payload;
}

function setNotice(message = "", isError = false) {
  const notice = $("#notice");
  notice.textContent = message;
  notice.classList.toggle("error", isError);
}

function setControlsEnabled(enabled) {
  controls.forEach((selector) => { $(selector).disabled = !enabled; });
}

function renderWorld(world) {
  $("#bedCount").value = world.bed_count;
  $("#bedCountValue").textContent = world.bed_count;
  $("#worldSummary").textContent = `${world.actor_count} 个临时角色 · 世界版本 ${world.world_revision}`;
  $("#roomStatus").textContent = world.paused ? "模拟已暂停" : world.wandering ? "随机游走中" : "等待指令";
}

function renderActors(actors) {
  const list = $("#actorList");
  list.replaceChildren();
  actors.forEach((actor) => {
    const item = document.createElement("li");
    item.textContent = `${actor.species === "fox" ? "狐狸" : "小狗"} · ${actor.actor_id}`;
    list.append(item);
  });
}

function renderEvents(events) {
  const timeline = $("#eventTimeline");
  timeline.replaceChildren();
  [...events].reverse().forEach((event) => {
    const item = document.createElement("li");
    const title = document.createElement("span");
    title.textContent = `#${event.sequence} ${event.name}`;
    const detail = document.createElement("small");
    detail.textContent = event.detail;
    item.append(title, detail);
    timeline.append(item);
  });
}

async function refreshState() {
  const [runtime, world, actors, events] = await Promise.all([
    request("/runtime"), request("/world"), request("/actors"), request("/events"),
  ]);
  renderWorld(world);
  renderActors(actors.items);
  renderEvents(events.items);
  const connected = runtime.runtime_connected;
  $("#connectionDot").classList.toggle("connected", connected);
  $("#connectionText").textContent = connected ? "Godot Runtime 已连接" : "等待 Godot Runtime 连接";
  setControlsEnabled(true);
}

async function configurePreview() {
  const status = await request("/godot-web");
  if (!status.ready) {
    $("#previewHint").textContent = `未找到导出物。请运行：${status.build_command}`;
    return;
  }
  const runtime = await request("/runtime");
  const frame = $("#godotFrame");
  const query = new URLSearchParams({
    ws: runtime.websocket_url,
    nonce: runtime.nonce,
    mode: "nest_lab",
  });
  frame.src = `${status.entry_url}?${query.toString()}`;
  frame.hidden = false;
  $("#previewPlaceholder").hidden = true;
}

async function perform(action, successMessage) {
  try {
    await action();
    await refreshState();
    setNotice(successMessage);
  } catch (error) {
    setNotice(error.message, true);
  }
}

$("#bedCount").addEventListener("input", (event) => { $("#bedCountValue").textContent = event.target.value; });
$("#applyBeds").addEventListener("click", () => perform(
  () => request("/world", { method: "PUT", body: JSON.stringify({ bed_count: Number($("#bedCount").value) }) }),
  "已提交新的房间床位数。",
));
$("#addFox").addEventListener("click", () => perform(
  () => request("/actors", { method: "POST", body: JSON.stringify({ species: "fox" }) }), "已添加一只狐狸。",
));
$("#addDog").addEventListener("click", () => perform(
  () => request("/actors", { method: "POST", body: JSON.stringify({ species: "dog" }) }), "已添加一只小狗。",
));
$("#wanderToggle").addEventListener("click", () => perform(
  () => request("/simulation/wander", { method: "POST" }), "Python 随机游走调度已开启。",
));
$("#pauseSimulation").addEventListener("click", () => perform(
  () => request("/simulation/pause", { method: "POST" }), "模拟已暂停，并取消在途移动。",
));
$("#resumeSimulation").addEventListener("click", () => perform(
  () => request("/simulation/resume", { method: "POST" }), "模拟继续运行。",
));
$("#resetSimulation").addEventListener("click", () => perform(
  () => request("/simulation/reset", { method: "POST" }), "实验台已重置；临时角色已清空。",
));
$("#refreshEvents").addEventListener("click", () => perform(refreshState, "事件时间线已刷新。"));

async function start() {
  setControlsEnabled(false);
  try {
    await configurePreview();
    await refreshState();
  } catch (error) {
    setNotice(`无法初始化 Nest Lab：${error.message}`, true);
  }
}

start();
window.setInterval(() => { refreshState().catch(() => undefined); }, 1500);
