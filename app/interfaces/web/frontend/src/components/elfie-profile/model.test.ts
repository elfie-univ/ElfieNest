import { describe, expect, it } from "vitest"
import { z } from "zod"

import { BIG_FIVE_TRAITS, parseExperienceFixture } from "./model"

const privateCognition = {
  status: "ready",
  recentFocus: { topics: [{ id: "topic:门口", label: "门口", category: "place", weight: 1 }] },
  importantExperiences: { entries: [{ id: "event:adoption", occurredAt: "2026-07-02", title: "被领养", changed: "有了稳定的家。", importance: 1, people: ["主人"] }] },
  relationshipWorld: { nodes: [{ id: "self", label: "Happy", kind: "self", weight: 1 }], edges: [] },
  worldUnderstanding: {
    summary: "安静的地方让我放松。",
    rings: [
      { key: "self", nodes: [] },
      { key: "family", nodes: [] },
      { key: "nest", nodes: [] },
      { key: "society", nodes: [] },
      { key: "outside", nodes: [] },
    ],
  },
  knowledgeBeliefs: { nodes: [], edges: [] },
}

const careSettings = {
  food: {
    selectedId: "food_common",
    selectedLabel: "常规主粮",
    options: [{ id: "food_common", label: "常规主粮" }],
    unavailable: false,
  },
}

function fixture(overrides: Record<string, unknown> = {}) {
  return {
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
    privateCognition,
    careSettings,
    ...overrides,
  }
}

describe("elfie profile model", () => {
  it("parses the five named cognition modules and separate care settings", () => {
    const result = parseExperienceFixture(fixture())

    expect(BIG_FIVE_TRAITS).toEqual([
      "openness",
      "conscientiousness",
      "extraversion",
      "agreeableness",
      "neuroticism",
    ])
    expect(result.privateCognition.recentFocus.topics[0]?.label).toBe("门口")
    expect(result.privateCognition.importantExperiences.entries).toHaveLength(1)
    expect(result.privateCognition.relationshipWorld.nodes[0]?.kind).toBe("self")
    expect(result.privateCognition.worldUnderstanding.rings).toHaveLength(5)
    expect(result.careSettings.food.selectedId).toBe("food_common")
  })

  it("rejects out-of-range Big Five values and cognition weights", () => {
    expect(() => parseExperienceFixture(fixture({
      publicProfile: {
        ...fixture().publicProfile,
        bigFive: { ...fixture().publicProfile.bigFive, openness: 1.2 },
      },
    }))).toThrow(z.ZodError)
    expect(() => parseExperienceFixture(fixture({
      privateCognition: {
        ...privateCognition,
        recentFocus: { topics: [{ id: "topic:bad", label: "bad", category: "activity", weight: 2 }] },
      },
    }))).toThrow(z.ZodError)
  })

  it("enforces the agreed topic, experience, relationship, and knowledge caps", () => {
    const tooManyTopics = Array.from({ length: 51 }, (_, index) => ({
      id: `topic:${index}`,
      label: `主题${index}`,
      category: "activity",
      weight: 0.5,
    }))
    const tooManyExperiences = Array.from({ length: 11 }, (_, index) => ({
      id: `event:${index}`,
      occurredAt: "2026-07-02",
      title: `事件${index}`,
      changed: "变化",
      importance: 0.5,
      people: [],
    }))
    const tooManyNodes = Array.from({ length: 21 }, (_, index) => ({
      id: `node:${index}`,
      label: `节点${index}`,
      kind: "human" as const,
      weight: 0.5,
    }))
    expect(() => parseExperienceFixture(fixture({
      privateCognition: {
        ...privateCognition,
        recentFocus: { topics: tooManyTopics },
        importantExperiences: { entries: tooManyExperiences },
        relationshipWorld: { nodes: tooManyNodes, edges: [] },
        knowledgeBeliefs: { nodes: [...tooManyNodes.slice(0, 10), { id: "node:extra", label: "额外", kind: "belief" as const, weight: 0.5 }], edges: [] },
      },
    }))).toThrow(z.ZodError)
  })

  it("accepts fifty recent-focus topics for a dense word cloud", () => {
    const topics = Array.from({ length: 50 }, (_, index) => ({
      id: `topic:${index}`,
      label: `主题${index}`,
      category: "activity",
      weight: index / 49,
    }))

    const result = parseExperienceFixture(fixture({
      privateCognition: {
        ...privateCognition,
        recentFocus: { topics },
      },
    }))

    expect(result.privateCognition.recentFocus.topics).toHaveLength(50)
  })
})
