import { readdir, readFile, copyFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const distAssets = fileURLToPath(new URL("../.vitepress/dist/assets/", import.meta.url));
const assetNames = await readdir(distAssets);
let restored = 0;

for (const assetName of assetNames) {
  if (!assetName.endsWith(".lean.js")) continue;

  const leanPath = join(distAssets, assetName);
  const fullPath = join(distAssets, assetName.replace(/\.lean\.js$/, ".js"));
  const fullSource = await readFile(fullPath, "utf8");

  if (!/(home-download|story-scroll|data-story-scroll)/.test(fullSource)) continue;

  await copyFile(fullPath, leanPath);
  restored += 1;
}

console.log(`Restored ${restored} custom client page module(s).`);
