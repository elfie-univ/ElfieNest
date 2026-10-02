import { describe, expect, it } from "vitest";

import {
  creationAgeError,
  createSubmissionGate,
  detailTitle,
  formatSignedDelta,
  latestSuccessfulFoodKey,
  randomCreationValues,
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
    expect(creationAgeError("0")).toBe("年龄必须是 2 到 20 岁之间的整数");
    expect(creationAgeError("-1")).toBe("年龄必须是 2 到 20 岁之间的整数");
    expect(creationAgeError("1")).toBe("年龄必须是 2 到 20 岁之间的整数");
    expect(creationAgeError("not-a-number")).toBe("年龄必须是 2 到 20 岁之间的整数");
    expect(creationAgeError("2.5")).toBe("年龄必须是 2 到 20 岁之间的整数");
    expect(creationAgeError("23")).toBe("年龄必须是 2 到 20 岁之间的整数");
    expect(creationAgeError("15", "saevi")).toBeNull();
    expect(creationAgeError("16", "saevi")).toBe("年龄必须是 2 到 15 岁之间的整数");
  });

  it("prepares concrete creation values before advanced controls are opened", () => {
    const low = randomCreationValues("tovren", () => 0);
    const high = randomCreationValues("saevi", () => 0.999999);
    expect(low).toEqual({
      age: 2,
      gender: "female",
      bigFive: { openness: 0.2, conscientiousness: 0.2, extraversion: 0.2, agreeableness: 0.2, neuroticism: 0.2 },
    });
    expect(high.age).toBe(15);
    expect(high.gender).toBe("male");
    expect(Object.values(high.bigFive)).toEqual([0.8, 0.8, 0.8, 0.8, 0.8]);
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
    expect(selectReadyFoodAfterLoad("", foods, "mock")).toBe("mock");
  });

  it("restores the latest successful Food when a session reloads", () => {
    expect(latestSuccessfulFoodKey([
      { food_key: "failed", result: { success: false } },
      { food_key: "working", result: { success: true } },
      { food_key: "missing", result: { success: false } },
    ])).toBe("working");
    expect(latestSuccessfulFoodKey([{ result: { success: false } }])).toBe("");
  });
});
