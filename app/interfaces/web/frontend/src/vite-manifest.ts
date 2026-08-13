type Manifest = Readonly<Record<string, unknown>>

export function exposeDynamicImportAssets(manifest: unknown): Manifest {
  if (!isRecord(manifest)) throw new TypeError("Vite manifest must be an object")
  return Object.fromEntries(
    Object.entries(manifest).map(([key, value]) => [key, exposeEntry(value)]),
  )
}

export function exposePublicAssets(manifest: unknown, assetPaths: readonly string[]): Manifest {
  if (!isRecord(manifest)) throw new TypeError("Vite manifest must be an object")
  const entry = manifest["index.html"]
  if (!isRecord(entry)) throw new TypeError("Vite manifest must include index.html")
  return {
    ...manifest,
    "index.html": {
      ...entry,
      assets: [...new Set([...stringList(entry["assets"]), ...assetPaths])],
    },
  }
}

function exposeEntry(value: unknown): unknown {
  if (!isRecord(value)) return value
  const dynamicImports = stringList(value["dynamicImports"])
  if (dynamicImports.length === 0) return value
  return {
    ...value,
    imports: [...new Set([...stringList(value["imports"]), ...dynamicImports])],
  }
}

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function stringList(value: unknown): readonly string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []
}
