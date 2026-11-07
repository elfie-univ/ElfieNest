import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StaticAssetReview } from "./StaticAssetReview";

describe("Nest asset preview modes", () => {
  it("keeps the scene and asset views without the retired comparison page", () => {
    const html = renderToStaticMarkup(<StaticAssetReview />);
    expect(html).toContain(">整体场景</button>");
    expect(html).toContain(">单件资产</button>");
    expect(html).not.toContain("回拼对照");
    expect(html).not.toContain("原版 V044");
    expect(html).not.toContain("对照机位");
    expect(html).not.toContain("像素一致");
  });
});
