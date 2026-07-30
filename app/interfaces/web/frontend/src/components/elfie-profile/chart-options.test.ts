import { describe, expect, it } from "vitest"

import { HAPPY_EXPERIENCE } from "./mock-data"
import {
  BIG_FIVE_COPY,
  buildBigFiveRadarOption,
  buildGraphOption,
  resolveChartTheme,
  strongestBigFiveDescriptors,
} from "./chart-options"
import { projectGraph } from "./model"

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

describe("cognition graph chart options", () => {
  it("keeps preview and detail nodes deterministically bounded", () => {
    const graph = HAPPY_EXPERIENCE.privateCognition.modules[3].graph

    const preview = buildGraphOption(projectGraph(graph, "preview"), THEME)
    const detail = buildGraphOption(projectGraph(graph, "detail"), THEME)
    const previewSeries = preview.series[0]
    const detailSeries = detail.series[0]
    expect(previewSeries).toBeDefined()
    expect(detailSeries).toBeDefined()
    if (previewSeries === undefined || detailSeries === undefined) return

    expect(previewSeries.data).toHaveLength(20)
    expect(detailSeries.data).toHaveLength(50)
    expect(previewSeries.data.map((node) => node.id)).toEqual(
      graph.nodes.slice(0, 20).map((node) => node.id),
    )
  })

  it("shows node labels and arrows for directed knowledge edges", () => {
    const graph = HAPPY_EXPERIENCE.privateCognition.modules[3].graph
    const option = buildGraphOption(projectGraph(graph, "preview"), THEME)
    const series = option.series[0]
    expect(series).toBeDefined()
    if (series === undefined) return

    expect(series.label.show).toBe(true)
    expect(series.data[0]?.name).toBe(graph.nodes[0]?.label)
    expect(series.edgeSymbol).toEqual(["none", "arrow"])
    expect(series.edgeLabel.show).toBe(false)
    expect(series.layout).toBe("circular")
    expect(series.circular.rotateLabel).toBe(true)
    expect(series.top).toBe("20%")
    expect(series.bottom).toBe("20%")
    expect(series.left).toBe("14%")
    expect(series.right).toBe("14%")
    expect(series.zoom).toBe(0.65)
    expect(option.aria).toEqual({ enabled: false })
  })

  it("keeps duplicate labels as distinct ID-backed nodes", () => {
    const graph = HAPPY_EXPERIENCE.privateCognition.modules[2].graph
    const duplicateGraph = {
      nodes: graph.nodes.slice(0, 2).map((node) => ({ ...node, label: "重复标签" })),
      edges: graph.edges.slice(0, 1),
    }
    const option = buildGraphOption(projectGraph(duplicateGraph, "preview"), THEME)
    const series = option.series[0]
    expect(series).toBeDefined()
    if (series === undefined) return

    expect(series.data).toEqual([
      expect.objectContaining({ id: graph.nodes[0]?.id, name: "重复标签" }),
      expect.objectContaining({ id: graph.nodes[1]?.id, name: "重复标签" }),
    ])
  })
})
