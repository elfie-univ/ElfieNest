export function isAssetMode(search: string): boolean {
  return new URLSearchParams(search).get("mode") === "asset";
}

export function modeUrl(current: string, asset: boolean): string {
  const url = new URL(current);
  url.searchParams.delete("asset_review");
  if (asset) url.searchParams.set("mode", "asset");
  else url.searchParams.delete("mode");
  return url.toString();
}
