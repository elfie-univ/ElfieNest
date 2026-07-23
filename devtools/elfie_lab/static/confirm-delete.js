import { el } from "./dom.js";

let resolver = null;
let trigger = null;

export function confirmElfieDeletion(elfie) {
  if (resolver) resolver(false);
  trigger = document.activeElement;
  el("deleteElfieName").textContent = elfie.name;
  el("deleteError").hidden = true;
  el("deleteModal").hidden = false;
  requestAnimationFrame(() => el("deleteCancel").focus());
  return new Promise((resolve) => { resolver = resolve; });
}

function settle(confirmed) {
  el("deleteModal").hidden = true;
  if (!resolver) return;
  const resolve = resolver;
  resolver = null;
  resolve(confirmed);
  trigger?.focus();
  trigger = null;
}

export function bindDeleteConfirmation() {
  el("deleteClose").addEventListener("click", () => settle(false));
  el("deleteCancel").addEventListener("click", () => settle(false));
  el("deleteForm").addEventListener("submit", (event) => {
    event.preventDefault();
    settle(true);
  });
  el("deleteModal").addEventListener("click", (event) => {
    if (event.target === el("deleteModal")) settle(false);
  });
  el("deleteModal").addEventListener("keydown", (event) => {
    if (event.key === "Escape") settle(false);
  });
}
