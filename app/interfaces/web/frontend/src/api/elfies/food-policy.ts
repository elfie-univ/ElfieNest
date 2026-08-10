import { z } from "zod"

import { ownerWrite, requestJson } from "../http"

export const ElfieFoodPolicySchema = z.object({
  main_food_id: z.string(),
  effective_main_food_id: z.string(),
  main_food_options: z.array(z.object({
    food_id: z.string(),
    display_name: z.string(),
  }).strict()),
  main_food_unavailable: z.boolean(),
}).strict()

export type ElfieFoodPolicy = z.infer<typeof ElfieFoodPolicySchema>

function foodPolicyPath(elfieId: string): string {
  return `/api/v1/elfies/${encodeURIComponent(elfieId)}/food-policy`
}

export async function elfieFoodPolicy(elfieId: string): Promise<ElfieFoodPolicy> {
  return ElfieFoodPolicySchema.parse(await requestJson(foodPolicyPath(elfieId)))
}

export async function updateElfieFoodPolicy(
  elfieId: string,
  mainFoodId: string,
  csrfToken: string,
): Promise<ElfieFoodPolicy> {
  return ElfieFoodPolicySchema.parse(await ownerWrite(
    foodPolicyPath(elfieId),
    "PUT",
    csrfToken,
    { main_food_id: mainFoodId },
  ))
}
