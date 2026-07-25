import { describe, expect, it } from "vitest";

import { buildStateInjection } from "./stimulus";

describe("Elfie Lab debug state injection", () => {
  it("sends nothing until the explicit state override switch is enabled", () => {
    expect(buildStateInjection(false, {}, false, false)).toEqual({});
  });

  it("keeps emotion overrides nested under the API emotions field", () => {
    expect(buildStateInjection(
      true,
      { energy: "42", happiness: "80", fear: "15" },
      true,
      true,
    )).toEqual({
      energy: 42,
      is_sleeping: true,
      emotions: { happiness: 80, fear: 15 },
    });
  });
});
