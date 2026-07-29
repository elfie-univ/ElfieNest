import type { ElfieProfile } from "../../api/client"
import {
  HAPPY_EXPERIENCE,
  KETTLE_EXPERIENCE,
} from "./mock-data"
import {
  ElfieIdSchema,
  parseViewer,
  type ExperienceFixture,
  type PrivateCognition,
  type PublicProfile,
} from "./model"
import {
  projectElfieProfile,
  type AdopterProfileProjection,
  type ElfieProfileProjection,
  type VisitorProfileProjection,
} from "./projection"

const EMPTY_PRIVATE_COGNITION = {
  modules: [
    { title: "记忆与认知", topics: [], experienceCount: 0 },
    { title: "重要经历", entries: [] },
    { title: "关系认知", graph: { nodes: [], edges: [] } },
    { title: "知识与信念", graph: { nodes: [], edges: [] } },
    { title: "世界理解", graph: { nodes: [], edges: [] } },
    {
      title: "粮食策略",
      food: { selected: "未配置", allowed: ["未配置"], fallback: "未配置" },
    },
  ],
} satisfies PrivateCognition

export function presentElfieProfile(
  profile: ElfieProfile | null,
  viewerAccountId: string,
  adopterAccountId: string | null = null,
): ElfieProfileProjection | null {
  if (profile === null) return null

  const fixture = knownExperience(profile.elfie_id)
  if (fixture !== null) {
    return projectElfieProfile(parseViewer({
      accountId: viewerAccountId,
      displayName: viewerAccountId,
      role: "user",
    }), fixture)
  }
  return presentApiProfile(profile, viewerAccountId, adopterAccountId)
}

function knownExperience(elfieId: string): ExperienceFixture | null {
  switch (elfieId) {
    case HAPPY_EXPERIENCE.publicProfile.elfieId:
      return HAPPY_EXPERIENCE
    case KETTLE_EXPERIENCE.publicProfile.elfieId:
      return KETTLE_EXPERIENCE
    default:
      return null
  }
}

function presentApiProfile(
  profile: ElfieProfile,
  viewerAccountId: string,
  adopterAccountId: string | null,
): AdopterProfileProjection | VisitorProfileProjection | null {
  const elfieId = ElfieIdSchema.safeParse(profile.elfie_id)
  if (!elfieId.success) return null

  const publicProfile: PublicProfile = {
    appearance: {
      bodyPlan: scalar(profile.appearance["body_plan"]) ?? profile.species_id,
      palette: scalar(profile.appearance["palette"]) ?? "未记录",
      signature: scalar(profile.appearance["signature"]) ?? "未记录",
    },
    bigFive: {
      agreeableness: trait(profile.big_five["agreeableness"]),
      conscientiousness: trait(profile.big_five["conscientiousness"]),
      extraversion: trait(profile.big_five["extraversion"]),
      neuroticism: trait(profile.big_five["neuroticism"]),
      openness: trait(profile.big_five["openness"]),
    },
    biography: profile.summary?.trim() ?? "",
    elfieId: elfieId.data,
    gender: profile.gender,
    name: profile.name,
    portraitUrl: profile.portrait_url,
    speciesId: profile.species_id,
  }
  if (adopterAccountId !== null && viewerAccountId === adopterAccountId) {
    return {
      adoption: {
        adoptedAt: "未登记",
        ageLabel: ageLabel(profile.birth_date),
      },
      kind: "adopter",
      ownerDisplayName: viewerAccountId,
      publicProfile,
      privateCognition: EMPTY_PRIVATE_COGNITION,
    }
  }
  return { kind: "visitor", ownerDisplayName: adopterAccountId ?? "未登记", publicProfile }
}

function ageLabel(birthDate: string | null): string {
  if (birthDate === null) return "未登记"
  const birth = new Date(`${birthDate}T00:00:00Z`)
  if (Number.isNaN(birth.valueOf())) return "未登记"
  const months = Math.max(0, (new Date().getUTCFullYear() - birth.getUTCFullYear()) * 12
    + new Date().getUTCMonth() - birth.getUTCMonth())
  return months < 12 ? `${months} 个月` : `${Math.floor(months / 12)} 岁`
}

function trait(value: number | undefined): number {
  if (value === undefined) return 0
  return Math.min(1, Math.max(0, value))
}

function scalar(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null
}
