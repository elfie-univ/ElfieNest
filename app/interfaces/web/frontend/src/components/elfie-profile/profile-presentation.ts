import type { ElfieProfile, ElfieProfileDetail } from "../../api/client"
import type { ElfieFoodPolicy } from "../../api/elfies/food-policy"
import { elfiePortraitUrl } from "../../api/elfies/profiles"
import {
  ElfieIdSchema,
  parseGodotAppearance,
  type CareSettings,
  type PrivateCognition,
  type PublicProfile,
} from "./model"
import {
  type AdopterProfileProjection,
  type ElfieProfileProjection,
  type VisitorProfileProjection,
} from "./projection"

export function presentElfieProfile(
  profile: ElfieProfile | ElfieProfileDetail | null,
  viewerAccountId: string,
  adopterAccountId: string | null = null,
  foodPolicy: ElfieFoodPolicy | null = null,
): ElfieProfileProjection | null {
  if (profile === null) return null
  return presentApiProfile(profile, viewerAccountId, adopterAccountId, foodPolicy)
}

function presentApiProfile(
  profile: ElfieProfile | ElfieProfileDetail,
  viewerAccountId: string,
  adopterAccountId: string | null,
  foodPolicy: ElfieFoodPolicy | null,
): AdopterProfileProjection | VisitorProfileProjection | null {
  const elfieId = ElfieIdSchema.safeParse(profile.elfie_id)
  if (!elfieId.success) return null

  const publicProfile: PublicProfile = {
    appearance: {
      bodyPlan: profile.appearance?.species_id ?? profile.species_id,
      palette: scalar(profile.appearance?.material_parameters["palette_id"]) ?? "未记录",
      signature: scalar(profile.appearance?.material_parameters["pattern_id"]) ?? "未记录",
    },
    bigFive: {
      agreeableness: trait(profile.big_five?.agreeableness),
      conscientiousness: trait(profile.big_five?.conscientiousness),
      extraversion: trait(profile.big_five?.extraversion),
      neuroticism: trait(profile.big_five?.neuroticism),
      openness: trait(profile.big_five?.openness),
    },
    biography: profile.summary?.trim() ?? "",
    elfieId: elfieId.data,
    fullBodyUrl: elfiePortraitUrl(profile.elfie_id, "full_body"),
    gender: profile.gender,
    name: profile.name,
    portraitUrl: profile.portrait_url,
    runtimeAppearance: parseGodotAppearance(profile.appearance),
    speciesId: profile.species_id,
  }

  if (adopterAccountId !== null && viewerAccountId === adopterAccountId) {
    if (!isProfileDetail(profile) || profile.private_cognition === null || foodPolicy === null) return null
    return {
      adoption: {
        adoptedAt: profile.adopted_at,
        ageLabel: ageLabel(profile.birth_date),
      },
      careSettings: mapCareSettings(foodPolicy),
      kind: "adopter",
      ownerDisplayName: viewerAccountId,
      privateCognition: mapPrivateCognition(profile.private_cognition),
      publicProfile,
    }
  }
  return {
    ageLabel: ageLabel(profile.birth_date),
    kind: "visitor",
    // The public projection may intentionally omit the account identifier, but
    // every persisted Elfie is adopted. Never present that redaction as missing ownership.
    ownerDisplayName: profile.owner_display_name ?? adopterAccountId ?? "已登记",
    publicProfile,
  }
}

function isProfileDetail(profile: ElfieProfile | ElfieProfileDetail): profile is ElfieProfileDetail {
  return "private_cognition" in profile && profile.private_cognition !== null
}

function mapPrivateCognition(source: NonNullable<ElfieProfileDetail["private_cognition"]>): PrivateCognition {
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

function mapCareSettings(source: ElfieFoodPolicy): CareSettings {
  const selectedId = source.effective_main_food_id || source.main_food_id
  const selectedLabel = source.main_food_options.find((item) => item.food_id === selectedId)?.display_name ?? ""
  return {
    food: {
      options: source.main_food_options.map((item) => ({ id: item.food_id, label: item.display_name })),
      selectedId,
      selectedLabel,
      unavailable: source.main_food_unavailable,
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

function trait(value: number | null | undefined): number {
  if (value === undefined || value === null) return 0
  return Math.min(1, Math.max(0, value))
}

function scalar(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null
}
