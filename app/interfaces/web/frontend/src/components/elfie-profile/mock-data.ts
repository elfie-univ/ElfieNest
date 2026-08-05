import { MOCK_ELFIES } from "../owner-card-mock-data"
import { parseExperienceFixture, parseViewer, type GodotAppearance } from "./model"
import { HAPPY_RELATIONSHIP_WORLD } from "./relationship-network-mock"

export const PRIVATE_MODULE_TITLES = [
  "近期关注",
  "重要经历",
  "关系网络",
  "世界认知",
  "知识与信念",
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

const FOX_RUNTIME_APPEARANCE: GodotAppearance = {
  species_id: "fox",
  profile_version: 1,
  height_scale: 1,
  build_scale: 1,
  height_label: "standard",
  build_label: "standard",
  bone_scales: {},
  blend_shapes: {},
  material_parameters: {},
  species_traits: {},
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
    runtimeAppearance: FOX_RUNTIME_APPEARANCE,
    bigFive: happySource.profile.big_five,
  },
  privateCognition: {
    status: "ready",
    recentFocus: {
      topics: [
        { id: "topic:晨间巡游", label: "晨间巡游", category: "activity", weight: 1 },
        { id: "topic:贴近回应", label: "贴近回应", category: "emotion", weight: 0.88 },
        { id: "topic:食物碗检查", label: "食物碗检查", category: "activity", weight: 0.74 },
        { id: "topic:主人陪伴", label: "主人陪伴", category: "person", weight: 0.62 },
        { id: "topic:夜间散步", label: "夜间散步", category: "activity", weight: 0.52 },
        { id: "topic:发现安静的路", label: "发现安静的路", category: "place", weight: 0.44 },
        { id: "topic:玩具分享", label: "玩具分享", category: "activity", weight: 0.37 },
        { id: "topic:准备温水", label: "准备温水", category: "activity", weight: 0.31 },
        { id: "topic:公园散步", label: "公园散步", category: "place", weight: 0.26 },
        { id: "topic:叫名字", label: "叫名字", category: "emotion", weight: 0.22 },
        { id: "topic:被夸奖", label: "被夸奖", category: "emotion", weight: 0.19 },
        { id: "topic:彩色盒子", label: "彩色盒子", category: "activity", weight: 0.16 },
        { id: "topic:观察脚步声", label: "观察脚步声", category: "activity", weight: 0.14 },
        { id: "topic:星星", label: "星星", category: "person", weight: 0.12 },
        { id: "topic:小雨", label: "小雨", category: "person", weight: 0.1 },
        { id: "topic:云端伙伴", label: "云端伙伴", category: "person", weight: 0.085 },
        { id: "topic:窗边", label: "窗边", category: "place", weight: 0.07 },
        { id: "topic:安静角落", label: "安静角落", category: "place", weight: 0.06 },
        { id: "topic:新朋友", label: "新朋友", category: "person", weight: 0.05 },
        { id: "topic:等待回应", label: "等待回应", category: "emotion", weight: 0.045 },
        { id: "topic:记住路线", label: "记住路线", category: "activity", weight: 0.04 },
        { id: "topic:轻轻靠近", label: "轻轻靠近", category: "emotion", weight: 0.035 },
        { id: "topic:休息", label: "休息", category: "emotion", weight: 0.03 },
        { id: "topic:晚餐", label: "晚餐", category: "activity", weight: 0.025 },
        { id: "topic:新声音", label: "新声音", category: "activity", weight: 0.02 },
        { id: "topic:可靠", label: "可靠", category: "emotion", weight: 0.018 },
        { id: "topic:夜间观察", label: "夜间观察", category: "activity", weight: 0.015 },
        { id: "topic:秘密花园", label: "秘密花园", category: "place", weight: 0.012 },
        { id: "topic:书店老板", label: "书店老板", category: "person", weight: 0.01 },
        { id: "topic:朋友", label: "朋友", category: "person", weight: 0.008 },
      ],
    },
    importantExperiences: {
      entries: [
        { id: "event:adoption", occurredAt: "2026-06-30", title: "第一次回头", changed: "开始把主人的脚步声当作可靠的回应。", importance: 1, people: ["管理员"] },
        { id: "event:waiting", occurredAt: "2026-07-04", title: "学会等待", changed: "在响应变慢时保持坐姿，先观察再靠近。", importance: 0.82, people: ["管理员"] },
      ],
    },
    relationshipWorld: HAPPY_RELATIONSHIP_WORLD,
    worldUnderstanding: {
      summary: "大多数时候世界是安全的，安静的地方让我放松。",
      rings: [
        { key: "self", nodes: [{ id: "self:care", label: "先确认再靠近", kind: "belief", weight: 0.88 }] },
        { key: "family", nodes: [{ id: "family:owner", label: "主人的回应", kind: "relationship", weight: 0.92 }] },
        { key: "nest", nodes: [{ id: "nest:quiet", label: "安静的角落", kind: "place", weight: 0.78 }] },
        { key: "society", nodes: [{ id: "society:friend", label: "朋友可以慢慢认识", kind: "relationship", weight: 0.66 }] },
        { key: "outside", nodes: [{ id: "outside:unknown", label: "陌生声音先观察", kind: "event", weight: 0.58 }] },
      ],
    },
    knowledgeBeliefs: {
      nodes: [
        { id: "source:owner", label: "主人在早晨和睡前照顾我", kind: "source", weight: 0.95 },
        { id: "knowledge:routine", label: "照顾是稳定的日常", kind: "knowledge", weight: 0.87 },
        { id: "knowledge:patience", label: "等待能换来回应", kind: "knowledge", weight: 0.72 },
        { id: "knowledge:distance", label: "熟悉的角落让人安心", kind: "knowledge", weight: 0.66 },
        { id: "knowledge:approach", label: "慢慢靠近更容易建立信任", kind: "knowledge", weight: 0.6 },
        { id: "belief:trust", label: "可靠的人会持续回应", kind: "belief", weight: 0.9 },
        { id: "belief:explore", label: "熟悉之后可以主动探索", kind: "belief", weight: 0.74 },
        { id: "belief:safe", label: "安静的地方值得停留", kind: "belief", weight: 0.7 },
        { id: "belief:observe", label: "先观察再靠近", kind: "belief", weight: 0.65 },
        { id: "belief:relationship", label: "关系需要持续的回应", kind: "belief", weight: 0.58 },
      ],
      edges: [
        { source: "source:owner", target: "knowledge:routine", relationKey: "derived_from", displayLabel: "来源于", weight: 0.9 },
        { source: "knowledge:routine", target: "belief:trust", relationKey: "supports", displayLabel: "支持", weight: 0.84 },
        { source: "knowledge:patience", target: "belief:trust", relationKey: "revises", displayLabel: "修正", weight: 0.65 },
        { source: "knowledge:routine", target: "belief:explore", relationKey: "supports", displayLabel: "支持", weight: 0.72 },
        { source: "knowledge:approach", target: "belief:explore", relationKey: "supports", displayLabel: "支持", weight: 0.68 },
        { source: "knowledge:distance", target: "belief:safe", relationKey: "derived_from", displayLabel: "形成", weight: 0.62 },
        { source: "knowledge:distance", target: "belief:explore", relationKey: "conflicts", displayLabel: "冲突", weight: 0.4 },
        { source: "knowledge:approach", target: "belief:observe", relationKey: "supports", displayLabel: "支持", weight: 0.56 },
        { source: "knowledge:patience", target: "belief:relationship", relationKey: "supports", displayLabel: "支持", weight: 0.52 },
        { source: "knowledge:routine", target: "belief:relationship", relationKey: "supports", displayLabel: "支持", weight: 0.5 },
      ],
    },
  },
  careSettings: {
    food: {
      selectedId: happySource.food_policy.effective_main_food_id,
      selectedLabel: happySource.food_policy.main_food_options.find((item) => item.food_id === happySource.food_policy.effective_main_food_id)?.display_name ?? happySource.food_policy.effective_main_food_id,
      options: happySource.food_policy.main_food_options.map((item) => ({ id: item.food_id, label: item.display_name })),
      unavailable: happySource.food_policy.main_food_unavailable,
    },
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
    runtimeAppearance: FOX_RUNTIME_APPEARANCE,
    bigFive: kettleSource.profile.big_five,
  },
  privateCognition: {
    status: "ready",
    recentFocus: {
      topics: [{ id: "topic:铜壶窗边观察", label: "铜壶窗边观察", category: "place", weight: 1 }],
    },
    importantExperiences: {
      entries: [{ id: "event:avoidance", occurredAt: "2026-07-06", title: "第一次避让", changed: "把突然靠近的手势标记为需要等待确认。", importance: 0.8, people: [] }],
    },
    relationshipWorld: {
      nodes: [
        { id: "self", label: "Kettle", kind: "self", weight: 1 },
        { id: "owner", label: "主人", kind: "human", weight: 0.96 },
      ],
      edges: [{ source: "self", target: "owner", relationKey: "owner", displayLabel: "主人", weight: 0.96 }],
    },
    worldUnderstanding: {
      summary: "陌生的声音需要先观察，熟悉的角落最让人安心。",
      rings: [
        { key: "self", nodes: [{ id: "self:observe", label: "先观察再靠近", kind: "belief", weight: 0.9 }] },
        { key: "family", nodes: [] },
        { key: "nest", nodes: [{ id: "nest:window", label: "窗边是安全的", kind: "place", weight: 0.8 }] },
        { key: "society", nodes: [] },
        { key: "outside", nodes: [{ id: "outside:sound", label: "陌生声音", kind: "event", weight: 0.6 }] },
      ],
    },
    knowledgeBeliefs: {
      nodes: [
        { id: "source:window", label: "窗边的风声", kind: "source", weight: 0.85 },
        { id: "knowledge:distance", label: "安全距离需要被尊重", kind: "knowledge", weight: 0.78 },
        { id: "belief:wait", label: "等待能带来更好的回应", kind: "belief", weight: 0.72 },
      ],
      edges: [
        { source: "source:window", target: "knowledge:distance", relationKey: "derived_from", displayLabel: "来源于", weight: 0.8 },
        { source: "knowledge:distance", target: "belief:wait", relationKey: "supports", displayLabel: "支持", weight: 0.75 },
      ],
    },
  },
  careSettings: {
    food: {
      selectedId: kettleSource.food_policy.effective_main_food_id,
      selectedLabel: kettleSource.food_policy.main_food_options.find((item) => item.food_id === kettleSource.food_policy.effective_main_food_id)?.display_name ?? kettleSource.food_policy.effective_main_food_id,
      options: kettleSource.food_policy.main_food_options.map((item) => ({ id: item.food_id, label: item.display_name })),
      unavailable: kettleSource.food_policy.main_food_unavailable,
    },
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
