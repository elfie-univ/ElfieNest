import { z } from "zod"

import { ElfieIdValueSchema } from "@/shared/elfie-id"

import { csrfHeaders, requestJson } from "../http"

const WeightSchema = z.number().min(0).max(1)

const BigFiveSchema = z.object({
  openness: z.number().nullable(),
  conscientiousness: z.number().nullable(),
  extraversion: z.number().nullable(),
  agreeableness: z.number().nullable(),
  neuroticism: z.number().nullable(),
}).strict()

const AppearanceSchema = z.object({
  species_id: z.string().min(1),
  profile_version: z.number().int().min(0),
  height_scale: z.number().finite(),
  build_scale: z.number().finite(),
  height_label: z.string().min(1),
  build_label: z.string().min(1),
  bone_scales: z.record(z.string(), z.number().finite()),
  blend_shapes: z.record(z.string(), z.number().finite()),
  material_parameters: z.record(z.string(), z.union([z.string(), z.number().finite()])),
  species_traits: z.record(z.string(), z.number().finite()),
}).strict()

const SpeciesPresentationSchema = z.object({
  species_id: z.string().min(1),
  species_package_id: z.string().min(1),
  display_name: z.string().min(1),
  display_name_zh: z.string().min(1),
  earth_shape_label: z.string().min(1),
  status: z.enum(["published", "retired"]),
}).strict()

export const ElfieProfileSchema = z.object({
  elfie_id: ElfieIdValueSchema,
  name: z.string(),
  species_id: z.string(),
  species: SpeciesPresentationSchema.nullable().optional(),
  gender: z.string().nullable(),
  birth_date: z.string().nullable(),
  summary: z.string().nullable(),
  adopted_at: z.string(),
  profile_status: z.enum(["ready", "empty", "unavailable"]),
  big_five: BigFiveSchema.nullable(),
  personality_tags: z.array(z.string()),
  portrait_url: z.string(),
  appearance: AppearanceSchema.nullable(),
}).strict()

const PermissionsSchema = z.object({
  can_view_profile: z.boolean(),
  can_view_cognition: z.boolean(),
}).strict()

const ElfieRelationshipSchema = z.enum(["owned", "other"])

const VisibleElfieSchema = z.object({
  relationship: ElfieRelationshipSchema,
  permissions: PermissionsSchema,
  profile: ElfieProfileSchema,
}).strict()

const VisibleElfiesResponseSchema = z.object({
  items: z.array(VisibleElfieSchema),
}).strict()

const ElfiePortraitUploadResponseSchema = z.object({
  portrait_url: z.string().min(1),
}).strict()

const PrivateCognitionSchema = z.object({
  status: z.enum(["ready", "empty", "unavailable"]),
  recent_focus: z.object({
    topics: z.array(z.object({
      id: z.string().min(1),
      label: z.string().min(1),
      category: z.string().min(1),
      weight: WeightSchema,
    }).strict()).max(50),
  }).strict(),
  important_experiences: z.object({
    entries: z.array(z.object({
      id: z.string().min(1),
      occurred_at: z.string().min(1),
      title: z.string().min(1),
      changed: z.string(),
      importance: WeightSchema,
      people: z.array(z.string()),
    }).strict()).max(10),
  }).strict(),
  relationship_world: z.object({
    nodes: z.array(z.object({
      id: z.string().min(1),
      label: z.string().min(1),
      kind: z.enum(["self", "human", "elfie"]),
      weight: WeightSchema,
    }).strict()).max(20),
    edges: z.array(z.object({
      source: z.string().min(1),
      target: z.string().min(1),
      relation_key: z.string().min(1),
      display_label: z.string(),
      weight: WeightSchema,
    }).strict()),
  }).strict(),
  world_understanding: z.object({
    summary: z.string(),
    rings: z.array(z.object({
      key: z.enum(["self", "family", "nest", "society", "outside"]),
      nodes: z.array(z.object({
        id: z.string().min(1),
        label: z.string().min(1),
        kind: z.string().min(1),
        weight: WeightSchema,
      }).strict()),
    }).strict()).length(5),
  }).strict(),
  knowledge_beliefs: z.object({
    nodes: z.array(z.object({
      id: z.string().min(1),
      label: z.string().min(1),
      kind: z.enum(["source", "knowledge", "belief"]),
      weight: WeightSchema,
    }).strict()).max(10),
    edges: z.array(z.object({
      source: z.string().min(1),
      target: z.string().min(1),
      relation_key: z.string().min(1),
      display_label: z.string(),
      weight: WeightSchema,
    }).strict()),
  }).strict(),
}).strict()

const ProfileDetailResponseSchema = z.object({
  relationship: ElfieRelationshipSchema,
  permissions: PermissionsSchema,
  profile: ElfieProfileSchema,
  private_cognition: PrivateCognitionSchema.nullable(),
}).strict().transform(({ profile: value, private_cognition, relationship, permissions }) => ({
  ...value,
  permissions,
  private_cognition,
  relationship,
}))

export type ElfieRelationship = z.infer<typeof ElfieRelationshipSchema>
export type ElfieProfile = z.infer<typeof ElfieProfileSchema> & {
  readonly relationship?: ElfieRelationship
}
export type ElfieProfileDetail = z.infer<typeof ProfileDetailResponseSchema>

export async function elfies(): Promise<readonly ElfieProfile[]> {
  return VisibleElfiesResponseSchema.parse(await requestJson("/api/v1/elfies"))
    .items.map((item) => ({ ...item.profile, relationship: item.relationship }))
}

export async function profile(elfieId: string): Promise<ElfieProfileDetail> {
  return ProfileDetailResponseSchema.parse(
    await requestJson(`/api/v1/elfies/${encodeURIComponent(elfieId)}/profile`),
  )
}

export async function saveElfiePortrait(
  elfieId: string,
  image: Blob,
  csrfToken: string,
): Promise<string> {
  const formData = new FormData()
  formData.append("file", image, "portrait.png")
  const result = await requestJson(
    `/api/v1/elfies/${encodeURIComponent(elfieId)}/portrait`,
    {
      body: formData,
      headers: csrfHeaders(csrfToken),
      method: "PUT",
    },
  )
  return ElfiePortraitUploadResponseSchema.parse(result).portrait_url
}

export function elfiePortraitUrl(elfieId: string, kind: "headshot" | "full_body" = "headshot"): string {
  return `/api/v1/elfies/${encodeURIComponent(elfieId)}/portrait?kind=${kind}`
}
