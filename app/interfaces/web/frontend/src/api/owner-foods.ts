import { z } from "zod"

import { ownerRead, ownerWrite } from "./http"

export const ExecutionProfileSchema = z.object({
  model: z.string(),
  reasoning_profile: z.string(),
  max_tokens: z.number(),
  temperature: z.number(),
  provider_options: z.record(z.string(), z.unknown()),
})
export const FoodRecipeSchema = z.object({
  key: z.string(),
  display_name: z.string(),
  description: z.string(),
  primary: ExecutionProfileSchema,
  deep: ExecutionProfileSchema.nullable(),
  vision: ExecutionProfileSchema.nullable(),
  verifier: ExecutionProfileSchema.nullable(),
  technical_fallbacks: z.array(ExecutionProfileSchema),
  local_only: z.boolean(),
  validation_status: z.string(),
  source: z.string(),
  locked_fields: z.array(z.string()),
})
export const FoodCatalogSchema = z.object({
  version: z.number(),
  default_food: z.string(),
  fallback_food: z.string(),
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
const CreateResultSchema = z.object({
  food: FoodRecipeSchema,
  warnings: z.array(z.string()),
  catalog: FoodCatalogSchema,
})
const SettingsResultSchema = z.object({
  catalog: FoodCatalogSchema,
  warnings: z.array(z.string()),
})
const FoodVisibilitySchema = z.object({
  food_key: z.string(),
  user_ids: z.array(z.number().int()),
  users: z.array(z.object({
    user_id: z.number().int(),
    display_name: z.string(),
    assigned: z.boolean(),
  })).optional().default([]),
})
const ApplyResultSchema = z.object({ applied: z.boolean(), candidate: FoodCatalogSchema })

export type ExecutionProfile = z.infer<typeof ExecutionProfileSchema>
export type FoodRecipe = z.infer<typeof FoodRecipeSchema>
export type FoodCatalog = z.infer<typeof FoodCatalogSchema>
export type FoodPreview = z.infer<typeof FoodPreviewSchema>
export type FoodVisibility = z.infer<typeof FoodVisibilitySchema>

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

export async function createFood(
  draft: Pick<FoodRecipe, "display_name" | "description" | "primary">,
  csrfToken: string,
): Promise<z.infer<typeof CreateResultSchema>> {
  return CreateResultSchema.parse(await ownerWrite(
    "/api/owner/runtime/foods/",
    "POST",
    csrfToken,
    draft,
  ))
}

export async function updateFoodSettings(
  defaultFood: string,
  fallbackFood: string,
  csrfToken: string,
): Promise<z.infer<typeof SettingsResultSchema>> {
  return SettingsResultSchema.parse(await ownerWrite(
    "/api/owner/runtime/foods/settings",
    "PUT",
    csrfToken,
    { default_food: defaultFood, fallback_food: fallbackFood },
  ))
}

export async function deleteFood(foodKey: string, csrfToken: string): Promise<FoodCatalog> {
  return FoodCatalogSchema.parse(await ownerWrite(
    `/api/owner/runtime/foods/${encodeURIComponent(foodKey)}`,
    "DELETE",
    csrfToken,
  ))
}

export async function foodVisibility(foodKey: string): Promise<FoodVisibility> {
  return FoodVisibilitySchema.parse(await ownerRead(
    `/api/owner/runtime/foods/${encodeURIComponent(foodKey)}/visibility`,
  ))
}

export async function updateFoodVisibility(
  foodKey: string,
  userIds: readonly number[],
  csrfToken: string,
): Promise<void> {
  await ownerWrite(
    `/api/owner/runtime/foods/${encodeURIComponent(foodKey)}/visibility`,
    "PUT",
    csrfToken,
    { user_ids: userIds },
  )
}

export async function rollbackFoods(csrfToken: string): Promise<FoodCatalog> {
  return FoodCatalogSchema.parse(await ownerWrite(
    "/api/owner/runtime/foods/rollback",
    "POST",
    csrfToken,
    { confirm: true },
  ))
}
