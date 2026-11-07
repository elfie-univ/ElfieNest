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
    const bedroom = folder(layouts.children!, "bedroom");
    expect(assetLeaves(bedroom.children!).map(item => item.id)).toEqual(["view:bedroom-layout"]);
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
      .toEqual(["source:plant-library", "source:forest-wood", "source:forest-foliage", "source:shore-stones"]);
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
