import type { i18n } from "i18next"

import type { SupportedLocale } from "./locale"

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
