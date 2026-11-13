import catalog from "../../../../godot_project/nest/assembly/asset-index.json";

export type AssetItem = { id: string; label: string; preview?: string; artifact?: string; children?: AssetItem[] };
export type AssetCategory = AssetItem & { color: string; children: AssetItem[] };
export const assetCategories = catalog.fileGraph.categories as AssetCategory[];

export function assetLeaves(items: readonly AssetItem[]): AssetItem[] {
  return items.flatMap(item => item.children ? assetLeaves(item.children) : [item]);
}
export function assetPath(items: readonly AssetItem[], id: string): string[] {
  for (const item of items) {
    if (item.id === id) return [id];
    const child = item.children ? assetPath(item.children, id) : [];
    if (child.length) return [item.id, ...child];
  }
  return [];
}
type AssetOption = { value: string; label: string; children?: AssetOption[] };
export function assetOptions(items: readonly AssetItem[]): AssetOption[] {
  return items.map(item => ({ value: item.id, label: item.label, ...(item.children ? { children: assetOptions(item.children) } : {}) }));
}
