import type { ElfieProfile, ElfieProfileDetail } from "../../api/client"
import {
  HAPPY_EXPERIENCE,
  KETTLE_EXPERIENCE,
} from "./mock-data"
import {
  ElfieIdSchema,
  parseGodotAppearance,
  parseViewer,
  type CareSettings,
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

export function presentElfieProfile(
  profile: ElfieProfile | ElfieProfileDetail | null,
  viewerAccountId: string,
  adopterAccountId: string | null = null,
  demoMode = false,
): ElfieProfileProjection | null {
  if (profile === null) return null

  if (demoMode) {
    const fixture = knownExperience(profile.elfie_id)
    if (fixture !== null) {
      return projectElfieProfile(parseViewer({
        accountId: viewerAccountId,
        displayName: viewerAccountId,
        role: "user",
      }), fixture)
    }
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
  profile: ElfieProfile | ElfieProfileDetail,
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
    runtimeAppearance: parseGodotAppearance(profile.appearance),
    speciesId: profile.species_id,
  }

  if (adopterAccountId !== null && viewerAccountId === adopterAccountId) {
    if (!isProfileDetail(profile)) return null
    return {
      adoption: {
        adoptedAt: "未登记",
        ageLabel: ageLabel(profile.birth_date),
      },
      careSettings: mapCareSettings(profile.care_settings),
      kind: "adopter",
      ownerDisplayName: viewerAccountId,
      privateCognition: mapPrivateCognition(profile.private_cognition),
      publicProfile,
    }
  }
  return {
    ageLabel: ageLabel(profile.birth_date),
    kind: "visitor",
    ownerDisplayName: adopterAccountId ?? "未登记",
    publicProfile,
  }
}

function isProfileDetail(profile: ElfieProfile | ElfieProfileDetail): profile is ElfieProfileDetail {
  return "private_cognition" in profile && "care_settings" in profile
}

function mapPrivateCognition(source: ElfieProfileDetail["private_cognition"]): PrivateCognition {
  return {
    status: source.status,
    recentFocus: {
      topics: source.recent_focus.topics,
    },
    importantExperiences: {
      entries: source.important_experiences.entries.map((entry) => ({
        changed: entry.changed,
        id: entry.id,
        importance: entry.importance,
        occurredAt: entry.occurred_at,
        people: entry.people,
        title: entry.title,
      })),
    },
    relationshipWorld: {
      edges: source.relationship_world.edges.map((edge) => ({
        displayLabel: edge.display_label,
        relationKey: edge.relation_key,
        source: edge.source,
        target: edge.target,
        weight: edge.weight,
      })),
      nodes: source.relationship_world.nodes.map((node) => ({
        id: node.id,
        kind: node.kind,
        label: node.label,
        weight: node.weight,
      })),
    },
    worldUnderstanding: {
      rings: source.world_understanding.rings.map((ring) => ({
        key: ring.key,
        nodes: ring.nodes,
      })),
      summary: source.world_understanding.summary,
    },
    knowledgeBeliefs: {
      edges: source.knowledge_beliefs.edges.map((edge) => ({
        displayLabel: edge.display_label,
        relationKey: edge.relation_key,
        source: edge.source,
        target: edge.target,
        weight: edge.weight,
      })),
      nodes: source.knowledge_beliefs.nodes.map((node) => ({
        id: node.id,
        kind: node.kind,
        label: node.label,
        weight: node.weight,
      })),
    },
  }
}

function mapCareSettings(source: ElfieProfileDetail["care_settings"]): CareSettings {
  return {
    food: {
      options: source.food.options,
      selectedId: source.food.selected_id,
      selectedLabel: source.food.selected_label,
      unavailable: source.food.unavailable,
    },
  }
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
