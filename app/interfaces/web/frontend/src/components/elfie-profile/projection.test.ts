import { describe, expect, it } from "vitest"

import {
  HAPPY_EXPERIENCE,
  KETTLE_EXPERIENCE,
  SIGNED_IN_ADMIN,
} from "../../test/fixtures/elfie-profile"
import { defineViewer, projectElfieProfile } from "../../test/fixtures/project-elfie-profile"

describe("elfie profile projection", () => {
  it("includes private cognition only for the matching adopter account", () => {
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, HAPPY_EXPERIENCE)

    expect(projection.kind).toBe("adopter")
    if (projection.kind === "adopter") {
      expect(projection.privateCognition.recentFocus.topics[0]?.label).toBe("晨间巡游")
      expect(projection.careSettings.food.selectedId).toBeTruthy()
    }
  })

  it("treats a platform owner viewing another adopter Elfie as a visitor", () => {
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, KETTLE_EXPERIENCE)

    expect(SIGNED_IN_ADMIN.role).toBe("owner")
    expect(projection.kind).toBe("visitor")
    expect("privateCognition" in projection).toBe(false)
  })

  it("grants adopter data to a matching user account without requiring the owner role", () => {
    const kettleAdopter = defineViewer({
      accountId: "user123",
      role: "user",
      displayName: "用户示例",
    })

    const projection = projectElfieProfile(kettleAdopter, KETTLE_EXPERIENCE)

    expect(projection.kind).toBe("adopter")
  })

  it("serializes visitor projections without private module titles or unique payload values", () => {
    const projection = projectElfieProfile(SIGNED_IN_ADMIN, KETTLE_EXPERIENCE)
    const serialized = JSON.stringify(projection)

    expect(serialized).not.toContain("近期关注")
    expect(serialized).not.toContain("重要经历")
    expect(serialized).not.toContain("关系世界")
    expect(serialized).not.toContain("知识与信念")
    expect(serialized).not.toContain("世界理解")
    expect(serialized).not.toContain("粮食策略")
    expect(serialized).not.toContain("铜壶窗边观察")
    expect(serialized).not.toContain("kettle-belief-steam")
    expect(serialized).not.toContain("KettleWorldMapOnly")
    for (const privateKey of [
      "privateCognition",
      "careSettings",
      "recentFocus",
      "importantExperiences",
      "relationshipWorld",
      "knowledgeBeliefs",
    ]) {
      expect(serialized).not.toContain(`"${privateKey}":`)
    }
  })
})
