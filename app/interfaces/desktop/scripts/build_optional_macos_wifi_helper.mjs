import { mkdirSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

if (process.platform !== "darwin") {
  process.exit(0);
}

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const helperScript = resolve(scriptDirectory, "build_macos_wifi_helper.mjs");
const helperOutput = resolve(
  scriptDirectory,
  "../../../../build/components/desktop-interface/macos",
);
const build = spawnSync(process.execPath, [helperScript], { stdio: "inherit" });

if (build.status !== 0) {
  rmSync(helperOutput, { recursive: true, force: true });
  mkdirSync(helperOutput, { recursive: true });
  const cause = build.error instanceof Error
    ? build.error.message
    : `exit-status=${String(build.status)}`;
  console.warn(
    `[ElfieNest] optional-component-skipped component=macos-wifi-helper cause=${cause}; `
      + "packaging continues without automatic Wi-Fi name detection.",
  );
}
