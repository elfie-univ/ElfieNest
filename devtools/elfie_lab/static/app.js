import { api } from "./api.js";
import { autoGrow, sendTurn, updateChannelHint } from "./composer.js";
import { bindDeleteConfirmation, confirmElfieDeletion } from "./confirm-delete.js";
import { closeCreate, configureCreateElfie, createElfie, openCreate } from "./create-elfie.js";
import { closeDetail, bindDetailTabs } from "./detail.js";
import { recordPreviewResult } from "./detail-preview.js";
import { el, showToast, ui } from "./dom.js";
import { closeElfieMenu, configureElfieMenu, toggleElfieMenu } from "./elfie-menu.js";
import { populateFoodSelect, updateModelHint } from "./foods.js";
import { ensurePreviewFrame } from "./portrait.js";
import { bindPersonalityEditor } from "./personality-editor.js";
import { bindPreviewControls, configureProfilePreview, previewIntentPreview, renderProfile } from "./profile.js";
import { state } from "./store.js";
import { configureTimeline, renderTimeline } from "./timeline.js";

function showEmpty() {
  ui.elfieEmpty.hidden = false;
  ui.elfieContent.hidden = true;
  ui.switcherWrap.hidden = true;
  ui.message.disabled = true;
  ui.send.disabled = true;
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
  state.currentId = id;
  state.session = session;
  state.selectedTurn = null;
  localStorage.setItem("elfieLab.currentElfie", id);
  ui.elfieEmpty.hidden = true;
  ui.elfieContent.hidden = false;
  ui.switcherWrap.hidden = false;
  ui.elfieError.hidden = true;
  ui.message.disabled = false;
  ui.send.disabled = false;
  ensurePreviewFrame();
  renderProfile();
  renderTimeline();
  closeDetail();
}

function bindEvents() {
  configureElfieMenu({
    onSelect: (id) => selectElfie(id).catch((error) => showToast(error.message, true)),
    onCreate: openCreate,
    onConfirmDelete: confirmElfieDeletion,
  });
  configureTimeline({
    onPreviewIntent: previewIntentPreview,
  });
  configureCreateElfie(selectElfie);
  configureProfilePreview(renderProfile, recordPreviewResult);
  bindPersonalityEditor(renderProfile);
  el("emptyCreate").addEventListener("click", openCreate);
  el("createClose").addEventListener("click", closeCreate);
  el("createCancel").addEventListener("click", closeCreate);
  if (el("errorReload")) el("errorReload").addEventListener("click", () => window.location.reload());
  ui.modal.addEventListener("click", (event) => { if (event.target === ui.modal) closeCreate(); });
  ui.createForm.addEventListener("submit", createElfie);
  bindDeleteConfirmation();
  ui.switcher.addEventListener("click", toggleElfieMenu);
  el("leftCollapse").addEventListener("click", () => ui.shell.classList.toggle("left-closed"));
  el("detailClose").addEventListener("click", closeDetail);
  bindDetailTabs();
  ui.stimulusToggle.addEventListener("click", () => {
    const open = ui.stimulusDrawer.hidden;
    ui.stimulusDrawer.hidden = !open;
    ui.stimulusToggle.classList.toggle("active", open);
    ui.stimulusToggle.setAttribute("aria-expanded", String(open));
    updateChannelHint();
  });
  el("salienceInput").addEventListener("input", (event) => {
    el("salienceOutput").value = event.target.value;
    updateChannelHint();
  });
  ["impactInput", "strokeInput", "injectEnergy", "injectFatigue"].forEach((id) => {
    el(id).addEventListener("input", updateChannelHint);
  });
  el("foodSelect").addEventListener("change", updateModelHint);
  ui.composer.addEventListener("submit", sendTurn);
  ui.message.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      ui.composer.requestSubmit();
    }
  });
  ui.message.addEventListener("input", autoGrow);
  document.addEventListener("click", (event) => {
    if (!ui.switcherWrap.contains(event.target)) closeElfieMenu();
  });
  bindPreviewControls();
}

async function boot() {
  bindEvents();
  try {
    const [data, foodsData] = await Promise.all([
      api("/api/elfies"),
      api("/api/runtime/foods"),
    ]);
    state.foods = foodsData.items || [];
    state.configurationCommand = foodsData.configuration_command || "";
    populateFoodSelect();
    updateModelHint();
    state.elfies = data.items || [];
    if (!state.elfies.length) {
      showEmpty();
      return;
    }
    const remembered = localStorage.getItem("elfieLab.currentElfie");
    const first = state.elfies.find((item) => item.elfie_id === remembered) || state.elfies[0];
    await selectElfie(first.elfie_id);
  } catch (error) {
    const errorMessage = error.message.toLowerCase();
    if (error.message.includes("503") || errorMessage.includes("粮食") || errorMessage.includes("food")) {
      showError();
      return;
    }
    showToast(error.message, true);
  }
}

boot();
