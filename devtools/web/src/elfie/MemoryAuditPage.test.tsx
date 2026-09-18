import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { MemoryAuditPage } from "./MemoryAuditPage";

describe("独立记忆审计台", () => {
  it("展示真实审计页的三个操作入口", () => {
    const markup = renderToStaticMarkup(<MemoryAuditPage />);

    expect(markup).toContain("记忆审计台");
    expect(markup).toContain("全部 Node 与 Assertion；Evidence 在选中关系后查看");
    expect(markup).toContain("添加 Episode");
    expect(markup).toContain("检索");
    expect(markup).toContain("真实 SQLite 数据");
  });
});
