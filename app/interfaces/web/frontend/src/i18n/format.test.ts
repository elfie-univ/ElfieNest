import { describe, expect, it } from "vitest"

import { createI18n } from "./config"
import {
  compareLocalizedText,
  currentLocale,
  segmentWords,
} from "./format"

describe("central locale formatting", () => {
  it("sorts mixed Latin and Chinese labels by the selected locale", () => {
    // Given: the same immutable labels in mixed scripts.
    const labels = ["阿尔法", "Zulu", "apple", "张三", "Alice"] as const

    // When: copies are sorted with each central locale comparator.
    const zhCN = [...labels].sort((left, right) =>
      compareLocalizedText(left, right, "zh-CN"),
    )
    const enUS = [...labels].sort((left, right) =>
      compareLocalizedText(left, right, "en-US"),
    )

    // Then: ordering is deterministic and locale-sensitive.
    expect(zhCN).toEqual(["阿尔法", "张三", "Alice", "apple", "Zulu"])
    expect(enUS).toEqual(["Alice", "apple", "Zulu", "张三", "阿尔法"])
  })

  it("segments words with the selected closed locale", () => {
    // Given: a mixed-script phrase displayed as user-authored content.
    const phrase = "你好 ElfieNest friends"

    // When: the phrase is segmented through the central service.
    const words = segmentWords(phrase, "en-US").map((entry) => entry.segment)

    // Then: content is preserved while word boundaries are exposed to the component.
    expect(words).toEqual(["你好", " ", "ElfieNest", " ", "friends"])
  })

  it("maps initialized i18n state back to the supported locale set", () => {
    // Given: an initialized instance switched to the closed English locale.
    const instance = createI18n()
    void instance.changeLanguage("en-US")

    // When: a component requests its current formatter locale.
    const locale = currentLocale(instance)

    // Then: the result is the exact supported English value.
    expect(locale).toBe("en-US")
  })
})
