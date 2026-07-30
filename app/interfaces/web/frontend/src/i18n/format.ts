import type { i18n } from "i18next"

import type { SupportedLocale } from "./locale"

const dateTimeFormatters = {
  "zh-CN": {
    local: new Intl.DateTimeFormat("zh-CN", {
      dateStyle: "medium",
      timeStyle: "short",
    }),
    UTC: new Intl.DateTimeFormat("zh-CN", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "UTC",
    }),
  },
  "en-US": {
    local: new Intl.DateTimeFormat("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
    }),
    UTC: new Intl.DateTimeFormat("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "UTC",
    }),
  },
} as const satisfies Record<
  SupportedLocale,
  Readonly<Record<"UTC" | "local", Intl.DateTimeFormat>>
>

const numberFormatters = {
  "zh-CN": {
    compact: new Intl.NumberFormat("zh-CN", {
      notation: "compact",
      maximumFractionDigits: 1,
    }),
    standard: new Intl.NumberFormat("zh-CN"),
  },
  "en-US": {
    compact: new Intl.NumberFormat("en-US", {
      notation: "compact",
      maximumFractionDigits: 1,
    }),
    standard: new Intl.NumberFormat("en-US"),
  },
} as const satisfies Record<
  SupportedLocale,
  Readonly<Record<"compact" | "standard", Intl.NumberFormat>>
>

const collators = {
  "zh-CN": new Intl.Collator("zh-CN"),
  "en-US": new Intl.Collator("en-US"),
} as const satisfies Record<SupportedLocale, Intl.Collator>

const wordSegmenters = {
  "zh-CN": new Intl.Segmenter("zh-CN", { granularity: "word" }),
  "en-US": new Intl.Segmenter("en-US", { granularity: "word" }),
} as const satisfies Record<SupportedLocale, Intl.Segmenter>

export function currentLocale(instance: i18n): SupportedLocale {
  return instance.resolvedLanguage === "en-US" ? "en-US" : "zh-CN"
}

export function currentDocumentLocale(
  documentElement: Pick<HTMLElement, "lang"> = document.documentElement,
): SupportedLocale {
  return documentElement.lang === "en-US" ? "en-US" : "zh-CN"
}

export function formatDateTime(
  value: Date | number | string,
  locale: SupportedLocale,
  timeZone: "UTC" | "local" = "local",
): string {
  return dateTimeFormatters[locale][timeZone].format(new Date(value))
}

export function formatNumber(
  value: number,
  locale: SupportedLocale,
  notation: "compact" | "standard" = "standard",
): string {
  return numberFormatters[locale][notation].format(value)
}

export function compareLocalizedText(
  left: string,
  right: string,
  locale: SupportedLocale,
): number {
  return collators[locale].compare(left, right)
}

export function segmentWords(
  value: string,
  locale: SupportedLocale,
): readonly Intl.SegmentData[] {
  return [...wordSegmenters[locale].segment(value)]
}
