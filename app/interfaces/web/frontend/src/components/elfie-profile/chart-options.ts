import type { EChartsCoreOption } from "echarts/core"

import {
  BIG_FIVE_TRAITS,
  type GraphProjection,
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
      indicator: BIG_FIVE_TRAITS.map((trait) => ({
        max: 100,
        min: 0,
        name: labels[trait],
      })),
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

export function buildGraphOption(
  graph: GraphProjection,
  theme: ChartTheme,
) {
  const directed = graph.edges.some((edge) => edge.directed)
  return {
    animationDuration: 280,
    aria: { enabled: false },
    color: [theme.accent],
    series: [{
      data: graph.nodes.map((node) => ({
        id: node.id,
        name: node.label,
        symbolSize: 34,
      })),
      edgeLabel: {
        color: theme.textMuted,
        formatter: "{c}",
        show: false,
      },
      edgeLineStyle: { color: theme.border, curveness: directed ? 0.08 : 0 },
      edgeSymbol: directed ? ["none", "arrow"] : ["none", "none"],
      edgeSymbolSize: directed ? 8 : 0,
      emphasis: { focus: "adjacency" },
      label: { color: theme.text, overflow: "break", position: "right", show: true },
      layout: "circular",
      circular: { rotateLabel: true },
      top: "20%",
      bottom: "20%",
      left: "14%",
      right: "14%",
      zoom: 0.65,
      links: graph.edges.map((edge) => ({
        source: edge.source,
        target: edge.target,
        value: edge.label,
      })),
      roam: true,
      type: "graph",
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
