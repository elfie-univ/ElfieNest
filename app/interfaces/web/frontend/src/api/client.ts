import { z } from "zod"

import { requestJson } from "./http"
import { ProfileDetailSchema, ProfileSchema } from "./owner-elfies"

export * from "./http"
export * from "./owner-elfies"
export * from "./admin/food-packages"
export * from "./admin/runtime"
export * from "./elfies/food-policy"
export * from "./owner-nest"
export * from "./owner-providers"
export * from "./owner-users"
export * from "./roles"
export * from "./session"

export async function elfies(): Promise<readonly z.infer<typeof ProfileSchema>[]> {
  return z.array(ProfileSchema).parse(await requestJson("/api/v1/elfies"))
}

export async function profile(elfieId: string): Promise<z.infer<typeof ProfileDetailSchema>> {
  return ProfileDetailSchema.parse(
    await requestJson(`/api/v1/elfies/${encodeURIComponent(elfieId)}/profile`),
  )
}
