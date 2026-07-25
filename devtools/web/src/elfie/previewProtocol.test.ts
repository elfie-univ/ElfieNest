import { describe, expect, it } from "vitest";

import {
  buildPreviewCommand,
  clampPreviewDelta,
  createPreviewRequestRegistry,
} from "./previewProtocol";

describe("Elfie Lab preview protocol", () => {
  it("bounds direct manipulation gestures before they reach Godot", () => {
    expect(clampPreviewDelta(2, 0.35)).toBe(0.35);
    expect(clampPreviewDelta(-2, 0.25)).toBe(-0.25);
    expect(clampPreviewDelta(Number.NaN, 0.5)).toBe(0);
  });

  it("uses the typed payload envelope expected by the Godot controller", () => {
    expect(buildPreviewCommand("request-1", "orbit", {
      delta: { x: 0.1, y: -0.1 },
    })).toEqual({
      channel: "elfie-lab",
      action: "orbit",
      request_id: "request-1",
      payload: { delta: { x: 0.1, y: -0.1 } },
    });
  });

  it("can retain capture ownership until portrait delivery", () => {
    const requests = createPreviewRequestRegistry();
    requests.add("capture-1", { action: "capture", elfieId: "elfie-a" });

    expect(requests.complete("capture-1", true)).toEqual({
      action: "capture",
      elfieId: "elfie-a",
    });
    expect(requests.complete("capture-1")).toEqual({
      action: "capture",
      elfieId: "elfie-a",
    });
    expect(requests.complete("capture-1")).toBeUndefined();
  });
});
