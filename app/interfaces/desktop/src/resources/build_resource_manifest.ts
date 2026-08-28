import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { join } from "node:path";

import {
  ResourceManifestError,
  ResourceTargetError,
  buildResourceManifest,
  isResourceTarget,
} from "./resource_manifest.js";

const target = process.argv[4] ?? process.env.ELFIENEST_TARGET;
const projectRoot = join(process.cwd(), "..", "..", "..");
const sourceRevision =
  process.argv[5] ??
  process.env.ELFIENEST_SOURCE_REVISION ??
  execFileSync("git", ["rev-parse", "HEAD"], {
    cwd: projectRoot,
    encoding: "utf8",
  }).trim();

try {
  if (target === undefined || !isResourceTarget(target)) {
    throw new ResourceTargetError(target ?? "<missing>");
  }
  const resourcesRoot =
    process.argv[2] ??
    join(process.cwd(), "..", "..", "..", "build", "staging", target, "resources");
  const outputPath = process.argv[3] ?? join(resourcesRoot, "manifest.json");
  const manifest = buildResourceManifest(
    resourcesRoot,
    "0.1.0-beta.2",
    sourceRevision,
    target,
  );
  writeFileSync(outputPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  console.log(`已生成资源 manifest: ${outputPath}`);
} catch (error: unknown) {
  if (
    error instanceof ResourceManifestError ||
    error instanceof ResourceTargetError
  ) {
    console.error(`资源 manifest 生成失败: ${error.message}`);
    process.exitCode = 1;
  } else {
    throw error;
  }
}
