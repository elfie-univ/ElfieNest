import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

export const SUPPORTED_RESOURCE_TARGETS = [
  "darwin-arm64",
  "darwin-x64",
  "win32-x64",
  "linux-x64",
] as const;

export type ResourceTarget = (typeof SUPPORTED_RESOURCE_TARGETS)[number];

const GODOT_WEB_RESOURCE_PATHS = [
  "godot-web/elfienest.html",
  "godot-web/elfienest.js",
  "godot-web/elfienest.wasm",
  "godot-web/elfienest.pck",
] as const;

export type ResourcePath = string;

export type ResourceFile = Readonly<{
  readonly size: number;
  readonly sha256: string;
}>;

export type ResourceManifest = Readonly<{
  readonly schema_version: 1;
  readonly application_version: string;
  readonly target: ResourceTarget;
  readonly files: Readonly<Record<string, ResourceFile>>;
}>;

export class ResourceManifestError extends Error {
  readonly name = "ResourceManifestError";

  constructor(readonly resourcePath: string, message: string) {
    super(`${resourcePath}: ${message}`);
  }
}

export class ResourceTargetError extends Error {
  readonly name = "ResourceTargetError";

  constructor(readonly target: string) {
    super(`不支持的资源 target: ${target}`);
  }
}

function assertNever(value: never): never {
  throw new ResourceTargetError(String(value));
}

export function isResourceTarget(target: string): target is ResourceTarget {
  return SUPPORTED_RESOURCE_TARGETS.some((supported) => supported === target);
}

function executablePathForTarget(
  target: ResourceTarget,
  directory: "python-core" | "ollama",
): string {
  switch (target) {
    case "darwin-arm64":
    case "darwin-x64":
    case "linux-x64":
      return directory === "python-core"
        ? "python-core/ElfieNestCore"
        : "ollama/ollama";
    case "win32-x64":
      return directory === "python-core"
        ? "python-core/ElfieNestCore.exe"
        : "ollama/ollama.exe";
    default:
      return assertNever(target);
  }
}

export function requiredResourcePathsForTarget(
  target: ResourceTarget,
): readonly ResourcePath[] {
  return [
    ...GODOT_WEB_RESOURCE_PATHS,
    executablePathForTarget(target, "python-core"),
    executablePathForTarget(target, "ollama"),
  ];
}

export function buildResourceManifest(
  root: string,
  applicationVersion: string,
  target: ResourceTarget,
): ResourceManifest {
  const files: Record<string, ResourceFile> = {};
  for (const resourcePath of requiredResourcePathsForTarget(target)) {
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
    target,
    files,
  };
}

export function validateResourceManifest(
  root: string,
  manifest: ResourceManifest,
): readonly string[] {
  const errors: string[] = [];
  for (const resourcePath of requiredResourcePathsForTarget(manifest.target)) {
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
