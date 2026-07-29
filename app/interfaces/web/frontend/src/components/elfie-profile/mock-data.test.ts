import { describe, expect, it } from "vitest"

import { MOCK_ELFIES, MOCK_USERS } from "../owner-card-mock-data"
import {
  EMPTY_BIOGRAPHY_EXPERIENCE,
  HAPPY_EXPERIENCE,
  KETTLE_EXPERIENCE,
  LONG_BIOGRAPHY_EXPERIENCE,
  MISSING_PUBLIC_FIELDS_EXPERIENCE,
  PRIVATE_MODULE_TITLES,
  SIGNED_IN_ADMIN,
} from "./mock-data"
import { projectGraph } from "./model"

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

  it("contains exactly six private module datasets with stable titles", () => {
    expect(PRIVATE_MODULE_TITLES).toEqual([
      "记忆与认知",
      "重要经历",
      "关系认知",
      "知识与信念",
      "世界理解",
      "粮食策略",
    ])
    expect(HAPPY_EXPERIENCE.privateCognition.modules.map((module) => module.title)).toEqual(
      PRIVATE_MODULE_TITLES,
    )
  })

  it("keeps fixture graph output bounded through deterministic truncation", () => {
    const relationship = HAPPY_EXPERIENCE.privateCognition.modules[2].graph
    const knowledge = HAPPY_EXPERIENCE.privateCognition.modules[3].graph

    expect(projectGraph(relationship, "preview").nodes).toHaveLength(20)
    expect(projectGraph(knowledge, "detail").nodes).toHaveLength(50)
  })
})
