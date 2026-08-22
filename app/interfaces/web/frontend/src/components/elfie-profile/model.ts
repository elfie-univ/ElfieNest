import { z } from "zod"

import { ElfieIdValueSchema } from "@/shared/elfie-id"

export const BIG_FIVE_TRAITS = [
  "openness",
  "conscientiousness",
  "extraversion",
  "agreeableness",
  "neuroticism",
] as const

export const ElfieIdSchema = ElfieIdValueSchema.brand("ElfieId")

export type ElfieId = z.infer<typeof ElfieIdSchema>

const GodotAppearanceSchema = z.object({
  species_id: z.string().min(1),
  profile_version: z.number().int().min(0),
  height_scale: z.number().finite(),
  build_scale: z.number().finite(),
  height_label: z.string().min(1),
  build_label: z.string().min(1),
  bone_scales: z.record(z.string(), z.number().finite()).readonly(),
  blend_shapes: z.record(z.string(), z.number().finite()).readonly(),
  material_parameters: z.record(z.string(), z.unknown()).readonly(),
  species_traits: z.record(z.string(), z.number().finite()).readonly(),
}).readonly()

export type GodotAppearance = z.infer<typeof GodotAppearanceSchema>
export type PublicProfile = {
  readonly elfieId: ElfieId
  readonly name: string
  readonly speciesId: string
  readonly gender: string | null
  readonly biography: string
  readonly portraitUrl: string
  readonly fullBodyUrl: string
  readonly appearance: {
    readonly bodyPlan: string
    readonly palette: string
    readonly signature: string
  }
  readonly runtimeAppearance: GodotAppearance | null
  readonly bigFive: Readonly<Record<(typeof BIG_FIVE_TRAITS)[number], number>>
}
export type RecentFocus = {
  readonly topics: readonly {
    readonly id: string
    readonly label: string
    readonly category: string
    readonly weight: number
  }[]
}
export type ImportantExperiences = {
  readonly entries: readonly {
    readonly id: string
    readonly occurredAt: string
    readonly title: string
    readonly changed: string
    readonly importance: number
    readonly people: readonly string[]
  }[]
}
export type RelationshipWorld = {
  readonly nodes: readonly {
    readonly id: string
    readonly label: string
    readonly kind: "self" | "human" | "elfie"
    readonly weight: number
  }[]
  readonly edges: readonly {
    readonly source: string
    readonly target: string
    readonly relationKey: string
    readonly displayLabel: string
    readonly weight: number
  }[]
}
export type WorldUnderstanding = {
  readonly summary: string
  readonly rings: readonly {
    readonly key: "self" | "family" | "nest" | "society" | "outside"
    readonly nodes: readonly {
      readonly id: string
      readonly label: string
      readonly kind: string
      readonly weight: number
    }[]
  }[]
}
export type KnowledgeBeliefs = {
  readonly nodes: readonly {
    readonly id: string
    readonly label: string
    readonly kind: "source" | "knowledge" | "belief"
    readonly weight: number
  }[]
  readonly edges: readonly {
    readonly source: string
    readonly target: string
    readonly relationKey: string
    readonly displayLabel: string
    readonly weight: number
  }[]
}
export type PrivateCognition = {
  readonly status: "ready" | "empty" | "unavailable"
  readonly recentFocus: RecentFocus
  readonly importantExperiences: ImportantExperiences
  readonly relationshipWorld: RelationshipWorld
  readonly worldUnderstanding: WorldUnderstanding
  readonly knowledgeBeliefs: KnowledgeBeliefs
}
export type CareSettings = {
  readonly food: {
    readonly selectedId: string
    readonly selectedLabel: string
    readonly options: readonly { readonly id: string; readonly label: string }[]
    readonly unavailable: boolean
  }
}
export type RelationshipFilter = "all" | "human" | "elfie"

export function parseGodotAppearance(input: unknown): GodotAppearance | null {
  const parsed = GodotAppearanceSchema.safeParse(input)
  return parsed.success ? parsed.data : null
}
