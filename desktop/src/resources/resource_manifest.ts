import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

export const REQUIRED_RESOURCE_PATHS = [
  "godot-web/elfienest.html",
  "godot-web/elfienest.js",
  "godot-web/elfienest.wasm",
  "godot-web/elfienest.pck",
  "python-core/darwin/ElfieNestCore",
  "python-core/win32/ElfieNestCore.exe",
  "python-core/linux/ElfieNestCore",
  "ollama/darwin/ollama",
  "ollama/win32/ollama.exe",
  "ollama/linux/ollama",
] as const;

export type ResourcePath = (typeof REQUIRED_RESOURCE_PATHS)[number];

export type ResourceFile = Readonly<{
  readonly size: number;
  readonly sha256: string;
}>;

export type ResourceManifest = Readonly<{
  readonly schema_version: 1;
  readonly application_version: string;
  readonly files: Readonly<Record<string, ResourceFile>>;
}>;

export class ResourceManifestError extends Error {
  readonly name = "ResourceManifestError";

  constructor(readonly resourcePath: string, message: string) {
    super(`${resourcePath}: ${message}`);
  }
}

export function buildResourceManifest(
  root: string,
  applicationVersion: string,
): ResourceManifest {
  const files: Record<string, ResourceFile> = {};
  for (const resourcePath of REQUIRED_RESOURCE_PATHS) {
    const fullPath = join(root, resourcePath);
    if (!existsSync(fullPath)) {
      throw new ResourceManifestError(resourcePath, "资源文件不存在");
    }
    const stats = statSync(fullPath);
    if (!stats.isFile()) {
      throw new ResourceManifestError(resourcePath, "资源路径不是文件");
    }
    const data = readFileSync(fullPath);
    files[resourcePath] = {
      size: data.byteLength,
      sha256: createHash("sha256").update(data).digest("hex"),
    };
  }
  return {
    schema_version: 1,
    application_version: applicationVersion,
    files,
  };
}

export function validateResourceManifest(
  root: string,
  manifest: ResourceManifest,
): readonly string[] {
  const errors: string[] = [];
  for (const resourcePath of REQUIRED_RESOURCE_PATHS) {
    const expected = manifest.files[resourcePath];
    const fullPath = join(root, resourcePath);
    if (expected === undefined) {
      errors.push(`${resourcePath}: manifest 缺少条目`);
      continue;
    }
    if (!existsSync(fullPath)) {
      errors.push(`${resourcePath}: 资源文件不存在`);
      continue;
    }
    const data = readFileSync(fullPath);
    const actualHash = createHash("sha256").update(data).digest("hex");
    if (data.byteLength !== expected.size) {
      errors.push(`${resourcePath}: size 不匹配`);
    }
    if (actualHash !== expected.sha256) {
      errors.push(`${resourcePath}: sha256 不匹配`);
    }
  }
  return errors;
}
