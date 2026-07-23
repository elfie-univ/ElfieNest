import { api } from "./api.js";
import { el, showToast } from "./dom.js";
import { state } from "./store.js";

const TRAITS = [
  ["openness", "开放性"],
  ["conscientiousness", "尽责性"],
  ["extraversion", "外向性"],
  ["agreeableness", "宜人性"],
  ["neuroticism", "敏感性"],
];

function closeEditor() {
  el("personalityModal").hidden = true;
  el("personalityError").hidden = true;
}

function traitRow(key, label, value) {
  const row = document.createElement("label");
  row.className = "trait-row";
  const name = document.createElement("span");
  name.textContent = label;
  const input = document.createElement("input");
  input.type = "range";
  input.min = "0";
  input.max = "1";
  input.step = "0.01";
  input.value = String(value);
  input.dataset.trait = key;
  const output = document.createElement("output");
  output.textContent = Number(value).toFixed(2);
  input.addEventListener("input", () => { output.textContent = Number(input.value).toFixed(2); });
  row.append(name, input, output);
  return row;
}

function openEditor() {
  const values = state.session?.profile?.big_five || {};
  const rows = TRAITS.map(([key, label]) => traitRow(key, label, Number(values[key] ?? 0.5)));
  el("personalityTraitEditor").replaceChildren(...rows);
  el("personalityError").hidden = true;
  el("personalityModal").hidden = false;
}

function buildPayload() {
  return Object.fromEntries(
    [...el("personalityTraitEditor").querySelectorAll("input[data-trait]")]
      .map((input) => [input.dataset.trait, Number(input.value)]),
  );
}

export function bindPersonalityEditor(onUpdated) {
  el("editPersonality").addEventListener("click", openEditor);
  el("personalityClose").addEventListener("click", closeEditor);
  el("personalityCancel").addEventListener("click", closeEditor);
  el("personalityModal").addEventListener("click", (event) => {
    if (event.target === el("personalityModal")) closeEditor();
  });
  el("personalityForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      state.session = await api(
        `/api/elfies/${encodeURIComponent(state.currentId)}/personality`,
        { method: "PATCH", body: JSON.stringify(buildPayload()) },
      );
      onUpdated();
      closeEditor();
      showToast("人格参数已保存");
    } catch (error) {
      el("personalityError").textContent = error.message;
      el("personalityError").hidden = false;
    }
  });
}
