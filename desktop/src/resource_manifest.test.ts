import { strict as assert } from "node:assert";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  REQUIRED_RESOURCE_PATHS,
  buildResourceManifest,
  validateResourceManifest,
} from "./resource_manifest.js";

function createResourceTree(): string {
  const root = mkdtempSync(join(tmpdir(), "elfienest-resources-"));
  for (const resourcePath of REQUIRED_RESOURCE_PATHS) {
    const fullPath = join(root, resourcePath);
    mkdirSync(join(fullPath, ".."), { recursive: true });
    writeFileSync(fullPath, `resource:${resourcePath}`);
  }
  return root;
}

test("resource manifest records and validates every packaged component", () => {
  // Given
  const root = createResourceTree();
  try {
    // When
    const manifest = buildResourceManifest(root, "0.1.0");

    // Then
    assert.equal(manifest.schema_version, 1);
    assert.equal(manifest.application_version, "0.1.0");
    assert.deepEqual(validateResourceManifest(root, manifest), []);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("resource manifest reports tampered and missing files", () => {
  // Given
  const root = createResourceTree();
  try {
    const manifest = buildResourceManifest(root, "0.1.0");
    writeFileSync(join(root, "godot-web/elfienest.wasm"), "tampered");
    rmSync(join(root, "ollama/linux/ollama"));

    // When
    const errors = validateResourceManifest(root, manifest);

    // Then
    assert.equal(errors.length, 3);
    assert.ok(errors.some((error) => error.includes("elfienest.wasm")));
    assert.ok(errors.some((error) => error.includes("ollama/linux/ollama")));
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
