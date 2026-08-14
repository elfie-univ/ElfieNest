import { z } from "zod"

import { ElfieIdValueSchema } from "@/shared/elfie-id"

import { csrfHeaders, requestJson } from "../http"

const AdoptionInfoSchema = z.object({
  personality_styles: z.array(z.string()),
  species_ids: z.array(z.union([z.literal("dog"), z.literal("fox"), z.literal("cat")])),
  heights: z.array(z.string()),
  builds: z.array(z.string()),
  life_stages: z.array(z.string()),
  quota: z.object({
    used: z.number().int(),
    max: z.number().int(),
    remaining: z.number().int(),
    can_adopt: z.boolean(),
  }),
})

const AdoptionCandidateSchema = z.object({
  candidate_id: z.string(),
  original_name: z.string(),
  suggested_name: z.string(),
  species_id: z.union([z.literal("dog"), z.literal("fox"), z.literal("cat")]),
  life_stage: z.union([
    z.literal("youth"),
    z.literal("young_adult"),
    z.literal("mature"),
    z.literal("elder"),
  ]),
  gender: z.union([z.literal("male"), z.literal("female")]),
  image_url: z.string(),
  appearance_tags: z.array(z.string()),
  personality_tags: z.array(z.string()),
  introduction: z.string(),
  compatibility: z.string(),
})

const AdoptionCandidateSetSchema = z.object({
  candidate_set_id: z.string(),
  candidates: z.array(AdoptionCandidateSchema).length(5),
})

const AdoptionReplySchema = AdoptionCandidateSchema.extend({
  status: z.union([z.literal("accepted"), z.literal("unsure")]),
  message: z.string(),
})

const AdoptionRepliesSchema = z.object({
  candidate_set_id: z.string(),
  replies: z.array(AdoptionReplySchema).min(1).max(3),
})

const AdoptionResultSchema = z.object({
  elfie_id: ElfieIdValueSchema,
  name: z.string(),
  species_id: z.union([z.literal("dog"), z.literal("fox"), z.literal("cat")]),
})

export type AdoptionInfo = z.infer<typeof AdoptionInfoSchema>
export type AdoptionCandidate = z.infer<typeof AdoptionCandidateSchema>
export type AdoptionCandidateSet = z.infer<typeof AdoptionCandidateSetSchema>
export type AdoptionReply = z.infer<typeof AdoptionReplySchema>
export type AdoptionReplies = z.infer<typeof AdoptionRepliesSchema>

export type AdoptionCandidateSetInput = {
  readonly species_id: "dog" | "fox" | "cat"
  readonly life_stage: "youth" | "young_adult" | "mature" | "elder" | "any"
  readonly gender: "male" | "female" | "any"
  readonly appearance: {
    readonly stature: "small" | "standard" | "tall" | "any"
    readonly build: "slim" | "standard" | "round" | "any"
    readonly face: "soft" | "balanced" | "defined" | "any"
    readonly signature: "warm" | "marked" | "ears" | "any"
    readonly priority: "stature" | "build" | "face" | "signature"
  }
  readonly answers: readonly string[]
}

export async function adoptionInfo(): Promise<AdoptionInfo> {
  return AdoptionInfoSchema.parse(await requestJson("/api/v1/me/adoption"))
}

export async function adoptionCandidates(
  input: AdoptionCandidateSetInput,
  csrfToken: string,
): Promise<AdoptionCandidateSet> {
  return AdoptionCandidateSetSchema.parse(await requestJson("/api/v1/me/adoption/candidate-sets", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify(input),
  }))
}

export async function adoptionReplies(
  candidateSetId: string,
  candidateIds: readonly string[],
  csrfToken: string,
): Promise<AdoptionReplies> {
  return AdoptionRepliesSchema.parse(await requestJson(
    `/api/v1/me/adoption/candidate-sets/${encodeURIComponent(candidateSetId)}/replies`,
    {
      method: "POST",
      headers: csrfHeaders(csrfToken, true),
      body: JSON.stringify({ candidate_ids: candidateIds }),
    },
  ))
}

export async function commitAdoption(
  candidateSetId: string,
  candidateId: string,
  name: string,
  csrfToken: string,
): Promise<z.infer<typeof AdoptionResultSchema>> {
  return AdoptionResultSchema.parse(await requestJson("/api/v1/me/adoption", {
    method: "POST",
    headers: csrfHeaders(csrfToken, true),
    body: JSON.stringify({
      candidate_set_id: candidateSetId,
      candidate_id: candidateId,
      name,
    }),
  }))
}
