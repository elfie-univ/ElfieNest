import { describe, expect, it } from "vitest"

import { MOCK_ELFIES, MOCK_USERS } from "../../test/fixtures/owner-cards"
import {
  EMPTY_BIOGRAPHY_EXPERIENCE,
  HAPPY_EXPERIENCE,
  KETTLE_EXPERIENCE,
  LONG_BIOGRAPHY_EXPERIENCE,
  MISSING_PUBLIC_FIELDS_EXPERIENCE,
  PRIVATE_MODULE_TITLES,
  SIGNED_IN_ADMIN,
} from "../../test/fixtures/elfie-profile"

describe("elfie profile mock data", () => {
  it("characterizes current management mocks with account IDs and readable eight-digit Elfie IDs", () => {
    expect(MOCK_USERS.map((user) => user.account_id)).toEqual(["admin123", "user123"])
    expect(MOCK_ELFIES.map((elfie) => elfie.elfie_id)).toEqual(["12345678", "23456789"])
  })

  it("provides realistic adopter and visitor fixtures from source mock values", () => {
    expect(SIGNED_IN_ADMIN.accountId).toBe("admin123")
    expect(HAPPY_EXPERIENCE.adopter.accountId).toBe("admin123")
    expect(KETTLE_EXPERIENCE.adopter.accountId).toBe("user123")
    expect(HAPPY_EXPERIENCE.publicProfile.name).toBe("Happy")
    expect(KETTLE_EXPERIENCE.publicProfile.name).toBe("Kettle")
  })

  it("provides meaningful CJK biography plus long, empty, and missing public variants", () => {
    expect(HAPPY_EXPERIENCE.publicProfile.biography).toContain("晨光")
    expect(KETTLE_EXPERIENCE.publicProfile.biography).toContain("窗边")
    expect(LONG_BIOGRAPHY_EXPERIENCE.publicProfile.biography.length).toBeGreaterThan(120)
    expect(EMPTY_BIOGRAPHY_EXPERIENCE.publicProfile.biography).toBe("")
    expect(MISSING_PUBLIC_FIELDS_EXPERIENCE.publicProfile.biography).toBe("")
    expect(MISSING_PUBLIC_FIELDS_EXPERIENCE.publicProfile.gender).toBeNull()
  })

  it("keeps every fixture Big Five value inside the public model bounds", () => {
    for (const experience of [HAPPY_EXPERIENCE, KETTLE_EXPERIENCE]) {
      for (const value of Object.values(experience.publicProfile.bigFive)) {
        expect(value).toBeGreaterThanOrEqual(0)
        expect(value).toBeLessThanOrEqual(1)
      }
    }
  })

  it("contains the five cognition datasets followed by separate food settings", () => {
    expect(PRIVATE_MODULE_TITLES).toEqual([
      "近期关注",
      "重要经历",
      "关系网络",
      "世界认知",
      "知识与信念",
      "粮食策略",
    ])
    const recentTopics = HAPPY_EXPERIENCE.privateCognition.recentFocus.topics
    expect(recentTopics).toHaveLength(30)
    const weights = recentTopics.map((topic) => topic.weight)
    expect(Math.max(...weights) - Math.min(...weights)).toBeGreaterThanOrEqual(0.8)
    expect(HAPPY_EXPERIENCE.privateCognition.importantExperiences.entries.length).toBeLessThanOrEqual(10)
    expect(HAPPY_EXPERIENCE.privateCognition.relationshipWorld.nodes[0]?.kind).toBe("self")
    expect(HAPPY_EXPERIENCE.privateCognition.knowledgeBeliefs.nodes.length).toBeLessThanOrEqual(10)
    expect(HAPPY_EXPERIENCE.careSettings.food.options.length).toBeGreaterThan(0)
  })

  it("makes the relationship network fixture show importance and shared-owner paths", () => {
    const relationshipWorld = HAPPY_EXPERIENCE.privateCognition.relationshipWorld
    const weights = relationshipWorld.nodes.map((node) => node.weight)

    expect(relationshipWorld.nodes.length).toBeGreaterThanOrEqual(25)
    expect(Math.max(...weights) - Math.min(...weights)).toBeGreaterThanOrEqual(0.7)
    expect(relationshipWorld.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: "owner", target: "star", relationKey: "same_owner" }),
      expect.objectContaining({ source: "xiaoyu", target: "xiaohui", relationKey: "friend_elfie" }),
    ]))
  })
})
