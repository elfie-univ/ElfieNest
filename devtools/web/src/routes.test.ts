import { describe, expect, it } from "vitest";

import { labKinds } from "./lab-kind";
import { devtoolsRoutes, elfieIdFromSearch, routeFromPath, routeHref, routePath } from "./routes";

describe("Developer Tools 页面路由", () => {
  it("从 Memory Debug 查询参数读取当前精灵", () => {
    expect(elfieIdFromSearch("?elfie_id=96474648")).toBe("96474648");
    expect(elfieIdFromSearch("?elfie_id=%20")).toBeUndefined();
  });

  it("将 Elfie 页面映射到稳定地址", () => {
    expect(routeFromPath(labKinds.elfie, "/elfie/experiment")).toBe(devtoolsRoutes.elfieExperiment);
    expect(routeFromPath(labKinds.elfie, "/elfie/evaluations")).toBe(devtoolsRoutes.elfieEvaluations);
    expect(routeFromPath(labKinds.elfie, "/elfie/evaluations/")).toBe(devtoolsRoutes.elfieEvaluations);
    expect(routeFromPath(labKinds.elfie, "/elfie/memory-audit")).toBe(devtoolsRoutes.elfieMemoryAudit);
    expect(routeFromPath(labKinds.elfie, "/elfie/memory-audit/")).toBe(devtoolsRoutes.elfieMemoryAudit);
    expect(routeFromPath(labKinds.elfie, "/elfie/memory-debug")).toBe(devtoolsRoutes.elfieMemoryDebugWorkspace);
    expect(routeFromPath(labKinds.elfie, "/elfie/memory-debug/")).toBe(devtoolsRoutes.elfieMemoryDebugWorkspace);
    expect(routeFromPath(labKinds.elfie, "/")).toBe(devtoolsRoutes.elfieExperiment);
  });

  it("Nest 服务只进入精灵巢页面", () => {
    expect(routeFromPath(labKinds.nest, "/nest/experiment")).toBe(devtoolsRoutes.nestExperiment);
    expect(routeFromPath(labKinds.nest, "/")).toBe(devtoolsRoutes.nestExperiment);
  });

  it("统一服务按路径识别开发工具页面", () => {
    expect(routeFromPath(labKinds.unified, "/elfie/experiment")).toBe(devtoolsRoutes.elfieExperiment);
    expect(routeFromPath(labKinds.unified, "/elfie/evaluations")).toBe(devtoolsRoutes.elfieEvaluations);
    expect(routeFromPath(labKinds.unified, "/elfie/memory-audit")).toBe(devtoolsRoutes.elfieMemoryAudit);
    expect(routeFromPath(labKinds.unified, "/elfie/memory-audit/")).toBe(devtoolsRoutes.elfieMemoryAudit);
    expect(routeFromPath(labKinds.unified, "/elfie/memory-debug")).toBe(devtoolsRoutes.elfieMemoryDebugWorkspace);
    expect(routeFromPath(labKinds.unified, "/elfie/memory-debug/")).toBe(devtoolsRoutes.elfieMemoryDebugWorkspace);
    expect(routeFromPath(labKinds.unified, "/nest/experiment")).toBe(devtoolsRoutes.nestExperiment);
  });

  it("为开发工具页面暴露可读的路径", () => {
    expect(routePath(devtoolsRoutes.elfieExperiment)).toBe("/elfie/experiment");
    expect(routePath(devtoolsRoutes.elfieEvaluations)).toBe("/elfie/evaluations");
    expect(routePath(devtoolsRoutes.elfieMemoryAudit)).toBe("/elfie/memory-audit");
    expect(routePath(devtoolsRoutes.elfieMemoryDebugWorkspace)).toBe("/elfie/memory-debug");
    expect(routePath(devtoolsRoutes.nestExperiment)).toBe("/nest/experiment");
  });

  it("统一服务切换时不改端口", () => {
    const location = { href: "http://127.0.0.1:19001/elfie/experiment" } as Location;
    expect(routeHref(devtoolsRoutes.nestExperiment, labKinds.unified, location)).toBe("/nest/experiment");
    expect(routeHref(devtoolsRoutes.elfieEvaluations, labKinds.unified, location)).toBe("/elfie/evaluations");
  });
});
