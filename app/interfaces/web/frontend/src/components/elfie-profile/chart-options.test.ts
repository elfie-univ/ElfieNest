import { describe, expect, it } from "vitest"

import { HAPPY_EXPERIENCE } from "../../test/fixtures/elfie-profile"
import {
  BIG_FIVE_COPY,
  buildBigFiveRadarOption,
  resolveChartTheme,
  strongestBigFiveDescriptors,
} from "./chart-options"

const THEME = {
  accent: "token-accent",
  border: "token-border",
  surface: "token-surface",
  text: "token-text",
  textMuted: "token-muted",
}

const TRAIT_LABELS = {
  agreeableness: "Agreeableness",
  conscientiousness: "Conscientiousness",
  extraversion: "Extraversion",
  neuroticism: "Neuroticism",
  openness: "Openness",
} as const

describe("Big Five chart options", () => {
  it("builds five bounded radar axes from semantic theme tokens", () => {
    const option = buildBigFiveRadarOption(
      HAPPY_EXPERIENCE.publicProfile.bigFive,
      THEME,
      TRAIT_LABELS,
      "Big Five",
    )

    expect(option.radar.indicator).toHaveLength(5)
    expect(option.radar.radius).toBe("72%")
    expect(option.radar.axisNameGap).toBe(8)
    expect(option.radar.indicator.every((axis) => axis.max === 100 && axis.min === 0)).toBe(true)
    expect(option.series[0]?.data[0]?.value).toEqual([80, 60, 80, 70, 20])
    expect(option.color).toEqual(["token-accent"])
    expect(JSON.stringify(option)).not.toMatch(/#[0-9a-f]{3,8}|rgb\(|hsl\(/i)
  })

  it("chooses strongest descriptors deterministically, including ties", () => {
    expect(strongestBigFiveDescriptors(HAPPY_EXPERIENCE.publicProfile.bigFive)).toEqual([
      BIG_FIVE_COPY.openness,
      BIG_FIVE_COPY.extraversion,
      BIG_FIVE_COPY.agreeableness,
    ])
    expect(strongestBigFiveDescriptors({
      agreeableness: 0.5,
      conscientiousness: 0.5,
      extraversion: 0.5,
      neuroticism: 0.5,
      openness: 0.5,
    })).toEqual([
      BIG_FIVE_COPY.openness,
      BIG_FIVE_COPY.conscientiousness,
      BIG_FIVE_COPY.extraversion,
    ])
  })

  it("resolves chart colors from CSS custom properties", () => {
    const style = {
      getPropertyValue: (name: string) => ({
        "--accent": " chart-accent ",
        "--border": " chart-border ",
        "--surface-raised": " chart-surface ",
        "--text": " chart-text ",
        "--text-muted": " chart-muted ",
      })[name] ?? "",
    }

    expect(resolveChartTheme(style)).toEqual({
      accent: "chart-accent",
      border: "chart-border",
      surface: "chart-surface",
      text: "chart-text",
      textMuted: "chart-muted",
    })
  })
})
