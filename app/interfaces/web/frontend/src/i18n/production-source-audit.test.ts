import { readdirSync, readFileSync } from "node:fs"
import { dirname, join, relative } from "node:path"
import { fileURLToPath } from "node:url"

import { describe, expect, it } from "vitest"

const SOURCE_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..")

const CJK_ALLOWLIST = {
  "components/elfie-profile/PersonalIdentityFrame.tsx": "Legacy API sentinels are parsed before localized presentation.",
  "components/elfie-profile/profile-presentation.ts": "Legacy API values are normalized before localized rendering.",
} as const satisfies Readonly<Record<string, string>>

type AuditRisk = "cjk-ui" | "locale-sensitive-api"

function auditSource(relativePath: string, source: string): readonly AuditRisk[] {
  const risks: AuditRisk[] = []
  const cjkAuditSource = relativePath === "components/LanguageSwitcher.tsx"
    ? source.replace(/(["'])简体中文\1/gu, "")
    : source
  if (/\p{Script=Han}/u.test(cjkAuditSource) && !(relativePath in CJK_ALLOWLIST)) {
    risks.push("cjk-ui")
  }
  const usesLocaleSensitiveApi =
    /\.toLocale(?:String|DateString|TimeString|LowerCase|UpperCase)\s*\(/u.test(source)
    || /\.localeCompare\s*\(/u.test(source)
    || /new\s+Intl\./u.test(source)
  if (usesLocaleSensitiveApi && relativePath !== "i18n/format.ts") {
    risks.push("locale-sensitive-api")
  }
  return risks
}

function productionSources(directory: string): readonly string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const absolutePath = join(directory, entry.name)
    if (entry.isDirectory()) {
      return entry.name === "locales" || entry.name === "test" ? [] : productionSources(absolutePath)
    }
    if (!entry.isFile() || !/\.(?:ts|tsx)$/u.test(entry.name) || /\.(?:test|spec)\.(?:ts|tsx)$/u.test(entry.name)) {
      return []
    }
    return [absolutePath]
  })
}

describe("production source internationalization audit", () => {
  it("rejects unclassified CJK UI and locale-sensitive APIs outside the central formatter", () => {
    const findings = productionSources(SOURCE_ROOT).flatMap((absolutePath) => {
      const relativePath = relative(SOURCE_ROOT, absolutePath)
      return auditSource(relativePath, readFileSync(absolutePath, "utf8"))
        .map((risk) => `${relativePath}: ${risk}`)
    })

    expect(findings).toEqual([])
  })

  it("keeps every CJK exception narrow, documented, and live", () => {
    for (const [relativePath, reason] of Object.entries(CJK_ALLOWLIST)) {
      expect(reason.length).toBeGreaterThan(20)
      expect(readFileSync(join(SOURCE_ROOT, relativePath), "utf8")).toMatch(/\p{Script=Han}/u)
    }
  })

  it("detects a controlled bad fixture", () => {
    const source = "export const label = '保存'; new Intl.DateTimeFormat('en-US')"
    expect(auditSource("fixtures/bad-ui.tsx", source)).toEqual([
      "cjk-ui",
      "locale-sensitive-api",
    ])
  })

  it("allows locale autonyms without exempting other product-owned copy", () => {
    const source = "export const autonym = '简体中文'; export const label = '语言 / Language'"
    expect(auditSource("components/LanguageSwitcher.tsx", source)).toEqual(["cjk-ui"])
  })
})
