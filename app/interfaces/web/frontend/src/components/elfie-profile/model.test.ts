import { describe, expect, it } from "vitest"
import { z } from "zod"

import {
  BIG_FIVE_TRAITS,
  GRAPH_DETAIL_LIMIT,
  GRAPH_PREVIEW_LIMIT,
  parseExperienceFixture,
  projectGraph,
} from "./model"

describe("elfie profile model", () => {
  it("bounds Big Five values when parsing experience fixtures", () => {
    const result = parseExperienceFixture({
      adopter: { accountId: "admin123", displayName: "管理员" },
      publicProfile: {
        elfieId: "elfie_default",
        name: "Happy",
        speciesId: "fox",
        biography: "会在晨光里整理自己的小小发现。",
        appearance: { bodyPlan: "fox", palette: "sunlit amber", signature: "soft ears" },
        bigFive: {
          openness: 0.8,
          conscientiousness: 0.6,
          extraversion: 0.7,
          agreeableness: 0.9,
          neuroticism: 0.2,
        },
      },
      privateCognition: {
        modules: [
          { title: "记忆与认知", topics: [{ label: "晨间巡游", count: 7 }], experienceCount: 12 },
          { title: "重要经历", entries: [{ date: "2026-07-02", title: "第一次回应", detail: "记住了主人的称呼。" }] },
          { title: "关系认知", graph: { nodes: [{ id: "owner", label: "管理员" }], edges: [] } },
          { title: "知识与信念", graph: { nodes: [{ id: "nest", label: "巢" }], edges: [] } },
          { title: "世界理解", graph: { nodes: [{ id: "room", label: "主巢" }], edges: [] } },
          {
            title: "粮食策略",
            food: { selected: "standard", allowed: ["standard", "coarse"], fallback: "coarse" },
          },
        ],
      },
    })

    expect(BIG_FIVE_TRAITS).toEqual([
      "openness",
      "conscientiousness",
      "extraversion",
      "agreeableness",
      "neuroticism",
    ])
    expect(result.publicProfile.bigFive.openness).toBe(0.8)
    expect(result.publicProfile.elfieId).toBe("elfie_default")
  })

  it("rejects malformed Big Five fixture values", () => {
    const result = z.object({
      openness: z.number().min(0).max(1),
    }).safeParse({ openness: 1.2 })

    expect(result.success).toBe(false)
    expect(() => parseExperienceFixture({
      adopter: { accountId: "admin123", displayName: "管理员" },
      publicProfile: {
        elfieId: "12345678",
        name: "Happy",
        speciesId: "fox",
        biography: "边界测试。",
        appearance: { bodyPlan: "fox", palette: "amber", signature: "ears" },
        bigFive: {
          openness: 1.2,
          conscientiousness: 0.6,
          extraversion: 0.7,
          agreeableness: 0.9,
          neuroticism: 0.2,
        },
      },
      privateCognition: {
        modules: [
          { title: "记忆与认知", topics: [], experienceCount: 0 },
          { title: "重要经历", entries: [] },
          { title: "关系认知", graph: { nodes: [], edges: [] } },
          { title: "知识与信念", graph: { nodes: [], edges: [] } },
          { title: "世界理解", graph: { nodes: [], edges: [] } },
          {
            title: "粮食策略",
            food: { selected: "standard", allowed: ["standard", "coarse"], fallback: "coarse" },
          },
        ],
      },
    })).toThrow(z.ZodError)
  })

  it("parses missing public fields gracefully", () => {
    const result = parseExperienceFixture({
      adopter: { accountId: "admin123", displayName: "管理员" },
      publicProfile: {
        elfieId: "12345678",
        name: "Happy",
        speciesId: "fox",
        appearance: { bodyPlan: "fox", palette: "amber", signature: "ears" },
        bigFive: {
          openness: 0.5,
          conscientiousness: 0.5,
          extraversion: 0.5,
          agreeableness: 0.5,
          neuroticism: 0.5,
        },
      },
      privateCognition: {
        modules: [
          { title: "记忆与认知", topics: [], experienceCount: 0 },
          { title: "重要经历", entries: [] },
          { title: "关系认知", graph: { nodes: [], edges: [] } },
          { title: "知识与信念", graph: { nodes: [], edges: [] } },
          { title: "世界理解", graph: { nodes: [], edges: [] } },
          {
            title: "粮食策略",
            food: { selected: "standard", allowed: ["standard", "coarse"], fallback: "coarse" },
          },
        ],
      },
    })

    expect(result.publicProfile.biography).toBe("")
    expect(result.publicProfile.gender).toBeNull()
    expect(result.publicProfile.portraitUrl).toBe("")
  })

  it("truncates graph projections deterministically at preview and detail limits", () => {
    const nodes = Array.from({ length: 51 }, (_, index) => ({
      id: `node-${String(index + 1).padStart(2, "0")}`,
      label: `节点 ${index + 1}`,
    }))
    const graph = parseExperienceFixture({
      adopter: { accountId: "admin123", displayName: "管理员" },
      publicProfile: {
        elfieId: "12345678",
        name: "Happy",
        speciesId: "fox",
        appearance: { bodyPlan: "fox", palette: "amber", signature: "ears" },
        bigFive: {
          openness: 0.5,
          conscientiousness: 0.5,
          extraversion: 0.5,
          agreeableness: 0.5,
          neuroticism: 0.5,
        },
      },
      privateCognition: {
        modules: [
          { title: "记忆与认知", topics: [], experienceCount: 0 },
          { title: "重要经历", entries: [] },
          { title: "关系认知", graph: { nodes, edges: [{ source: "node-01", target: "node-51", label: "远端关系" }] } },
          { title: "知识与信念", graph: { nodes: [], edges: [] } },
          { title: "世界理解", graph: { nodes: [], edges: [] } },
          {
            title: "粮食策略",
            food: { selected: "standard", allowed: ["standard", "coarse"], fallback: "coarse" },
          },
        ],
      },
    }).privateCognition.modules[2].graph

    const preview = projectGraph(graph, "preview")
    const detail = projectGraph(graph, "detail")

    expect(preview.nodes).toHaveLength(GRAPH_PREVIEW_LIMIT)
    expect(preview.truncatedNodeCount).toBe(31)
    expect(preview.edges).toEqual([])
    expect(preview.nodes.map((node) => node.id).at(-1)).toBe("node-20")
    expect(detail.nodes).toHaveLength(GRAPH_DETAIL_LIMIT)
    expect(detail.truncatedNodeCount).toBe(1)
    expect(detail.nodes.map((node) => node.id).at(-1)).toBe("node-50")
  })
})
