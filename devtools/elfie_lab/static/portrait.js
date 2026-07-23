import { el } from "./dom.js";
import { state } from "./store.js";

const GODOT_PREVIEW_URL = "/godot-web/elfienest.html?mode=elfie_lab";

export function elfiePortraitUrl(elfieId, savedUrl = "") {
  return savedUrl || `/api/elfies/${encodeURIComponent(elfieId)}/portrait`;
}

export function createPortraitThumbnail(elfie, size = 28) {
  const portrait = document.createElement("span");
  portrait.className = "elfie-menu-portrait";
  portrait.style.cssText = `position:relative;display:grid;place-items:center;width:${size}px;height:${size}px;flex:0 0 ${size}px;overflow:hidden;border-radius:8px;background:var(--accent-primary);color:#fff;font-weight:800`;
  const fallback = document.createElement("span");
  fallback.textContent = elfie.name?.trim().slice(0, 1) || "艾";
  const image = document.createElement("img");
  image.alt = `${elfie.name || "精灵"}的头像`;
  image.width = size;
  image.height = size;
  image.hidden = true;
  image.style.cssText = "width:100%;height:100%;object-fit:cover";
  image.src = elfiePortraitUrl(elfie.elfie_id, elfie.portrait_url);
  image.addEventListener("load", () => {
    image.hidden = false;
    fallback.hidden = true;
  });
  image.addEventListener("error", () => {
    image.hidden = true;
    fallback.hidden = false;
  });
  portrait.append(fallback, image);
  return portrait;
}

export function syncCurrentElfiePortrait() {
  if (!state.session) return;
  const profile = state.session.profile;
  const miniAvatar = el("miniAvatar");
  miniAvatar.replaceChildren(createPortraitThumbnail(profile, 40));
  miniAvatar.setAttribute("aria-label", `${profile.name}的头像`);
}

export function setPreviewControlsEnabled(enabled) {
  document.querySelectorAll(".appearance-tools button").forEach((button) => {
    button.disabled = !enabled;
  });
}

export async function ensurePreviewFrame() {
  const frame = el("appearanceFrame");
  if (frame.src.includes("/godot-web/")) return;
  setPreviewControlsEnabled(false);
  try {
    const response = await fetch(GODOT_PREVIEW_URL, { method: "HEAD" });
    if (!response.ok) throw new Error(`Godot Web ${response.status}`);
    frame.src = GODOT_PREVIEW_URL;
  } catch {
    el("appearanceLoading").hidden = true;
    el("appearanceStatus").textContent = "3D 预览不可用";
  }
}
