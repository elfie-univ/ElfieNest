import { z } from "zod"

import { requestJson } from "../http"

export const MobileAccessSchema = z.object({
  available: z.boolean(),
  urls: z.array(z.string().url()),
}).strict()

export type MobileAccess = z.infer<typeof MobileAccessSchema>

export async function mobileAccess(): Promise<MobileAccess> {
  return MobileAccessSchema.parse(
    await requestJson("/api/v1/admin/runtime/mobile-access"),
  )
}
