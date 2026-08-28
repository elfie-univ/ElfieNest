import { createHash } from "node:crypto";
import { existsSync, lstatSync, readdirSync, readFileSync } from "node:fs";
import { isAbsolute, join, relative, resolve, sep } from "node:path";

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

const GODOT_LINUX_DEDICATED_RESOURCE_PATHS = [
  "godot-linux-dedicated/ElfieNestRuntime",
  "godot-linux-dedicated/build-manifest.json",
] as const;

const PRODUCT_WEB_RESOURCE_PATHS = [
  "web/manifest.json",
  "web/index.html",
] as const;

const PACKAGED_RESOURCE_DIRECTORIES = [
  "web",
  "godot-web",
  "godot-linux-dedicated",
  "python-core",
  "management-cli",
  "config",
] as const;

export type ResourcePath = string;

export type ResourceFile = Readonly<{
  readonly size: number;
  readonly sha256: string;
}>;

export type ResourceManifest = Readonly<{
  readonly schema_version: 2;
  readonly application_version: string;
  readonly source_revision: string;
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

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isSafeResourcePath(resourcePath: string): boolean {
  if (
    resourcePath.length === 0 ||
    resourcePath.includes("\\") ||
    resourcePath.startsWith("/") ||
    /^[A-Za-z]:\//u.test(resourcePath) ||
    isAbsolute(resourcePath)
  ) {
    return false;
  }
  return resourcePath.split("/").every((part) => part !== "" && part !== "." && part !== "..");
}

function resolvedResourcePath(root: string, resourcePath: string): string | null {
  if (!isSafeResourcePath(resourcePath)) {
    return null;
  }
  const resolvedRoot = resolve(root);
  const fullPath = resolve(resolvedRoot, resourcePath);
  const relativePath = relative(resolvedRoot, fullPath);
  if (
    relativePath === "" ||
    relativePath === ".." ||
    relativePath.startsWith(`..${sep}`) ||
    isAbsolute(relativePath)
  ) {
    return null;
  }
  return fullPath;
}

function isResourceFile(value: unknown): value is ResourceFile {
  if (!isRecord(value) || Object.keys(value).some((key) => key !== "size" && key !== "sha256")) {
    return false;
  }
  return (
    Number.isSafeInteger(value["size"]) &&
    Number(value["size"]) >= 0 &&
    typeof value["sha256"] === "string" &&
    /^[0-9a-f]{64}$/u.test(value["sha256"])
  );
}

function executablePathForTarget(
  target: ResourceTarget,
  directory: "python-core" | "management-cli",
): string {
  switch (target) {
    case "darwin-arm64":
    case "darwin-x64":
    case "linux-x64":
      if (directory === "python-core") {
        return "python-core/ElfieNestCore";
      }
      return "management-cli/ElfieNestCli";
    case "win32-x64":
      if (directory === "python-core") {
        return "python-core/ElfieNestCore.exe";
      }
      return "management-cli/ElfieNestCli.exe";
    default:
      return assertNever(target);
  }
}

export function requiredResourcePathsForTarget(
  target: ResourceTarget,
): readonly ResourcePath[] {
  return [
    ...GODOT_WEB_RESOURCE_PATHS,
    ...(target === "linux-x64" ? GODOT_LINUX_DEDICATED_RESOURCE_PATHS : []),
    ...PRODUCT_WEB_RESOURCE_PATHS,
    executablePathForTarget(target, "python-core"),
    executablePathForTarget(target, "management-cli"),
  ];
}

function packagedComponentPaths(root: string): readonly ResourcePath[] {
  const resourcePaths: string[] = [];
  const visit = (directory: string, prefix: string): void => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const relativePath = `${prefix}/${entry.name}`;
      const fullPath = join(directory, entry.name);
      if (entry.isDirectory()) {
        visit(fullPath, relativePath);
      } else if (entry.isFile()) {
        resourcePaths.push(relativePath);
      }
    }
  };
  for (const component of PACKAGED_RESOURCE_DIRECTORIES) {
    const componentRoot = join(root, component);
    if (existsSync(componentRoot)) {
      visit(componentRoot, component);
    }
  }
  return resourcePaths;
}

function manifestResourcePaths(root: string, target: ResourceTarget): readonly ResourcePath[] {
  return [
    ...new Set([
      ...requiredResourcePathsForTarget(target),
      ...packagedComponentPaths(root),
    ]),
  ];
}

