import { writeFileSync } from "node:fs";
import { join } from "node:path";

import {
  ResourceManifestError,
  buildResourceManifest,
} from "./resource_manifest.js";

const resourcesRoot = process.argv[2] ?? join(process.cwd(), "resources");
const outputPath = process.argv[3] ?? join(resourcesRoot, "manifest.json");

try {
  const manifest = buildResourceManifest(resourcesRoot, "0.1.0");
  writeFileSync(outputPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  console.log(`已生成资源 manifest: ${outputPath}`);
} catch (error: unknown) {
  if (error instanceof ResourceManifestError) {
    console.error(`资源 manifest 生成失败: ${error.message}`);
    process.exitCode = 1;
  } else {
    throw error;
  }
}
