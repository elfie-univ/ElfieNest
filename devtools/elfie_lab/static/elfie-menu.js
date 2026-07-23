import { api } from "./api.js";
import { showToast, ui } from "./dom.js";
import { createPortraitThumbnail } from "./portrait.js";
import { state } from "./store.js";

const callbacks = {
  onSelect: async () => {},
  onCreate: () => {},
  onConfirmDelete: async (elfie) => window.confirm(
    `将“${elfie.name}”移入回收站？\n\n当前调试记录和头像会一并移入，可由开发者恢复。`,
  ),
  onDeleted: () => showToast("精灵已移入回收站"),
  onDeleteError: (error) => showToast(error.message, true),
  onEmpty: () => {
    ui.elfieEmpty.hidden = false;
    ui.elfieContent.hidden = true;
    ui.switcherWrap.hidden = true;
    ui.message.disabled = true;
    ui.send.disabled = true;
  },
};
let pendingDeleteId = null;

export function configureElfieMenu(config) {
  Object.keys(callbacks).forEach((name) => {
    if (typeof config[name] === "function") callbacks[name] = config[name];
  });
}

export async function requestElfieDeletion(elfie) {
  try {
    if (!await callbacks.onConfirmDelete(elfie)) return;
  } catch (error) {
    callbacks.onDeleteError(error);
    return;
  }

  pendingDeleteId = elfie.elfie_id;
  renderElfieMenu();
  let result;
  try {
    result = await api(`/api/elfies/${encodeURIComponent(elfie.elfie_id)}`, {
      method: "DELETE",
    });
  } catch (error) {
    pendingDeleteId = null;
    renderElfieMenu();
    callbacks.onDeleteError(error);
    return;
  }

  state.elfies = state.elfies.filter((item) => item.elfie_id !== elfie.elfie_id);
  try {
    if (state.currentId === elfie.elfie_id) {
      state.currentId = null;
      state.session = null;
      localStorage.removeItem("elfieLab.currentElfie");
      if (result.next_elfie_id) {
        await callbacks.onSelect(result.next_elfie_id);
      } else {
        callbacks.onEmpty();
      }
    }
    callbacks.onDeleted(result);
    closeElfieMenu();
  } catch (error) {
    callbacks.onDeleteError(error);
  } finally {
    pendingDeleteId = null;
    renderElfieMenu();
  }
}

function createElfieRow(elfie) {
  const row = document.createElement("div");
  row.className = "elfie-menu-row";
  row.style.cssText = "display:flex;align-items:center;gap:4px";
  const selectButton = document.createElement("button");
  selectButton.type = "button";
  selectButton.classList.toggle("active", elfie.elfie_id === state.currentId);
  selectButton.setAttribute("role", "menuitem");
  selectButton.setAttribute("aria-current", elfie.elfie_id === state.currentId ? "true" : "false");
  selectButton.append(createPortraitThumbnail(elfie));
  const name = document.createElement("span");
  name.textContent = `${elfie.name} · ${elfie.species_id === "dog" ? "小狗" : "狐狸"}`;
  name.style.cssText = "min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
  selectButton.append(name);
  selectButton.addEventListener("click", () => callbacks.onSelect(elfie.elfie_id));

  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.textContent = "⌫";
  deleteButton.title = `删除${elfie.name}`;
  deleteButton.setAttribute("aria-label", `删除${elfie.name}`);
  deleteButton.disabled = pendingDeleteId !== null;
  deleteButton.style.cssText = "width:32px;min-height:32px;flex:0 0 32px;justify-content:center;color:var(--status-error);font-size:17px";
  deleteButton.addEventListener("click", (event) => {
    event.stopPropagation();
    requestElfieDeletion(elfie);
  });
  row.append(selectButton, deleteButton);
  return row;
}

export function renderElfieMenu() {
  const rows = state.elfies.map(createElfieRow);
  const rule = document.createElement("hr");
  const create = document.createElement("button");
  create.type = "button";
  create.textContent = "＋  新建测试精灵";
  create.addEventListener("click", callbacks.onCreate);
  ui.elfieMenu.replaceChildren(...rows, rule, create);
}

export function toggleElfieMenu() {
  const open = ui.elfieMenu.hidden;
  ui.elfieMenu.hidden = !open;
  ui.switcher.setAttribute("aria-expanded", String(open));
}

export function closeElfieMenu() {
  ui.elfieMenu.hidden = true;
  ui.switcher.setAttribute("aria-expanded", "false");
}
