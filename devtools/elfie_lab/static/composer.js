import { api, MAX_MEDIA_BYTES, uploadMedia } from "./api.js";
import { el, showToast, ui } from "./dom.js";
import { openDetail } from "./detail.js";
import { refreshFoods } from "./foods.js";
import { renderProfile } from "./profile.js";
import { state } from "./store.js";
import { renderTimeline } from "./timeline.js";

const emotionInputs = [
  ["happiness", "injectEmotionHappiness"],
  ["sadness", "injectEmotionSadness"],
  ["anger", "injectEmotionAnger"],
  ["fear", "injectEmotionFear"],
  ["surprise", "injectEmotionSurprise"],
  ["disgust", "injectEmotionDisgust"],
  ["boredom", "injectEmotionBoredom"],
  ["attachment", "injectEmotionAttachment"],
];

let attachedImage = null;
let previewUrl = null;

function numberValue(id) {
  return Number(el(id)?.value || 0);
}

function debugEnabled() {
  return Boolean(el("debugInjectionEnabled")?.checked);
}

function clearDebugInputs() {
  ["injectEnergy", "injectFatigue", ...emotionInputs.map(([, id]) => id)]
    .forEach((id) => { el(id).value = ""; });
  el("injectSleeping").checked = false;
  delete el("injectSleeping").dataset.touched;
}

function stateInjection() {
  const injection = {};
  if (!debugEnabled()) return injection;
  if (el("injectEnergy").value !== "") injection.energy = numberValue("injectEnergy");
  if (el("injectFatigue").value !== "") injection.fatigue = numberValue("injectFatigue");
  if (el("injectSleeping").dataset.touched) injection.is_sleeping = el("injectSleeping").checked;
  const emotions = {};
  emotionInputs.forEach(([name, id]) => {
    if (el(id).value !== "") emotions[name] = numberValue(id);
  });
  if (Object.keys(emotions).length) injection.emotions = emotions;
  return injection;
}

function turnBody(foodKey) {
  const body = {
    message: ui.message.value.trim(),
    food_key: foodKey,
    temperature: numberValue("temperatureInput"),
    is_network_online: el("networkOnline").checked,
    salience_score: numberValue("salienceInput"),
    impact_force: numberValue("impactInput"),
    impact_direction: el("impactDirection").value,
    gentle_stroke: numberValue("strokeInput"),
  };
  const injection = stateInjection();
  if (Object.keys(injection).length) body.state_injection = injection;
  return body;
}

function hasEffectiveStimulus(body) {
  return Boolean(
    body.message || attachedImage || body.impact_force || body.gentle_stroke
    || body.state_injection || body.salience_score >= 70,
  );
}

function setAttachmentStatus(text, isError = false) {
  el("mediaPreviewStatus").textContent = text;
  el("mediaPreviewStatus").setAttribute("role", isError ? "alert" : "status");
}

function selectAttachedImage(file) {
  removeAttachedImage();
  el("mediaPreview").hidden = false;
  el("mediaPreviewName").textContent = file.name;
  if (file.size > MAX_MEDIA_BYTES) {
    setAttachmentStatus("图片不能超过 5 MiB", true);
    showToast("图片不能超过 5 MiB", true);
    return;
  }
  attachedImage = { file, descriptor: null, elfieId: null };
  previewUrl = URL.createObjectURL(file);
  el("mediaPreviewImage").src = previewUrl;
  setAttachmentStatus("等待上传");
  updateChannelHint();
}

export function removeAttachedImage() {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  attachedImage = null;
  if (el("mediaInput")) el("mediaInput").value = "";
  if (el("mediaPreviewImage")) el("mediaPreviewImage").removeAttribute("src");
  if (el("mediaPreview")) el("mediaPreview").hidden = true;
  updateChannelHint();
}

