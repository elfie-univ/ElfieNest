export const el = (id) => document.getElementById(id);

export const ui = {
  shell: el("labShell"),
  elfieEmpty: el("elfieEmpty"),
  elfieContent: el("elfieContent"),
  switcherWrap: el("switcherWrap"),
  elfieMenu: el("elfieMenu"),
  switcher: el("elfieSwitcher"),
  timeline: el("timeline"),
  placeholder: el("timelinePlaceholder"),
  composer: el("composer"),
  message: el("messageInput"),
  send: el("sendButton"),
  detail: el("detailPanel"),
  detailContent: el("detailContent"),
  modal: el("createModal"),
  createForm: el("createForm"),
  toast: el("toast"),
  stimulusDrawer: el("stimulusDrawer"),
  stimulusToggle: el("stimulusToggle"),
  elfieError: el("elfieError"),
};

let toastTimer;

export function showToast(message, error = false) {
  clearTimeout(toastTimer);
  ui.toast.textContent = message;
  ui.toast.style.color = error ? "var(--status-error)" : "var(--text-secondary)";
  ui.toast.hidden = false;
  toastTimer = setTimeout(() => { ui.toast.hidden = true; }, 3200);
}
