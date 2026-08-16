import { z } from "zod"

import { ownerRead, ownerWrite } from "../http"

const AssignmentSchema = z.object({ model: z.string() }).strict()
const RequiredRoleSchema = z.enum(["reasoning", "vision", "tool"])
const FoodRolesSchema = z.object({
  primary: AssignmentSchema.nullable(),
  reasoning: AssignmentSchema.nullable(),
  vision: AssignmentSchema.nullable(),
  tool: AssignmentSchema.nullable(),
  fallback: AssignmentSchema.nullable(),
}).strict()

export const FoodPackageSchema = z.object({
  key: z.string(),
  display_name: z.string(),
  system_role: z.enum(["emergency", "common"]).nullable(),
  enabled: z.boolean(),
  archived: z.boolean(),
  visibility_mode: z.enum(["global", "users"]),
  visible_user_ids: z.array(z.number().int().positive()),
  roles: FoodRolesSchema,
  health: z.string(),
  locality: z.string(),
  latest_evidence_at: z.string().nullable(),
  required_roles: z.array(RequiredRoleSchema).optional(),
}).strict()

export const FoodCatalogSchema = z.object({
  version: z.number().int(),
  global_default_food_id: z.string(),
  global_emergency_food_id: z.string(),
  packages: z.array(FoodPackageSchema),
  eligible_models: z.array(z.object({
    reference: z.string(),
    display_name: z.string(),
    local: z.boolean(),
    capabilities: z.array(z.string()),
  }).strict()),
}).strict()

export const FoodPreviewSchema = z.object({
  food_id: z.string().nullable(),
  candidate: z.object({
    display_name: z.string(),
    enabled: z.boolean(),
    roles: FoodRolesSchema,
  }).strict(),
  changes: z.array(z.object({
    role: z.string(),
    old_model: z.string().nullable(),
    new_model: z.string().nullable(),
  }).strict()),
  warnings: z.array(z.string()),
  has_changes: z.boolean(),
}).strict()

const EditResultSchema = z.object({
  food: FoodPackageSchema,
  warnings: z.array(z.string()),
}).strict()

const CreateResultSchema = z.object({
  food: FoodPackageSchema,
  catalog: FoodCatalogSchema,
}).strict()

export type FoodPackage = z.infer<typeof FoodPackageSchema>
export type FoodCatalog = z.infer<typeof FoodCatalogSchema>
export type FoodPreview = z.infer<typeof FoodPreviewSchema>
export type FoodPackageDraft = Pick<FoodPackage, "display_name" | "enabled" | "roles" | "visibility_mode"> & {
  readonly visible_user_ids: readonly number[]
  readonly required_roles?: readonly z.infer<typeof RequiredRoleSchema>[]
}

const COLLECTION_PATH = "/api/v1/admin/food-packages"

export async function ownerFoods(): Promise<FoodCatalog> {
  return FoodCatalogSchema.parse(await ownerRead(COLLECTION_PATH))
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
    `${COLLECTION_PATH}/${encodeURIComponent(foodId)}/generation-preview`,
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
    `${COLLECTION_PATH}/generation-preview`,
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
    `${COLLECTION_PATH}/${encodeURIComponent(foodId)}`,
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
    COLLECTION_PATH,
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
    `${COLLECTION_PATH}/${encodeURIComponent(foodId)}/${action}`,
    "POST",
    csrfToken,
  ))
}

export async function deleteFood(foodId: string, csrfToken: string): Promise<FoodCatalog> {
  return FoodCatalogSchema.parse(await ownerWrite(
    `${COLLECTION_PATH}/${encodeURIComponent(foodId)}`,
    "DELETE",
    csrfToken,
  ))
}
