import type { EChartsCoreOption } from "echarts/core"

import {
  BIG_FIVE_TRAITS,
  type PublicProfile,
} from "./model"

export type BigFiveValues = PublicProfile["bigFive"]

export type ChartTheme = {
  readonly accent: string
  readonly border: string
  readonly surface: string
  readonly text: string
  readonly textMuted: string
}

export type TraitCopy = {
  readonly trait: keyof BigFiveValues
}

export const BIG_FIVE_COPY = {
  openness: { trait: "openness" },
  conscientiousness: { trait: "conscientiousness" },
  extraversion: { trait: "extraversion" },
  agreeableness: { trait: "agreeableness" },
  neuroticism: { trait: "neuroticism" },
} satisfies Record<keyof BigFiveValues, TraitCopy>

export function buildBigFiveRadarOption(
  values: BigFiveValues,
  theme: ChartTheme,
  labels: Readonly<Record<keyof BigFiveValues, string>>,
  seriesName: string,
) {
  return {
    animationDuration: 280,
    aria: { enabled: true, decal: { show: true } },
    color: [theme.accent],
    radar: {
      axisName: { color: theme.textMuted },
      axisNameGap: 8,
      center: ["50%", "50%"],
      indicator: BIG_FIVE_TRAITS.map((trait) => ({
        max: 100,
        min: 0,
        name: labels[trait],
      })),
      radius: "84%",
      splitArea: { areaStyle: { color: [theme.surface] } },
      splitLine: { lineStyle: { color: theme.border } },
      axisLine: { lineStyle: { color: theme.border } },
    },
    series: [{
      data: [{ name: seriesName, value: BIG_FIVE_TRAITS.map((trait) => score(values[trait])) }],
      lineStyle: { color: theme.accent, width: 2 },
      areaStyle: { color: theme.accent, opacity: 0.2 },
      symbolSize: 7,
      type: "radar",
    }],
    textStyle: { color: theme.text },
    tooltip: { trigger: "item" },
  } satisfies EChartsCoreOption
}

export function strongestBigFiveDescriptors(values: BigFiveValues): readonly TraitCopy[] {
  return BIG_FIVE_TRAITS
    .map((trait, order) => ({ copy: BIG_FIVE_COPY[trait], order, value: values[trait] }))
    .sort((left, right) => right.value - left.value || left.order - right.order)
    .slice(0, 3)
    .map(({ copy }) => copy)
}

export function resolveChartTheme(
  style: Pick<CSSStyleDeclaration, "getPropertyValue">,
): ChartTheme {
  return {
    accent: token(style, "--accent", "currentColor"),
    border: token(style, "--border", "currentColor"),
    surface: token(style, "--surface-raised", "transparent"),
    text: token(style, "--text", "currentColor"),
    textMuted: token(style, "--text-muted", "currentColor"),
  }
}

function score(value: number): number {
  return Math.round(Math.min(1, Math.max(0, value)) * 100)
}

function token(
  style: Pick<CSSStyleDeclaration, "getPropertyValue">,
  name: string,
  fallback: string,
): string {
  return style.getPropertyValue(name).trim() || fallback
}