export async function sendTurn(event) {
  event.preventDefault();
  if (!state.currentId || state.sending) return;
  const selectedBeforeRefresh = el("foodSelect").value;
  if (!await refreshFoods(selectedBeforeRefresh)) return;
  const foodKey = el("foodSelect").value;
  const food = state.foods.find((item) => item.key === foodKey);
  if (!food || !food.ready_for_attempt) {
    showToast(`粮食「${food?.display_name || foodKey}」尚未就绪`, true);
    return;
  }
  const body = turnBody(foodKey);
  if (!hasEffectiveStimulus(body)) {
    showToast("请输入消息或添加有效刺激", true);
    return;
  }
  setSending(true);
  try {
    if (attachedImage && attachedImage.elfieId !== state.currentId) {
      setAttachmentStatus("正在上传");
      attachedImage.descriptor = await uploadMedia(state.currentId, attachedImage.file);
      attachedImage.elfieId = state.currentId;
      setAttachmentStatus("上传完成");
    }
    if (attachedImage) body.vision_media_id = attachedImage.descriptor.media_id;
    const turn = await api(`/api/elfies/${encodeURIComponent(state.currentId)}/turns`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    state.session.turns.push(turn);
    state.session.current_state = turn.state_after;
    ui.message.value = "";
    autoGrow();
    clearOneShotInputs();
    renderProfile();
    renderTimeline();
    openDetail(turn, "output");
  } catch (error) {
    if (attachedImage) setAttachmentStatus(error.message, true);
    showToast(error.message, true);
  } finally {
    setSending(false);
  }
}

export function setSending(value) {
  state.sending = value;
  ui.send.disabled = value || !state.currentId;
  ui.message.disabled = value || !state.currentId;
  el("mediaAttach").disabled = value || !state.currentId;
  el("mediaRemove").disabled = value;
  ui.send.querySelector("span").textContent = value ? "思考中" : "发送";
}

export function clearOneShotInputs() {
  el("impactInput").value = "0";
  el("impactDirection").value = "none";
  el("strokeInput").value = "0";
  clearDebugInputs();
  removeAttachedImage();
  updateChannelHint();
}

export function autoGrow() {
  ui.message.style.height = "auto";
  ui.message.style.height = `${Math.min(ui.message.scrollHeight, 140)}px`;
}

export function updateChannelHint() {
  const tags = ["文字"];
  if (attachedImage) tags.push("图片");
  if (numberValue("impactInput") || numberValue("strokeInput")) tags.push("触觉");
  if (numberValue("salienceInput") !== 20 || numberValue("temperatureInput") !== 24 || !el("networkOnline")?.checked) tags.push("环境");
  if (debugEnabled() && Object.keys(stateInjection()).length) tags.push("注入");
  el("channelHint").textContent = tags.map((tag) => `[${tag}]`).join("");
}

function selectStimulusTab(debug) {
  el("advancedStimulusPanel").hidden = debug;
  el("debugStimulusPanel").hidden = !debug;
  el("advancedTab").classList.toggle("active", !debug);
  el("debugTab").classList.toggle("active", debug);
  el("advancedTab").setAttribute("aria-selected", String(!debug));
  el("debugTab").setAttribute("aria-selected", String(debug));
}

function setDebugEnabled(enabled) {
  el("debugInjectionFields").setAttribute("aria-disabled", String(!enabled));
  el("debugInjectionFields").querySelectorAll("input").forEach((input) => {
    input.disabled = !enabled;
  });
  if (!enabled) clearDebugInputs();
  updateChannelHint();
}

export function configureComposer() {
  if (!ui.composer || ui.composer.dataset.layeredInputs === "true") return;
  ui.composer.dataset.layeredInputs = "true";
  el("mediaAttach").addEventListener("click", () => el("mediaInput").click());
  el("mediaInput").addEventListener("change", () => {
    if (el("mediaInput").files?.[0]) selectAttachedImage(el("mediaInput").files[0]);
  });
  el("mediaRemove").addEventListener("click", removeAttachedImage);
  el("advancedTab").addEventListener("click", () => selectStimulusTab(false));
  el("debugTab").addEventListener("click", () => selectStimulusTab(true));
  el("debugInjectionEnabled").addEventListener("change", (event) => setDebugEnabled(event.target.checked));
  el("injectSleeping").addEventListener("change", (event) => { event.target.dataset.touched = "true"; updateChannelHint(); });
  ["temperatureInput", "networkOnline", "impactDirection", ...emotionInputs.map(([, id]) => id)]
    .forEach((id) => el(id).addEventListener("input", updateChannelHint));
  setDebugEnabled(false);
}

configureComposer();
