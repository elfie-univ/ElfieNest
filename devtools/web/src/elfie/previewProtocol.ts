export type PreviewRequest = Readonly<{
  readonly action: string;
  readonly turnId?: string;
  readonly intentId?: string;
  readonly elfieId?: string;
}>;

export function clampPreviewDelta(value: number, limit: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(-limit, Math.min(limit, value));
}

export function orbitButtonDelta(direction: "left" | "right"): Readonly<{
  readonly x: number;
  readonly y: number;
}> {
  return { x: direction === "left" ? 0.28 : -0.28, y: 0 };
}

export function boundedPreviewPayload(
  action: string,
  payload: Readonly<Record<string, unknown>>,
): Readonly<Record<string, unknown>> {
  if (action === "zoom") {
    return { ...payload, delta: clampPreviewDelta(Number(payload.delta), 0.5) };
  }
  if (action !== "orbit" && action !== "pan") return payload;
  const delta = payload.delta;
  if (typeof delta !== "object" || delta === null) return payload;
  const x = "x" in delta && typeof delta.x === "number" ? delta.x : 0;
  const y = "y" in delta && typeof delta.y === "number" ? delta.y : 0;
  const limit = action === "orbit" ? 0.35 : 0.25;
  return {
    ...payload,
    delta: {
      x: clampPreviewDelta(x, limit),
      y: clampPreviewDelta(y, limit),
    },
  };
}

export function buildPreviewCommand(
  requestId: string,
  action: string,
  payload: Readonly<Record<string, unknown>>,
): Readonly<Record<string, unknown>> {
  return {
    channel: "elfie-lab",
    action,
    request_id: requestId,
    payload: boundedPreviewPayload(action, payload),
  };
}

export function createPreviewRequestRegistry(): {
  readonly add: (id: string, request: PreviewRequest) => void;
  readonly complete: (id: string, retain?: boolean) => PreviewRequest | undefined;
} {
  const pending = new Map<string, PreviewRequest>();
  return {
    add(id, request) {
      pending.set(id, request);
    },
    complete(id, retain = false) {
      const request = pending.get(id);
      if (!retain) pending.delete(id);
      return request;
    },
  };
}
