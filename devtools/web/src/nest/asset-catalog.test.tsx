import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import index from "../../../../godot_project/nest/assembly/asset-index.json";
import { assetCategories, assetLeaves, assetPath, type AssetItem } from "./asset-catalog";
import { AssetBrowserToolbar } from "./AssetBrowserToolbar";

function category(id: string) {
  return assetCategories.find(item => item.id === id)!;
}

function folder(items: AssetItem[], id: string) {
  return items.find(item => item.id === id)!;
}

describe("formal Nest asset menu", () => {
  it("uses the formal file index for every menu entry", () => {
    expect(assetCategories).toEqual(index.fileGraph.categories);
    const leaves = assetCategories.flatMap(item => assetLeaves(item.children));
    const ids = leaves.map(item => item.id);
    const files = Object.values(index.fileGraph.entries).map(item => item.file);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(ids)).toEqual(new Set(Object.keys(index.fileGraph.entries)));
    expect(new Set(files).size).toBe(files.length);
  });

  it("keeps one bedroom layout and four complete bedroom suites", () => {
    const furniture = category("furniture");
    const layouts = folder(furniture.children, "furniture-layouts");
    expect(assetLeaves(layouts.children!).filter(item => item.id === "view:bedroom-layout"))
      .toHaveLength(1);
    const sets = folder(furniture.children, "furniture-sets");
    expect(assetLeaves(folder(sets.children!, "bedroom").children!).map(item => item.id))
      .toEqual(["view:bedroom-set-a", "view:bedroom-set-b", "view:bedroom-set-c", "view:bedroom-set-d"]);
    expect(Object.keys(index.fileGraph.entries).some(id => id.startsWith("placement:bedroom-") || id.startsWith("view:desk-") || /^source:desk-.-local$/.test(id))).toBe(false);
  });

  it("keeps the main building and its doors in one component", () => {
    expect(category("buildings").children.map(item => item.id))
      .toEqual(["source:central-building", "source:pod-building", "view:building-layout"]);
    expect(category("buildings").children[0]!.label).toBe("主楼");
  });

  it("lifts standalone courtyard and furniture layouts", () => {
    const furniture = category("furniture");
    const layouts = folder(furniture.children, "furniture-layouts");
    expect(layouts.children!.map(item => item.id)).toEqual([
      "view:bedroom-layout", "terraces", "view:central-layout-1",
      "view:central-layout-2", "view:central-layout-3",
    ]);
    expect(assetPath(furniture.children, "view:bedroom-layout"))
      .toEqual(["furniture-layouts", "view:bedroom-layout"]);
    expect(assetPath(furniture.children, "view:terrace-layout-01"))
      .toEqual(["furniture-layouts", "terraces", "view:terrace-layout-01"]);
    expect(assetPath(furniture.children, "view:central-living"))
      .toEqual(["furniture-sets", "main-1", "view:central-living"]);
    expect(assetPath(furniture.children, "source:central-living-local"))
      .toEqual(["furniture-shared", "main-1", "source:central-living-local"]);

    const court = category("courtyard");
    expect(folder(court.children, "courtyard-overview").children!.map(item => item.id))
      .toEqual(["view:courtyard-covered", "view:courtyard-layout"]);
    expect(assetPath(court.children, "view:courtyard-covered"))
      .toEqual(["courtyard-overview", "view:courtyard-covered"]);
    expect(assetPath(court.children, "view:courtyard-ground"))
      .toEqual(["courtyard-areas", "view:courtyard-ground"]);
    expect(assetPath(court.children, "view:meadow-layout"))
      .toEqual(["courtyard-areas", "view:meadow-layout"]);
    expect(category("total").children.map(item => item.id)).toEqual(["view:estate-layout"]);
  });

  it("offers covered and uncovered gardens with the cover under ground parts", () => {
    const court = category("courtyard");
    const overview = folder(court.children, "courtyard-overview");
    expect(assetLeaves(overview.children!).map(item => item.id))
      .toEqual(["view:courtyard-covered", "view:courtyard-layout"]);
    const parts = folder(court.children, "courtyard-parts");
    expect(assetLeaves(folder(parts.children!, "ground").children!).some(item => item.id === "source:environment")).toBe(true);
    expect(assetPath(court.children, "source:environment").slice(0, 2)).toEqual(["courtyard-parts", "ground"]);
  });

  it("shows cross-area plants once in the shared category", () => {
    const parts = folder(category("courtyard").children, "courtyard-parts");
    expect(parts.children!.map(item => item.label)).toEqual(["地面", "森林", "水榭", "草原", "共享"]);
    expect(assetLeaves(folder(parts.children!, "shared").children!).map(item => item.id))
      .toEqual(["source:plant-library", "source:shore-stones"]);
    expect(assetPath(category("courtyard").children, "source:forest-foliage"))
      .toEqual(["courtyard-parts", "forest", "source:forest-foliage"]);
  });

  it("renders the selected shared asset in the existing toolbar", () => {
    const item = assetLeaves(category("courtyard").children).find(item => item.id === "source:forest-foliage")!;
    const html = renderToStaticMarkup(<AssetBrowserToolbar selected={item} select={() => {}} reset={() => {}} ready />);
    expect(html).toContain('aria-label="资产分类"');
    expect(html).toContain('aria-label="具体资产"');
    expect(html).toContain("ant-cascader");
    expect(html).not.toContain('disabled=""');
  });
});
