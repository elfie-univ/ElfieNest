import { strict as assert } from "node:assert";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { resolveSupervisorConfig } from "./supervisor_config.js";

test("desktop opens the login page and resolves the Core at the packaged manifest path", () => {
  const root = mkdtempSync(join(tmpdir(), "elfienest-supervisor-config-"));
  const resources = join(root, "resources");
  const core = join(resources, "python-core", "ElfieNestCore");
  mkdirSync(join(resources, "python-core"), { recursive: true });
  writeFileSync(core, "core");

  try {
    const config = resolveSupervisorConfig({}, resources, root, "darwin", join(root, "data"));

    assert.equal(config.uiUrl, "http://127.0.0.1:8000/login");
    assert.equal(config.coreExecutable, core);
    assert.equal(config.ollamaExecutable, join(resources, "ollama", "ollama"));
    assert.equal(config.webBuildDirectory, join(resources, "web"));
    assert.deepEqual(config.coreArgs, ["--lan"]);
    assert.equal(config.coreWorkingDirectory, join(root, "data"));
    assert.equal(config.ollamaOptional, true);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("desktop environment overrides retain the explicit UI and Core launch contract", () => {
  const root = mkdtempSync(join(tmpdir(), "elfienest-supervisor-config-"));
  try {
    const config = resolveSupervisorConfig(
      {
        ELFIENEST_CORE_BIN: "/custom/core",
        ELFIENEST_CORE_CWD: "/custom/workdir",
        ELFIENEST_WEB_BUILD_DIR: "/custom/web",
        ELFIENEST_UI_URL: "http://127.0.0.1:8010/login",
      },
      join(root, "resources"),
      root,
      "linux",
    );

    assert.equal(config.uiUrl, "http://127.0.0.1:8010/login");
    assert.equal(config.coreExecutable, "/custom/core");
    assert.equal(config.webBuildDirectory, "/custom/web");
    assert.deepEqual(config.coreArgs, ["scripts/serve.py", "--lan"]);
    assert.equal(config.coreWorkingDirectory, "/custom/workdir");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
