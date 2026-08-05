#!/bin/bash
# Verify the repository's independent Node projects share one locked toolchain.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${1:-$(dirname "$SCRIPT_DIR")}"
EXPECTED_PNPM="pnpm@10.12.1"
EXPECTED_NODE_ENGINE=">=20"

NODE_PROJECTS=(
    "."
    "app/interfaces/web/frontend"
    "app/interfaces/desktop"
    "docs"
    "devtools/web"
)

read_package_field() {
    local manifest="$1"
    local field="$2"

    node -e '
const fs = require("node:fs");
const [manifestPath, field] = process.argv.slice(1);
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const value = field === "node"
  ? manifest.engines?.node
  : manifest[field];
if (typeof value !== "string") process.exit(2);
process.stdout.write(value);
' "$manifest" "$field"
}

fail() {
    echo "❌ $1" >&2
    exit 1
}

command -v node >/dev/null 2>&1 || fail "Node.js is required to inspect package.json files."

root_manifest="$PROJECT_ROOT/package.json"
[[ -f "$root_manifest" ]] || fail "Missing repository toolchain anchor: $root_manifest"

root_pnpm="$(read_package_field "$root_manifest" packageManager)" || \
    fail "Repository toolchain anchor has no packageManager: $root_manifest"
[[ "$root_pnpm" == "$EXPECTED_PNPM" ]] || \
    fail "$root_manifest declares $root_pnpm; expected $EXPECTED_PNPM"

for relative_dir in "${NODE_PROJECTS[@]}"; do
    package_dir="$PROJECT_ROOT/$relative_dir"
    manifest="$package_dir/package.json"
    [[ -f "$manifest" ]] || fail "Missing Node project manifest: $manifest"
    [[ -f "$package_dir/pnpm-lock.yaml" || "$relative_dir" == "." ]] || \
        fail "Missing pnpm lockfile: $package_dir/pnpm-lock.yaml"

    package_manager="$(read_package_field "$manifest" packageManager)" || \
        fail "$manifest has no packageManager declaration"
    [[ "$package_manager" == "$EXPECTED_PNPM" ]] || \
        fail "$manifest declares $package_manager; expected $EXPECTED_PNPM"

    node_engine="$(read_package_field "$manifest" node)" || \
        fail "$manifest has no engines.node declaration"
    [[ "$node_engine" == "$EXPECTED_NODE_ENGINE" ]] || \
        fail "$manifest declares engines.node=$node_engine; expected $EXPECTED_NODE_ENGINE"
done

echo "✅ Node toolchain manifests are consistent: Node $EXPECTED_NODE_ENGINE, $EXPECTED_PNPM"
