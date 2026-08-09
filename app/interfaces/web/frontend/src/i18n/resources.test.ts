import { access } from "node:fs/promises"
import { resolve } from "node:path"

import { afterEach, describe, expect, it, vi } from "vitest"
import { z } from "zod"

import { createI18n, i18nOptions } from "./config"
import { namespaces, resources, supportedLngs } from "./resources"

const localeNames = ["zh-CN", "en-US"] as const
const namespaceNames = [
  "common",
  "auth",
  "setup",
  "account",
  "chat",
  "manage",
  "monitor",
] as const

const i18nRoot = resolve(import.meta.dirname)

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

interface ResourceBranch {
  readonly [key: string]: ResourceNode
}

type ResourceNode = string | ResourceBranch

const resourceNodeSchema: z.ZodType<ResourceNode> = z.lazy(() =>
  z.union([z.string(), z.record(resourceNodeSchema)]),
)

function collectLeafPaths(source: unknown, prefix = ""): readonly string[] {
  const resourceNode = resourceNodeSchema.parse(source)
  if (typeof resourceNode === "string") {
    return [prefix]
  }

  return Object.entries(resourceNode).flatMap(([key, value]) => {
    const path = prefix.length === 0 ? key : `${prefix}.${key}`
    return collectLeafPaths(value, path)
  })
}

async function findExistingContractFiles(): Promise<readonly string[]> {
  const expectedFiles = [
    "config.ts",
    "resources.ts",
    "types.d.ts",
    ...localeNames.flatMap((localeName) =>
      namespaceNames.map(
        (namespaceName) => `locales/${localeName}/${namespaceName}.ts`,
      ),
    ),
  ]

  const existingFiles = await Promise.all(
    expectedFiles.map(async (relativePath) => {
      try {
        await access(resolve(i18nRoot, relativePath))
        return relativePath
      } catch (error) {
        if (error instanceof Error) {
          return null
        }
        throw error
      }
    }),
  )

  return existingFiles.filter((relativePath) => relativePath !== null)
}

describe("static i18n resource contract", () => {
  it("provides every locale and namespace as TypeScript modules", async () => {
    // Given: the complete static i18n module contract.
    const expectedFileCount = 17

    // When: the Task 2 module paths are inspected.
    const existingFiles = await findExistingContractFiles()

    // Then: config, resources, augmentation, and all 14 dictionaries exist.
    expect(existingFiles).toHaveLength(expectedFileCount)
  })

  it("keeps recursive translation leaf paths equal across locales", () => {
    // Given: every supported namespace in the two statically bundled locales.
    const parityByNamespace = namespaces.map((namespaceName) => ({
      namespaceName,
      zhCN: [...collectLeafPaths(resources["zh-CN"][namespaceName])].sort(),
      enUS: [...collectLeafPaths(resources["en-US"][namespaceName])].sort(),
    }))

    // When: recursive leaf paths are compared namespace by namespace.
    const mismatches = parityByNamespace.filter(
      ({ zhCN, enUS }) => JSON.stringify(zhCN) !== JSON.stringify(enUS),
    )

    // Then: neither locale has a missing or extra translation leaf.
    expect(mismatches).toEqual([])
  })

  it("detects a missing recursive key in a controlled malformed fixture", () => {
    // Given: a translated fixture whose nested secondary label is missing.
    const referenceFixture = {
      panel: { title: "标题", actions: { save: "保存" } },
    } as const
    const malformedFixture = { panel: { title: "Title" } } as const

    // When: the same recursive parity comparison is applied.
    const referencePaths = [...collectLeafPaths(referenceFixture)].sort()
    const malformedPaths = [...collectLeafPaths(malformedFixture)].sort()

    // Then: the missing nested key is surfaced deterministically.
    expect(malformedPaths).not.toEqual(referencePaths)
    expect(referencePaths).toContain("panel.actions.save")
    expect(malformedPaths).not.toContain("panel.actions.save")
  })

  it("resolves every namespace in both supported locales", () => {
    // Given: a fresh synchronously initialized static i18n instance.
    const instance = createI18n()

    // When: one live message from every namespace is translated.
    const zhCNTranslations = [
      instance.getFixedT("zh-CN", "common")("actions.confirm"),
      instance.getFixedT("zh-CN", "auth")("login.action"),
      instance.getFixedT("zh-CN", "setup")("progress.stepCount", { current: 2, total: 5 }),
      instance.getFixedT("zh-CN", "account")("session.logout"),
      instance.getFixedT("zh-CN", "chat")("composer.withElfie", { elfieName: "艾菲" }),
      instance.getFixedT("zh-CN", "manage")("systemSettings.quota.count", { count: 4 }),
      instance.getFixedT("zh-CN", "monitor")("connection.connectedTo", { endpoint: "Nest" }),
    ]
    const enUSTranslations = [
      instance.getFixedT("en-US", "common")("actions.confirm"),
      instance.getFixedT("en-US", "auth")("login.action"),
      instance.getFixedT("en-US", "setup")("progress.stepCount", { current: 2, total: 5 }),
      instance.getFixedT("en-US", "account")("session.logout"),
      instance.getFixedT("en-US", "chat")("composer.withElfie", { elfieName: "Elfie" }),
      instance.getFixedT("en-US", "manage")("systemSettings.quota.count", { count: 4 }),
      instance.getFixedT("en-US", "monitor")("connection.connectedTo", { endpoint: "Nest" }),
    ]

    // Then: interpolation is complete and no raw template marker remains.
    expect(zhCNTranslations).toEqual([
      "确认",
      "登录",
      "第 2 步，共 5 步",
      "退出登录",
      "对 艾菲 说点什么…",
      "4 只",
      "已连接至 Nest",
    ])
    expect(enUSTranslations).toEqual([
      "Confirm",
      "Log in",
      "Step 2 of 5",
      "Sign out",
      "Say something to Elfie...",
      "4",
      "Connected to Nest",
    ])
  })

  it("initializes synchronously from bundled resources without network calls", () => {
    // Given: spies on both browser resource-loading surfaces.
    const fetchSpy = vi.fn()
    const xhrOpenSpy = vi.spyOn(XMLHttpRequest.prototype, "open")
    vi.stubGlobal("fetch", fetchSpy)

    // When: a fresh i18n instance is created from the static configuration.
    const instance = createI18n()

    // Then: initialization and translation are immediate and entirely local.
    expect(instance.isInitialized).toBe(true)
    expect(instance.t("actions.confirm")).toBe("确认")
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(xhrOpenSpy).not.toHaveBeenCalled()

  })

  it("exposes the closed locale and synchronous initialization options", () => {
    // Given: the exported resource and initialization contracts.
    const firstInstance = createI18n()
    const secondInstance = createI18n()

    // When: their closed-set and lifecycle values are inspected.
    const contract = {
      supportedLngs,
      namespaceCount: namespaces.length,
      fallbackLng: i18nOptions.fallbackLng,
      load: i18nOptions.load,
      returnNull: i18nOptions.returnNull,
      useSuspense: i18nOptions.react.useSuspense,
      initAsync: i18nOptions.initAsync,
    } as const

    // Then: the Task 2 defaults are fixed and instances never share stale state.
    expect(contract).toEqual({
      supportedLngs: ["zh-CN", "en-US"],
      namespaceCount: 7,
      fallbackLng: "zh-CN",
      load: "currentOnly",
      returnNull: false,
      useSuspense: false,
      initAsync: false,
    })
    expect(firstInstance).not.toBe(secondInstance)
  })
})
