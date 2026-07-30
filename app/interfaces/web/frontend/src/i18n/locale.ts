import type { i18n } from "i18next"

import { supportedLngs } from "./resources"

export const localeStorageKey = "elfienest.locale" as const

export type SupportedLocale = (typeof supportedLngs)[number]

type LocaleStorage = Pick<Storage, "getItem" | "removeItem" | "setItem">

type BrowserStorageSource = {
  readonly localStorage: LocaleStorage
}

const unavailableBrowserStorage = {
  getItem(): null {
    return null
  },
  removeItem(): void {},
  setItem(): void {},
} as const satisfies LocaleStorage

type LocaleEnvironment = {
  readonly storage: LocaleStorage
  readonly browserLanguages: readonly string[]
  readonly documentElement: Pick<HTMLElement, "dir" | "lang">
}

function isSupportedLocale(value: string | null): value is SupportedLocale {
  return value === supportedLngs[0] || value === supportedLngs[1]
}

export function getBrowserStorage(source: BrowserStorageSource): LocaleStorage {
  try {
    return source.localStorage
  } catch {
    // Host accessors may throw arbitrary values; every failure means storage is unavailable.
    return unavailableBrowserStorage
  }
}

function discardInvalidSavedLocale(
  storage: LocaleEnvironment["storage"],
): void {
  try {
    storage.removeItem(localeStorageKey)
  } catch (error) {
    if (!(error instanceof DOMException) && !(error instanceof Error)) throw error
  }
}

function readSavedLocale(
  storage: LocaleEnvironment["storage"],
): SupportedLocale | null {
  try {
    const value = storage.getItem(localeStorageKey)
    if (isSupportedLocale(value)) return value
    if (value !== null) discardInvalidSavedLocale(storage)
    return null
  } catch (error) {
    if (error instanceof DOMException || error instanceof Error) return null
    throw error
  }
}

export function matchBrowserLocale(
  browserLanguages: readonly string[],
): SupportedLocale | null {
  for (const browserLanguage of browserLanguages) {
    const normalizedLanguage = browserLanguage.trim().toLowerCase()
    if (normalizedLanguage === "zh" || normalizedLanguage.startsWith("zh-")) {
      return "zh-CN"
    }
    if (normalizedLanguage === "en" || normalizedLanguage.startsWith("en-")) {
      return "en-US"
    }
  }
  return null
}

function applyLocale(
  instance: i18n,
  locale: SupportedLocale,
  documentElement: LocaleEnvironment["documentElement"],
): void {
  void instance.changeLanguage(locale)
  documentElement.lang = locale
  documentElement.dir = "ltr"
}

function persistLocale(
  storage: LocaleEnvironment["storage"],
  locale: SupportedLocale,
): void {
  try {
    storage.setItem(localeStorageKey, locale)
  } catch (error) {
    if (!(error instanceof DOMException) && !(error instanceof Error)) throw error
  }
}

export function setLocale(
  instance: i18n,
  locale: SupportedLocale,
  environment: LocaleEnvironment,
): void {
  applyLocale(instance, locale, environment.documentElement)
  persistLocale(environment.storage, locale)
}

export function initializeLocale(
  instance: i18n,
  environment: LocaleEnvironment,
): SupportedLocale {
  const locale =
    readSavedLocale(environment.storage) ??
    matchBrowserLocale(environment.browserLanguages) ??
    "zh-CN"

  applyLocale(instance, locale, environment.documentElement)
  return locale
}
