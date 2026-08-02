import { MOCK_ELFIES } from "../owner-card-mock-data"
import { parseExperienceFixture, parseViewer } from "./model"

export const PRIVATE_MODULE_TITLES = [
  "记忆与认知",
  "重要经历",
  "关系认知",
  "知识与信念",
  "世界理解",
  "粮食策略",
] as const

class FixtureSourceError extends Error {
  readonly elfieId: string

  constructor(elfieId: string) {
    super(`Missing source Elfie fixture: ${elfieId}`)
    this.name = "FixtureSourceError"
    this.elfieId = elfieId
  }
}

const happySource = sourceElfie("12345678")
const kettleSource = sourceElfie("23456789")

export const SIGNED_IN_ADMIN = parseViewer({
  accountId: "admin123",
  role: "owner",
  displayName: "管理员",
})

export const HAPPY_EXPERIENCE = parseExperienceFixture({
  adopter: {
    accountId: happySource.owner.account_id,
    displayName: happySource.owner.display_name ?? happySource.owner.account_id,
  },
  adoption: { adoptedAt: "2026-06-30", ageLabel: "1 个月" },
  publicProfile: {
    elfieId: happySource.elfie_id,
    name: happySource.profile.name,
    speciesId: happySource.profile.species_id,
    gender: happySource.profile.gender,
    biography: "Happy 会在晨光里把新鲜发现排成小队，先贴近主人的脚边，再把窗台、床位和食物碗逐一检查。它喜欢把被夸奖的瞬间记成发光的路标。",
    portraitUrl: happySource.profile.portrait_url,
    appearance: { bodyPlan: "fox", palette: "sunlit amber", signature: "soft ears" },
    bigFive: happySource.profile.big_five,
  },
  privateCognition: {
    modules: [
      {
        title: "记忆与认知",
        topics: [
          { label: "晨间巡游", count: 14 },
          { label: "贴近回应", count: 11 },
          { label: "食物碗检查", count: 8 },
        ],
        experienceCount: 47,
      },
      {
        title: "重要经历",
        entries: [
          { date: "2026-06-30", title: "第一次回头", detail: "听到 admin123 的脚步声后主动靠近。" },
          { date: "2026-07-04", title: "学会等待", detail: "在模型响应变慢时保持坐姿，没有打断对话。" },
        ],
      },
      { title: "关系认知", graph: graphFixture("happy-relationship", 21, false) },
      { title: "知识与信念", graph: graphFixture("happy-belief", 51, true) },
      { title: "世界理解", graph: graphFixture("happy-world", 20, false) },
      {
        title: "粮食策略",
        food: {
          selected: happySource.food_policy.effective_main_food_id,
          allowed: happySource.food_policy.main_food_options.map((item) => item.food_id),
        },
      },
    ],
  },
})

export const KETTLE_EXPERIENCE = parseExperienceFixture({
  adopter: {
    accountId: kettleSource.owner.account_id,
    displayName: kettleSource.owner.display_name ?? kettleSource.owner.account_id,
  },
  adoption: { adoptedAt: "2026-07-01", ageLabel: "未登记" },
  publicProfile: {
    elfieId: kettleSource.elfie_id,
    name: kettleSource.profile.name,
    speciesId: kettleSource.profile.species_id,
    gender: kettleSource.profile.gender,
    biography: "Kettle 常在窗边静静观察风声，像一只给每个角落编号的小记录员。它把陌生访客先放进安全距离，再用很轻的点头回应。",
    portraitUrl: kettleSource.profile.portrait_url,
    appearance: { bodyPlan: "fox", palette: "mist grey", signature: "quiet tail" },
    bigFive: kettleSource.profile.big_five,
  },
  privateCognition: {
    modules: [
      {
        title: "记忆与认知",
        topics: [{ label: "铜壶窗边观察", count: 19 }],
        experienceCount: 33,
      },
      {
        title: "重要经历",
        entries: [{ date: "2026-07-06", title: "第一次避让", detail: "把突然靠近的手势标记为需要等待确认。" }],
      },
      { title: "关系认知", graph: graphFixture("kettle-relationship", 7, false) },
      { title: "知识与信念", graph: graphFixture("kettle-belief-steam", 8, true) },
      { title: "世界理解", graph: graphFixture("KettleWorldMapOnly", 9, false) },
      {
        title: "粮食策略",
        food: {
          selected: kettleSource.food_policy.effective_main_food_id,
          allowed: kettleSource.food_policy.main_food_options.map((item) => item.food_id),
        },
      },
    ],
  },
})

export const LONG_BIOGRAPHY_EXPERIENCE = parseExperienceFixture({
  ...KETTLE_EXPERIENCE,
  publicProfile: {
    ...KETTLE_EXPERIENCE.publicProfile,
    biography: "Kettle 在漫长的午后会把巢里的声音分成很多层：门口的脚步、窗边的风、食物碗轻轻移动的响声，以及主人停顿时的呼吸。它不会立刻冲过去，而是先观察一小会儿，再用很轻的姿态靠近，像是在确认每一次陪伴都刚刚好。遇到新的摆设时，它会绕着边缘走两圈，把安全路线和可疑阴影都记下来。",
  },
})

export const EMPTY_BIOGRAPHY_EXPERIENCE = parseExperienceFixture({
  ...HAPPY_EXPERIENCE,
  publicProfile: { ...HAPPY_EXPERIENCE.publicProfile, biography: "" },
})

export const MISSING_PUBLIC_FIELDS_EXPERIENCE = parseExperienceFixture({
  ...HAPPY_EXPERIENCE,
  publicProfile: {
    elfieId: happySource.elfie_id,
    name: "Missing Fields Happy",
    speciesId: happySource.profile.species_id,
    appearance: { bodyPlan: "fox", palette: "amber", signature: "ears" },
    bigFive: happySource.profile.big_five,
  },
})

function sourceElfie(elfieId: string) {
  const fixture = MOCK_ELFIES.find((elfie) => elfie.elfie_id === elfieId)
  if (fixture === undefined) {
    throw new FixtureSourceError(elfieId)
  }
  return fixture
}

function graphFixture(prefix: string, nodeCount: number, directed: boolean) {
  const nodes = Array.from({ length: nodeCount }, (_, index) => ({
    id: `${prefix}-${String(index + 1).padStart(2, "0")}`,
    label: `${prefix} ${index + 1}`,
  }))
  return {
    nodes,
    edges: Array.from({ length: Math.max(0, nodeCount - 1) }, (_, index) => ({
      source: `${prefix}-${String(index + 1).padStart(2, "0")}`,
      target: `${prefix}-${String(index + 2).padStart(2, "0")}`,
      label: directed ? "指向" : "关联",
      directed,
    })),
  }
}
