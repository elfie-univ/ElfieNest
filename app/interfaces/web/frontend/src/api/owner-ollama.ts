import { z } from "zod"

import { ownerRead, ownerWrite } from "./http"

const OllamaStateSchema = z.enum([
  "absent",
  "healthy",
  "stopped",
  "deleted",
  "installing",
  "failed",
  "cancelled",
  "repair_required",
])

const OllamaTaskSchema = z.object({
  key: z.enum(["install", "model_pull"]),
  state: z.enum(["running", "completed", "failed"]),
  progress: z.number().int().min(0).max(100),
  error: z.string().nullable(),
}).nullable()

const OllamaModelSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  installed: z.boolean(),
  recommended: z.boolean(),
})

const OllamaStatusSchema = z.object({
  state: OllamaStateSchema,
  endpoint: z.string().nullable(),
  version: z.string().nullable(),
  memory_gb: z.number().int().min(0),
  recommended_model: z.string().nullable(),
  installed_model_count: z.number().int().min(0),
  models: z.array(OllamaModelSchema),
  task: OllamaTaskSchema,
})

export type OllamaStatus = z.infer<typeof OllamaStatusSchema>

export async function ownerOllamaStatus(): Promise<OllamaStatus> {
  return OllamaStatusSchema.parse(await ownerRead("/api/v1/admin/model-providers/ollama"))
}

export async function installOllama(csrfToken: string): Promise<OllamaStatus> {
  return OllamaStatusSchema.parse(await ownerWrite(
    "/api/v1/admin/model-providers/ollama/install",
    "POST",
    csrfToken,
    { confirmed: true },
  ))
}

export async function startOllama(csrfToken: string): Promise<OllamaStatus> {
  return OllamaStatusSchema.parse(await ownerWrite(
    "/api/v1/admin/model-providers/ollama/start",
    "POST",
    csrfToken,
  ))
}

export async function pullOllamaModels(
  modelIds: readonly string[],
  csrfToken: string,
): Promise<OllamaStatus> {
  return OllamaStatusSchema.parse(await ownerWrite(
    "/api/v1/admin/model-providers/ollama/models/pull",
    "POST",
    csrfToken,
    { model_ids: modelIds, confirmed: true },
  ))
}
