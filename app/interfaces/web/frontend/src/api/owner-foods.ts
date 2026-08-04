import { z } from "zod"

import { ownerRead, ownerWrite } from "./http"

const AssignmentSchema = z.object({ model: z.string() })
export const FoodPackageSchema = z.object({
  key: z.string(),
  display_name: z.string(),
  system_role: z.enum(["emergency", "common"]).nullable(),
  enabled: z.boolean(),
  archived: z.boolean(),
  visibility_mode: z.enum(["global", "users"]),
  visible_user_ids: z.array(z.number().int().positive()),
  roles: z.object({
    primary: AssignmentSchema.nullable(),
    reasoning: AssignmentSchema.nullable(),
    vision: AssignmentSchema.nullable(),
    tool: AssignmentSchema.nullable(),
    fallback: AssignmentSchema.nullable(),
  }),
  health: z.string(),
  locality: z.string(),
  latest_evidence_at: z.string().nullable(),
})
export const FoodCatalogSchema = z.object({
  version: z.number(),
  global_default_food_id: z.string(),
  global_emergency_food_id: z.string(),
  packages: z.array(FoodPackageSchema),
  eligible_models: z.array(z.object({
    reference: z.string(),
    display_name: z.string().nullable(),
    local: z.boolean(),
    capabilities: z.array(z.string()),
  })),
})
export const FoodPreviewSchema = z.object({
  food_id: z.string().nullable(),
  candidate: z.object({
    display_name: z.string(),
    enabled: z.boolean(),
    roles: FoodPackageSchema.shape.roles,
  }),
  changes: z.array(z.object({
    role: z.string(),
    old_model: z.string().nullable(),
    new_model: z.string().nullable(),
  })),
  warnings: z.array(z.string()),
  has_changes: z.boolean(),
})
const EditResultSchema = z.object({
  food: FoodPackageSchema,
  warnings: z.array(z.string()),
})
const CreateResultSchema = z.object({
  food: FoodPackageSchema,
  catalog: FoodCatalogSchema,
})
export type FoodPackage = z.infer<typeof FoodPackageSchema>
export type FoodCatalog = z.infer<typeof FoodCatalogSchema>
export type FoodPreview = z.infer<typeof FoodPreviewSchema>
export type FoodPackageDraft = Pick<FoodPackage, "display_name" | "enabled" | "roles" | "visibility_mode"> & {
  readonly visible_user_ids: readonly number[]
}

export async function ownerFoods(): Promise<FoodCatalog> {
  return FoodCatalogSchema.parse(await ownerRead("/api/owner/runtime/foods/"))
}

export async function previewFoodUpdate(
  foodId: string,
  connectionIds: readonly string[],
  localFirst: boolean,
  allowRemote: boolean,
  visibilityMode: FoodPackage["visibility_mode"],
  visibleUserIds: readonly number[],
  csrfToken: string,
): Promise<FoodPreview> {
  return FoodPreviewSchema.parse(await ownerWrite(
    `/api/owner/runtime/foods/${encodeURIComponent(foodId)}/generation-preview`,
    "POST",
    csrfToken,
    {
      connection_ids: connectionIds,
      local_first: localFirst,
      allow_remote: allowRemote,
      visibility_mode: visibilityMode,
      visible_user_ids: visibleUserIds,
    },
  ))
}

export async function previewNewFood(
  displayName: string,
  connectionIds: readonly string[],
  localFirst: boolean,
  allowRemote: boolean,
  visibilityMode: FoodPackage["visibility_mode"],
  visibleUserIds: readonly number[],
  csrfToken: string,
): Promise<FoodPreview> {
  return FoodPreviewSchema.parse(await ownerWrite(
    "/api/owner/runtime/foods/generation-preview",
    "POST",
    csrfToken,
    {
      display_name: displayName,
      connection_ids: connectionIds,
      local_first: localFirst,
      allow_remote: allowRemote,
      visibility_mode: visibilityMode,
      visible_user_ids: visibleUserIds,
    },
  ))
}

export async function editFood(
  foodId: string,
  recipe: FoodPackageDraft,
  csrfToken: string,
): Promise<{ readonly food: FoodPackage; readonly warnings: readonly string[] }> {
  return EditResultSchema.parse(await ownerWrite(
    `/api/owner/runtime/foods/${encodeURIComponent(foodId)}`,
    "PUT",
    csrfToken,
    recipe,
  ))
}

export async function createFood(
  draft: FoodPackageDraft,
  csrfToken: string,
): Promise<z.infer<typeof CreateResultSchema>> {
  return CreateResultSchema.parse(await ownerWrite(
    "/api/owner/runtime/foods/",
    "POST",
    csrfToken,
    draft,
  ))
}

export async function changeFoodLifecycle(
  foodId: string,
  action: "enable" | "disable" | "archive" | "restore",
  csrfToken: string,
): Promise<FoodPackage> {
  return FoodPackageSchema.parse(await ownerWrite(
    `/api/owner/runtime/foods/${encodeURIComponent(foodId)}/${action}`,
    "POST",
    csrfToken,
  ))
}

export async function deleteFood(foodId: string, csrfToken: string): Promise<FoodCatalog> {
  return FoodCatalogSchema.parse(await ownerWrite(
    `/api/owner/runtime/foods/${encodeURIComponent(foodId)}`,
    "DELETE",
    csrfToken,
  ))
}
