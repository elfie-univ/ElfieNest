import { chmodSync, cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

if (process.platform !== "darwin") {
  process.exit(0);
}

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const desktopDirectory = resolve(scriptDirectory, "..");
const outputDirectory = resolve(desktopDirectory, "../../../build/components/desktop-interface");
const macosDirectory = join(outputDirectory, "macos");
const helperApp = join(macosDirectory, "WifiAccessHelper.app");
const helperContents = join(helperApp, "Contents");
const helperBinaryDirectory = join(helperContents, "MacOS");
const helperBinary = join(helperBinaryDirectory, "WifiAccessHelper");
const helperBuild = join(macosDirectory, "WifiAccessHelperBin");

rmSync(macosDirectory, { recursive: true, force: true });
mkdirSync(macosDirectory, { recursive: true });

// Use Apple's /usr/bin/swiftc shim. On the current CommandLineTools release,
// invoking the raw xcrun-selected toolchain path directly can load two copies
// of SwiftBridging's module map and fail before compiling the source.
const swiftcPath = "swiftc";
const source = join(desktopDirectory, "macos", "WifiAccessHelper.swift");
const info = join(desktopDirectory, "macos", "Info.plist");
const targetArch = process.arch === "x64" ? "x86_64" : process.arch;
if (targetArch !== "arm64" && targetArch !== "x86_64") {
  throw new Error(`Unsupported macOS Wi-Fi helper architecture: ${process.arch}`);
}

const compile = spawnSync(
  swiftcPath,
  [
    "-O",
    "-target",
    `${targetArch}-apple-macos11.0`,
    "-disable-bridging-pch",
    "-framework",
    "AppKit",
    "-framework",
    "CoreLocation",
    "-framework",
    "CoreWLAN",
    "-o",
    helperBuild,
    source,
  ],
  { stdio: "inherit" },
);
if (compile.status !== 0) {
  throw new Error("Unable to build the macOS Wi-Fi access helper");
}

mkdirSync(helperContents, { recursive: true });
cpSync(info, join(helperContents, "Info.plist"));
mkdirSync(helperBinaryDirectory, { recursive: true });
cpSync(helperBuild, helperBinary);
rmSync(helperBuild, { force: true });
chmodSync(helperBinary, 0o755);

const sign = spawnSync(
  "/usr/bin/codesign",
  ["--force", "--deep", "--sign", "-", helperApp],
  { stdio: "inherit" },
);
if (sign.status !== 0) {
  throw new Error("Unable to ad-hoc sign the macOS Wi-Fi access helper");
}

if (!existsSync(helperBinary)) {
  throw new Error("The macOS Wi-Fi access helper was not produced");
}
