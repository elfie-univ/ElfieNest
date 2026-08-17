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
  availability_status: z.enum(["available", "degraded", "unavailable", "unknown"]).optional(),
  available: z.boolean().optional(),
})

const OllamaStatusSchema = z.object({
  state: OllamaStateSchema,
  endpoint: z.string().nullable(),
  version: z.string().nullable(),
  memory_gb: z.number().int().min(0),
  recommended_model: z.string().nullable(),
  installed_model_count: z.number().int().min(0),
  model_counts: z.object({
    installed: z.number().int().min(0),
    available: z.number().int().min(0),
    degraded: z.number().int().min(0),
    pending: z.number().int().min(0),
    unavailable: z.number().int().min(0),
  }).strict(),
  models: z.array(OllamaModelSchema),
  task: OllamaTaskSchema,
})

export type OllamaStatus = z.infer<typeof OllamaStatusSchema>

export type SupportedOllamaModelCounts = {
  readonly installed: number
  readonly available: number
  readonly degraded: number
  readonly pending: number
  readonly unavailable: number
}

export function supportedOllamaModelCounts(
  status: { readonly models: readonly {
    readonly id: string
    readonly display_name?: string | undefined
    readonly installed: boolean
    readonly recommended?: boolean | undefined
    readonly available?: boolean | undefined
    readonly availability_status?: "available" | "degraded" | "unavailable" | "unknown" | undefined
  }[] },
  supportedModelIds: readonly string[],
): SupportedOllamaModelCounts {
  const supported = new Set(supportedModelIds)
  const installed = status.models.filter((model) => model.installed && supported.has(model.id))
  return {
    installed: installed.length,
    available: installed.filter((model) => model.available === true).length,
    degraded: installed.filter((model) => model.availability_status === "degraded").length,
    pending: installed.filter((model) => model.availability_status === "unknown").length,
    unavailable: installed.filter((model) => model.availability_status === "unavailable").length,
  }
}

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

export async function verifyOllamaModels(csrfToken: string): Promise<OllamaStatus> {
  return OllamaStatusSchema.parse(await ownerWrite(
    "/api/v1/admin/model-providers/ollama/verify",
    "POST",
    csrfToken,
    undefined,
    { timeout: false },
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
