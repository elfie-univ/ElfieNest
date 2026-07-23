import { api } from "./api.js";
import { el, showToast, ui } from "./dom.js";
import { closeElfieMenu } from "./elfie-menu.js";
import { state } from "./store.js";

let onCreated = () => {};
let creating = false;

export function configureCreateElfie(callback) {
  onCreated = callback;
}

export function openCreate() {
  closeElfieMenu();
  ui.createForm.reset();
  const submit = ui.createForm.querySelector('button[type="submit"]');
  submit.disabled = false;
  submit.textContent = "创建并切换";
  el("createError").hidden = true;
  ui.modal.hidden = false;
  requestAnimationFrame(() => el("createName").focus());
}

export function closeCreate() {
  ui.modal.hidden = true;
  el("createError").hidden = true;
}

export function buildCreateElfiePayload() {
  const ageYears = Number(el("createAgeYears").value);
  if (!Number.isFinite(ageYears) || ageYears <= 0) throw new Error("年龄必须大于 0");
  return {
    name: el("createName").value.trim(),
    species_id: el("createSpecies").value,
    age_years: ageYears,
    description: el("createDescription").value.trim(),
    appearance_description: el("createAppearanceDescription").value.trim(),
    personality_description: el("createPersonalityDescription").value.trim(),
  };
}

export async function createElfie(event) {
  event.preventDefault();
  if (creating) return;
  creating = true;
  const errorBox = el("createError");
  const submit = ui.createForm.querySelector('button[type="submit"]');
  submit.disabled = true;
  submit.textContent = "创建中…";
  errorBox.hidden = true;
  try {
    const session = await api("/api/elfies", {
      method: "POST",
      body: JSON.stringify(buildCreateElfiePayload()),
    });
    const data = await api("/api/elfies");
    state.elfies = data.items || [];
    await onCreated(session.elfie_id);
    closeCreate();
    showToast("测试精灵已创建");
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  } finally {
    creating = false;
    submit.disabled = false;
    submit.textContent = "创建并切换";
  }
}
