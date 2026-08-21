import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { readFile, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";

const HELPER_TIMEOUT_MS = 30_000;
const HELPER_APP = "WifiAccessHelper.app";

export type DesktopWifiAccessStatus =
  | "available"
  | "permission_denied"
  | "location_services_disabled"
  | "ssid_unavailable"
  | "permission_unknown"
  | "helper_timeout"
  | "helper_unavailable"
  | "unsupported";

export type DesktopWifiAccessResult = Readonly<{
  status: DesktopWifiAccessStatus;
  network_name: string | null;
}>;

type HelperResponse = Readonly<{
  status: string;
  network_name?: unknown;
}>;

export async function readCurrentWifiName(options: Readonly<{
  platform: NodeJS.Platform;
  resourcesPath: string;
}>): Promise<DesktopWifiAccessResult> {
  if (options.platform !== "darwin") {
    return { status: "unsupported", network_name: null };
  }

  const helper = findHelper(options.resourcesPath);
  if (helper === undefined) {
    return { status: "helper_unavailable", network_name: null };
  }

  const resultFile = join(tmpdir(), `elfienest-wifi-${randomUUID()}.json`);
  try {
    const output = await launchHelper(helper, resultFile);
    return parseHelperResponse(output);
  } finally {
    await rm(resultFile, { force: true });
  }
}

export function findHelper(resourcesPath: string): string | undefined {
  const currentDirectory = dirname(fileURLToPath(import.meta.url));
  const candidates = [
    join(resourcesPath, "wifi-access-helper", HELPER_APP),
    join(currentDirectory, "macos", HELPER_APP),
  ];
  return candidates.find((candidate) => existsSync(join(candidate, "Contents", "Info.plist")));
}

async function launchHelper(helper: string, resultFile: string): Promise<string> {
  const child = spawn(
    "/usr/bin/open",
    ["-n", "-W", helper, "--args", "--result-file", resultFile],
    { stdio: "ignore", windowsHide: true },
  );
  const output = await waitForResult(resultFile);
  child.kill();
  return output;
}

async function waitForResult(resultFile: string): Promise<string> {
  const deadline = Date.now() + HELPER_TIMEOUT_MS + 5_000;
  while (Date.now() < deadline) {
    try {
      return await readFile(resultFile, "utf8");
    } catch (error: unknown) {
      if (!isMissingFileError(error)) throw error;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  return "";
}

export function parseHelperResponse(output: string): DesktopWifiAccessResult {
  const line = output
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter((value) => value.length > 0)
    .at(-1);
  if (line === undefined) {
    return { status: "helper_unavailable", network_name: null };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    return { status: "helper_unavailable", network_name: null };
  }
  if (!isHelperResponse(parsed)) {
    return { status: "helper_unavailable", network_name: null };
  }
  if (parsed.status === "available" && typeof parsed.network_name === "string") {
    const networkName = parsed.network_name.trim();
    if (networkName.length > 0) {
      return { status: "available", network_name: networkName };
    }
  }

  const status = knownStatus(parsed.status);
  return { status, network_name: null };
}

function isHelperResponse(value: unknown): value is HelperResponse {
  return (
    typeof value === "object"
    && value !== null
    && !Array.isArray(value)
    && typeof Reflect.get(value, "status") === "string"
  );
}

function knownStatus(value: string): DesktopWifiAccessStatus {
  switch (value) {
    case "permission_denied":
    case "location_services_disabled":
    case "ssid_unavailable":
    case "permission_unknown":
    case "helper_timeout":
      return value;
    default:
      return "helper_unavailable";
  }
}

function isMissingFileError(error: unknown): boolean {
  return typeof error === "object" && error !== null && Reflect.get(error, "code") === "ENOENT";
}

export const LOCATION_SERVICES_SETTINGS_URL =
  "x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices";
