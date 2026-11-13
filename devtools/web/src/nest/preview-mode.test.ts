import { describe, expect, it } from "vitest";
import { isAssetMode, modeUrl } from "./preview-mode";

describe("Nest Lab preview mode URL", () => {
  it("defaults to the scene and uses only mode=asset for assets", () => {
    expect(isAssetMode("")).toBe(false);
    expect(isAssetMode("?mode=asset")).toBe(true);
    expect(isAssetMode("?mode=unknown")).toBe(false);
    expect(modeUrl("http://localhost/nest/experiment", true)).toBe("http://localhost/nest/experiment?mode=asset");
    expect(modeUrl("http://localhost/nest/experiment?mode=asset", false)).toBe("http://localhost/nest/experiment");
    expect(modeUrl("http://localhost/nest/experiment?asset_review=bedroom-pilot", true)).toBe("http://localhost/nest/experiment?mode=asset");
  });
});
