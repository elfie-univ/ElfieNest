import { z } from "zod"

import { requestJson } from "../http"

export const EmbodimentSessionSchema = z.object({
  elfie_id: z.string().min(1),
  state: z.enum(["at_nest", "switching_to_hosted", "hosted", "returning_to_nest", "offline"]),
  body_id: z.string().nullable(),
}).strict()

const EmbodimentSessionsResponseSchema = z.object({
  items: z.array(EmbodimentSessionSchema),
}).strict()

export type EmbodimentSession = z.infer<typeof EmbodimentSessionSchema>

export async function embodimentSessions(): Promise<readonly EmbodimentSession[]> {
  return EmbodimentSessionsResponseSchema.parse(
    await requestJson("/api/v1/admin/runtime/embodiment-sessions"),
  ).items
}
