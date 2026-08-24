import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("sandbox preload is emitted as CommonJS and can load Electron through require", () => {
  const output = join(dirname(fileURLToPath(import.meta.url)), "preload.cjs");
  const source = readFileSync(output, "utf8");

  assert.match(source, /require\(["']electron["']\)/);
  assert.match(source, /diagnostics:renderer-error/u);
  assert.doesNotMatch(source, /^\s*import\s/m);
});
