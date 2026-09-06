import { describe, expect, it } from "vitest";

import {
  creationAgeError,
  createSubmissionGate,
  detailTitle,
  formatSignedDelta,
  selectReadyFoodAfterLoad,
  selectElfieIdAfterLoad,
} from "./viewModel";

describe("Elfie Lab view model", () => {
  it("formats floating point state deltas for people instead of exposing binary noise", () => {
    expect(formatSignedDelta(100, 99.97)).toBe("-0.03");
    expect(formatSignedDelta(0, 0.01)).toBe("+0.01");
    expect(formatSignedDelta(7, 7)).toBe("0");
  });

  it("keeps the selected message focus in the right-hand detail heading", () => {
    expect(detailTitle("input", "摘要")).toBe("输入与感知");
    expect(detailTitle("chain", "链路")).toBe("完整处理链路");
    expect(detailTitle("output", "摘要")).toBe("决策与执行");
  });

  it("rejects non-positive and non-numeric adoption ages before sending", () => {
    expect(creationAgeError("0")).toBe("年龄必须是 1 到 20 岁之间的整数");
    expect(creationAgeError("-1")).toBe("年龄必须是 1 到 20 岁之间的整数");
    expect(creationAgeError("not-a-number")).toBe("年龄必须是 1 到 20 岁之间的整数");
    expect(creationAgeError("2.5")).toBe("年龄必须是 1 到 20 岁之间的整数");
    expect(creationAgeError("23")).toBe("年龄必须是 1 到 20 岁之间的整数");
    expect(creationAgeError("15", "fox")).toBeNull();
    expect(creationAgeError("16", "fox")).toBe("年龄必须是 1 到 15 岁之间的整数");
  });

  it("ignores a second creation submission until the first one finishes", () => {
    const gate = createSubmissionGate();
    expect(gate.enter()).toBe(true);
    expect(gate.enter()).toBe(false);
    gate.leave();
    expect(gate.enter()).toBe(true);
  });

  it("does not fall back to a deleted current Elfie when deletion returns null", () => {
    expect(selectElfieIdAfterLoad(null, "deleted", undefined)).toBeUndefined();
    expect(selectElfieIdAfterLoad(null, "deleted", "remaining")).toBe("remaining");
    expect(selectElfieIdAfterLoad(undefined, "current", "first")).toBe("current");
  });

  it("selects the first runnable Food instead of a disabled system placeholder", () => {
    const foods = [
      { key: "food_emergency", ready_for_attempt: false },
      { key: "mock", ready_for_attempt: true },
    ];

    expect(selectReadyFoodAfterLoad("", foods)).toBe("mock");
    expect(selectReadyFoodAfterLoad("food_emergency", foods)).toBe("mock");
    expect(selectReadyFoodAfterLoad("mock", foods)).toBe("mock");
  });
});
