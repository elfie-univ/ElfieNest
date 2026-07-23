import { el } from "./dom.js";

let previewRequestSequence = 0;
const pendingPreviewRequests = new Map();
const clampPreviewDelta = (value, limit) => Math.max(-limit, Math.min(limit, Number(value) || 0));
const nextPreviewRequestId = () => `preview-${Date.now().toString(36)}-${++previewRequestSequence}`;

export function sendPreview(action, payload = {}) {
  const target = el("appearanceFrame").contentWindow;
  if (!target || typeof target.elfieLabEnqueue !== "function") return null;
  const requestId = nextPreviewRequestId();
  pendingPreviewRequests.set(requestId, { action, payload });
  target.elfieLabEnqueue(JSON.stringify({
    channel: "elfie-lab", action, request_id: requestId, payload,
  }));
  return requestId;
}

export function completePreviewRequest(requestId, { retain = false } = {}) {
  const pending = pendingPreviewRequests.get(requestId);
  if (!retain) pendingPreviewRequests.delete(requestId);
  return pending;
}

export function orbitPreview(x, y = 0) { return sendPreview("orbit", { delta: { x: clampPreviewDelta(x, 0.35), y: clampPreviewDelta(y, 0.35) } }); }
export function panPreview(x, y = 0) { return sendPreview("pan", { delta: { x: clampPreviewDelta(x, 0.25), y: clampPreviewDelta(y, 0.25) } }); }
export function zoomPreview(delta) { return sendPreview("zoom", { delta: clampPreviewDelta(delta, 0.5) }); }
export function focusPreview(target) { return ["actor", "body", "head"].includes(target) ? sendPreview("focus", { target }) : null; }
export function resetPreview() { return sendPreview("reset"); }
export function capturePreview(elfieId) {
  return typeof elfieId === "string" && elfieId
    ? sendPreview("capture", { elfie_id: elfieId })
    : null;
}
export function previewIntentPreview(intent) {
  if (!intent || !["motion", "expression"].includes(intent.type) || !intent.intent_id) return null;
  const value = intent.type === "motion" ? intent.motion : intent.expression;
  return typeof value === "string" && value.trim() ? sendPreview("preview_intent", { intent }) : null;
}
