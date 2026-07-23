import { api } from "./api.js";
import { el, showToast } from "./dom.js";
import { renderElfieMenu } from "./elfie-menu.js";
import { updateModelHint } from "./foods.js";
import { setPreviewControlsEnabled, syncCurrentElfiePortrait } from "./portrait.js";
import { capturePreview, completePreviewRequest, focusPreview, orbitPreview, panPreview, previewIntentPreview,
  resetPreview, sendPreview, zoomPreview,
} from "./preview-protocol.js";
import { createPreviewSyncState } from "./preview-sync-state.js";
import { renderMemoryCognition, renderPersonalityRadar, renderPersonalityTags } from "./profile-projections.js";
import { state } from "./store.js";
const previewSyncState = createPreviewSyncState();
let onPortraitSaved = () => {}; let onPreviewResult = () => {};
let dragPoint = null;
export {
  capturePreview, focusPreview, orbitPreview, panPreview,
  previewIntentPreview, resetPreview, zoomPreview,
} from "./preview-protocol.js";
export function configureProfilePreview(portraitCallback, previewResultCallback) {
  onPortraitSaved = portraitCallback;
  onPreviewResult = previewResultCallback;
}
function profileSpecRevision(profile) {
  if (Number.isInteger(profile.spec_revision) && profile.spec_revision >= 0) return profile.spec_revision;
  return [...String(profile.updated_at || JSON.stringify(profile.appearance || {}))]
    .reduce((hash, char) => ((hash * 31) + char.charCodeAt(0)) >>> 0, 0);
}
export function syncAppearancePreview() {
  if (!state.session) return;
  const profile = state.session.profile; const specRevision = profileSpecRevision(profile);
  const key = `${profile.elfie_id}:${specRevision}`;
  if (!previewSyncState.claim(key)) return;
  const requestId = sendPreview("configure", { elfie_id: profile.elfie_id, species_id: profile.species_id, spec_revision: specRevision, appearance: profile.appearance || {} });
  if (!requestId) {
    previewSyncState.release(key);
    return;
  }
  el("appearanceStatus").textContent = "配置请求已发送 · 等待 Godot";
}
function bindGestureSurface(surface) {
  surface.addEventListener("pointerdown", (event) => { event.preventDefault(); dragPoint = { x: event.clientX, y: event.clientY, pan: event.button === 2 || event.shiftKey }; });
  surface.addEventListener("pointermove", (event) => { if (!dragPoint) return; event.preventDefault(); const dx = event.clientX - dragPoint.x; const dy = event.clientY - dragPoint.y; dragPoint.x = event.clientX; dragPoint.y = event.clientY; (dragPoint.pan ? panPreview : orbitPreview)(dx * 0.008, dy * 0.008); });
  ["pointerup", "pointercancel"].forEach((name) => surface.addEventListener(name, () => { dragPoint = null; }));
  surface.addEventListener("wheel", (event) => { event.preventDefault(); if (event.shiftKey) panPreview(-event.deltaX * 0.002, -event.deltaY * 0.002); else zoomPreview(event.deltaY * 0.002); }, { passive: false });
}
export function bindPreviewControls() {
  const frame = el("appearanceFrame"); const viewport = el("appearanceViewport");
  frame.addEventListener("load", () => {
    state.previewReady = false;
    previewSyncState.setReady(false);
    setPreviewControlsEnabled(false);
    el("appearanceLoading").hidden = false;
    el("appearanceStatus").textContent = "加载中";
    bindGestureSurface(frame.contentWindow);
  });
  [["previewRotateLeft", () => orbitPreview(-0.28)], ["previewRotateRight", () => orbitPreview(0.28)], ["previewZoomOut", () => zoomPreview(0.18)], ["previewZoomIn", () => zoomPreview(-0.18)], ["previewReset", resetPreview], ["previewFocusHead", () => focusPreview("head")], ["previewCapture", () => capturePreview(state.currentId)]].forEach(([id, callback]) => el(id).addEventListener("click", callback));
  bindGestureSurface(viewport);
  window.addEventListener("message", handlePreviewMessage);
}
async function handlePreviewMessage(event) {
  if (event.origin !== window.location.origin || event.source !== el("appearanceFrame").contentWindow) return;
  let message = event.data;
  if (typeof message === "string") { if (message === "elfienest:godot-web-ready") return; try { message = JSON.parse(message); } catch { return; } }
  if (message?.channel !== "elfie-lab") return;
  if (message.event === "protocol_error") {
    el("appearanceStatus").textContent = "3D 通信失败";
    showToast(`3D 通信失败：${message.reason || "unknown"}`, true);
    return;
  }
  if (message.event === "accepted" && message.action === "configure") {
    el("appearanceStatus").textContent = "Godot 已接收 · 正在创建角色";
    return;
  }
  if (["completed", "unsupported"].includes(message.event)) {
    const retainCapture = message.action === "capture" && message.event === "completed";
    const pending = completePreviewRequest(message.request_id, { retain: retainCapture });
    if (message.action === "configure" && message.event === "completed") {
      el("appearanceStatus").textContent = "角色已装载 · 可交互";
    }
    if (message.action === "configure" && message.event === "unsupported") {
      const profile = state.session?.profile;
      if (profile) previewSyncState.release(`${profile.elfie_id}:${profileSpecRevision(profile)}`);
      el("appearanceStatus").textContent = "3D 角色装载失败";
      showToast(`3D 角色装载失败：${message.reason || "unsupported"}`, true);
    }
    if (message.action === "preview_intent" && pending?.payload.intent) {
      const completed = message.event === "completed";
      el("appearanceStatus").textContent = completed ? "动作已播放" : "动作不支持";
      onPreviewResult({ ...message, intent: pending.payload.intent });
      if (!completed) showToast(`该动作暂不可播放：${message.reason || "unsupported"}`, true);
    }
    return;
  }
  if (message.event === "ready") { state.previewReady = true; previewSyncState.setReady(true); el("appearanceLoading").hidden = true; el("appearanceStatus").textContent = "引擎已就绪 · 正在装载角色"; setPreviewControlsEnabled(true); syncAppearancePreview(); }
  if (message.event !== "portrait" || !message.data_url) return;
  const pending = completePreviewRequest(message.request_id);
  const elfieId = pending?.action === "capture" ? pending.payload.elfie_id : null;
  if (!elfieId) return;
  try {
    const result = await api(`/api/elfies/${encodeURIComponent(elfieId)}/portrait`, { method: "PUT", body: JSON.stringify({ data_url: message.data_url }) });
    const portraitUrl = `${result.portrait_url}?v=${Date.now()}`;
    state.elfies = state.elfies.map((elfie) => elfie.elfie_id === elfieId ? { ...elfie, portrait_url: portraitUrl } : elfie);
    if (state.currentId === elfieId && state.session?.profile.elfie_id === elfieId) {
      state.session.profile.portrait_url = portraitUrl;
      syncCurrentElfiePortrait(); onPortraitSaved();
    }
    showToast("头像已保存");
  } catch (error) { showToast(error.message, true); }
}
export function renderProfile() {
  const profile = state.session.profile;
  const current = state.session.current_state;
  const glyph = profile.name.trim().slice(0, 1) || "艾";
  el("avatarGlyph").textContent = glyph;
  el("elfieName").textContent = profile.name;
  el("switcherName").textContent = profile.name;
  el("elfieDescription").textContent = profile.description || profile.personality_summary;
  el("speciesLabel").textContent = profile.species_label || profile.species_id;
  const age = Number(profile.age_years);
  el("lifeStage").textContent = Number.isFinite(age) && age > 0 ? `${Number.isInteger(age) ? age : age.toFixed(1)} 岁 · ${profile.life_stage}` : (profile.life_stage || "年龄未设置");
  el("elfieId").textContent = profile.elfie_id;
  el("memoryCount").textContent = current.memory_count;
  const avatar = el("avatarImage");
  avatar.hidden = !profile.portrait_url;
  el("avatarGlyph").hidden = Boolean(profile.portrait_url);
  if (profile.portrait_url && avatar.src !== new URL(profile.portrait_url, window.location.origin).href) avatar.src = profile.portrait_url;
  renderPersonalityRadar(profile.big_five || {});
  renderPersonalityTags(profile.personality_tags || []);
  renderMemoryCognition(profile.memory_cognition || {});
  syncCurrentElfiePortrait();
  syncAppearancePreview();
  updateModelHint();
  renderElfieMenu();
}