export function buildResourceManifest(
  root: string,
  applicationVersion: string,
  sourceRevision: string,
  target: ResourceTarget,
): ResourceManifest {
  if (!/^[0-9a-f]{40}$/u.test(sourceRevision)) {
    throw new ResourceManifestError("manifest.json", "源码 revision 无效");
  }
  const files: Record<string, ResourceFile> = {};
  for (const resourcePath of manifestResourcePaths(root, target)) {
    const fullPath = resolvedResourcePath(root, resourcePath);
    if (fullPath === null || !existsSync(fullPath)) {
      throw new ResourceManifestError(resourcePath, "资源文件不存在");
    }
    const stats = lstatSync(fullPath);
    if (!stats.isFile() || stats.isSymbolicLink()) {
      throw new ResourceManifestError(resourcePath, "资源路径不是文件");
    }
    const data = readFileSync(fullPath);
    files[resourcePath] = {
      size: data.byteLength,
      sha256: createHash("sha256").update(data).digest("hex"),
    };
  }
  return {
    schema_version: 2,
    application_version: applicationVersion,
    source_revision: sourceRevision,
    target,
    files,
  };
}

export function validateResourceManifest(
  root: string,
  manifest: ResourceManifest,
): readonly string[] {
  const errors: string[] = [];
  const expectedPaths = new Set<ResourcePath>([
    ...requiredResourcePathsForTarget(manifest.target),
    ...packagedComponentPaths(root),
  ]);
  for (const resourcePath of Object.keys(manifest.files)) {
    if (!isSafeResourcePath(resourcePath)) {
      errors.push(`${resourcePath}: 资源路径必须是安全相对路径`);
    } else if (!expectedPaths.has(resourcePath)) {
      errors.push(`${resourcePath}: manifest 包含意外条目`);
    }
  }
  for (const resourcePath of expectedPaths) {
    const expected = manifest.files[resourcePath];
    if (expected === undefined) {
      errors.push(`${resourcePath}: manifest 缺少条目`);
      continue;
    }
    const fullPath = resolvedResourcePath(root, resourcePath);
    if (fullPath === null || !existsSync(fullPath)) {
      errors.push(`${resourcePath}: 资源文件不存在`);
      continue;
    }
    const stats = lstatSync(fullPath);
    if (!stats.isFile() || stats.isSymbolicLink()) {
      errors.push(`${resourcePath}: 资源路径不是普通文件`);
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

function parseResourceManifest(text: string): ResourceManifest {
  let payload: unknown;
  try {
    payload = JSON.parse(text) as unknown;
  } catch {
    throw new ResourceManifestError("manifest.json", "不是有效 JSON");
  }
  if (!isRecord(payload)) {
    throw new ResourceManifestError("manifest.json", "根节点必须是对象");
  }
  const allowedKeys = new Set(["schema_version", "application_version", "source_revision", "target", "files"]);
  if (
    Object.keys(payload).some((key) => !allowedKeys.has(key)) ||
    payload["schema_version"] !== 2 ||
    typeof payload["application_version"] !== "string" ||
    payload["application_version"].trim() === "" ||
    typeof payload["source_revision"] !== "string" ||
    !/^[0-9a-f]{40}$/u.test(payload["source_revision"]) ||
    typeof payload["target"] !== "string" ||
    !isResourceTarget(payload["target"]) ||
    !isRecord(payload["files"])
  ) {
    throw new ResourceManifestError("manifest.json", "结构无效");
  }
  const files: Record<string, ResourceFile> = {};
  for (const [resourcePath, value] of Object.entries(payload["files"])) {
    if (!isSafeResourcePath(resourcePath)) {
      throw new ResourceManifestError(resourcePath, "资源路径必须是安全相对路径");
    }
    if (!isResourceFile(value)) {
      throw new ResourceManifestError(resourcePath, "文件条目无效");
    }
    files[resourcePath] = value;
  }
  return {
    schema_version: 2,
    application_version: payload["application_version"],
    source_revision: payload["source_revision"],
    target: payload["target"],
    files,
  };
}

export function loadAndValidateResourceManifest(
  root: string,
  applicationVersion: string,
): ResourceManifest {
  const manifestPath = join(root, "manifest.json");
  if (!existsSync(manifestPath)) {
    throw new ResourceManifestError("manifest.json", "资源清单不存在");
  }
  const manifest = parseResourceManifest(readFileSync(manifestPath, "utf8"));
  if (manifest.application_version !== applicationVersion) {
    throw new ResourceManifestError(
      "manifest.json",
      `应用版本不匹配 expected=${applicationVersion} actual=${manifest.application_version}`,
    );
  }
  const errors = validateResourceManifest(root, manifest);
  if (errors.length > 0) {
    throw new ResourceManifestError("manifest.json", errors.join("; "));
  }
  return manifest;
}
