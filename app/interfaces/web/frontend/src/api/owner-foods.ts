import { z } from "zod"

import { ownerRead, ownerWrite } from "./http"

export const ExecutionProfileSchema = z.object({
  model: z.string(),
  reasoning_profile: z.string(),
  max_tokens: z.number(),
  temperature: z.number(),
  tools: z.array(z.string()),
  provider_options: z.record(z.string(), z.unknown()),
})
export const FoodRecipeSchema = z.object({
  key: z.string(),
  display_name: z.string(),
  description: z.string(),
  primary: ExecutionProfileSchema,
  deep: ExecutionProfileSchema.nullable(),
  verifier: ExecutionProfileSchema.nullable(),
  technical_fallbacks: z.array(ExecutionProfileSchema),
  validation_status: z.string(),
  source: z.string(),
  locked_fields: z.array(z.string()),
})
export const FoodCatalogSchema = z.object({
  version: z.number(),
  source_fingerprint: z.string(),
  generated_at: z.string(),
  generation_sources: z.array(z.string()),
  generation_note: z.string(),
  foods: z.record(z.string(), FoodRecipeSchema),
})
export const FoodPreviewSchema = z.object({
  base_catalog_fingerprint: z.string(),
  has_changes: z.boolean(),
  generation_sources: z.array(z.string()),
  advisor_error: z.string().nullable().optional(),
  warnings: z.array(z.string()),
  changes: z.array(z.object({
    food_key: z.string(),
    change_type: z.string(),
    old_model: z.string().nullable(),
    new_model: z.string().nullable(),
    warnings: z.array(z.string()),
  })),
  current: FoodCatalogSchema,
  candidate: FoodCatalogSchema,
})

const EditResultSchema = z.object({ food: FoodRecipeSchema, warnings: z.array(z.string()) })
const ApplyResultSchema = z.object({ applied: z.boolean(), candidate: FoodCatalogSchema })

export type ExecutionProfile = z.infer<typeof ExecutionProfileSchema>
export type FoodRecipe = z.infer<typeof FoodRecipeSchema>
export type FoodCatalog = z.infer<typeof FoodCatalogSchema>
export type FoodPreview = z.infer<typeof FoodPreviewSchema>

export async function ownerFoods(): Promise<FoodCatalog> {
  return FoodCatalogSchema.parse(await ownerRead("/api/owner/runtime/foods/"))
}

export async function previewFoodUpdate(csrfToken: string): Promise<FoodPreview> {
  return FoodPreviewSchema.parse(await ownerWrite(
    "/api/owner/runtime/foods/update-preview",
    "POST",
    csrfToken,
    { use_llm: false },
  ))
}

export async function applyFoodUpdate(preview: FoodPreview, csrfToken: string): Promise<FoodCatalog> {
  const result = ApplyResultSchema.parse(await ownerWrite(
    "/api/owner/runtime/foods/update-apply",
    "POST",
    csrfToken,
    {
      confirm: true,
      candidate: preview.candidate,
      base_catalog_fingerprint: preview.base_catalog_fingerprint,
    },
  ))
  return result.candidate
}

export async function editFood(
  foodKey: string,
  recipe: FoodRecipe,
  csrfToken: string,
): Promise<{ readonly food: FoodRecipe; readonly warnings: readonly string[] }> {
  return EditResultSchema.parse(await ownerWrite(
    `/api/owner/runtime/foods/${encodeURIComponent(foodKey)}`,
    "PUT",
    csrfToken,
    recipe,
  ))
}

export async function rollbackFoods(csrfToken: string): Promise<FoodCatalog> {
  return FoodCatalogSchema.parse(await ownerWrite(
    "/api/owner/runtime/foods/rollback",
    "POST",
    csrfToken,
    { confirm: true },
  ))
}
