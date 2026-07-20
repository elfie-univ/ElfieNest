import { strict as assert } from "node:assert";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  buildResourceManifest,
  requiredResourcePathsForTarget,
  validateResourceManifest,
} from "./resource_manifest.js";

function createResourceTree(target: "darwin-arm64" | "win32-x64"): string {
  const root = mkdtempSync(join(tmpdir(), "elfienest-resources-"));
  for (const resourcePath of requiredResourcePathsForTarget(target)) {
    const fullPath = join(root, resourcePath);
    mkdirSync(join(fullPath, ".."), { recursive: true });
    writeFileSync(fullPath, `resource:${resourcePath}`);
  }
  return root;
}

test("resource manifest records and validates every packaged component for one staging target", () => {
  // Given
  const root = createResourceTree("darwin-arm64");
  try {
    // When
    const manifest = buildResourceManifest(root, "0.1.0", "darwin-arm64");

    // Then
    assert.equal(manifest.schema_version, 1);
    assert.equal(manifest.application_version, "0.1.0");
    assert.equal(manifest.target, "darwin-arm64");
    assert.ok(manifest.files["python-core/ElfieNestCore"]);
    assert.ok(manifest.files["ollama/ollama"]);
    assert.equal(manifest.files["python-core/darwin/ElfieNestCore"], undefined);
    assert.equal(manifest.files["ollama/darwin/ollama"], undefined);
    assert.deepEqual(validateResourceManifest(root, manifest), []);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("resource manifest uses Windows executables inside the target staging root", () => {
  // Given
  const root = createResourceTree("win32-x64");
  try {
    // When
    const manifest = buildResourceManifest(root, "0.1.0", "win32-x64");

    // Then
    assert.equal(manifest.target, "win32-x64");
    assert.ok(manifest.files["python-core/ElfieNestCore.exe"]);
    assert.ok(manifest.files["ollama/ollama.exe"]);
    assert.equal(manifest.files["python-core/win32/ElfieNestCore.exe"], undefined);
    assert.deepEqual(validateResourceManifest(root, manifest), []);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("resource manifest reports tampered and missing files", () => {
  // Given
  const root = createResourceTree("darwin-arm64");
  try {
    const manifest = buildResourceManifest(root, "0.1.0", "darwin-arm64");
    writeFileSync(join(root, "godot-web/elfienest.wasm"), "tampered");
    rmSync(join(root, "ollama/ollama"));

    // When
    const errors = validateResourceManifest(root, manifest);

    // Then
    assert.equal(errors.length, 3);
    assert.ok(errors.some((error) => error.includes("elfienest.wasm")));
    assert.ok(errors.some((error) => error.includes("ollama/ollama")));
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
