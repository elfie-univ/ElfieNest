import { z } from "zod"

import { ownerRead, ownerWrite } from "./http"

const VerificationSchema = z.object({
  status: z.enum(["never", "passed", "failed"]),
  checked_at: z.string().nullable(),
  latency_ms: z.number().nullable(),
  error: z.string().nullable(),
})

const ProviderModelSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  source: z.enum(["discovered", "configured", "manual"]),
})

const ProviderViewSchema = z.object({
  provider_id: z.string(),
  name: z.string(),
  display_name: z.string(),
  api_base: z.string(),
  api_mode: z.string(),
  auth_type: z.string(),
  test_model: z.string(),
  configured: z.boolean(),
  configuration_status: z.enum(["configured", "unconfigured"]),
  verification: VerificationSchema,
  has_api_key: z.boolean(),
  models: z.array(ProviderModelSchema),
  model_refresh: z.record(z.unknown()),
  capabilities: z.object({
    connection_method: z.enum(["local", "api_key", "oauth"]),
    oauth_available: z.boolean(),
    oauth_unavailable: z.boolean(),
    model_discovery: z.boolean(),
  }),
})

const MatrixCellSchema = z.object({
  provider_id: z.string(),
  available: z.boolean(),
  verification_status: z.enum(["never", "passed", "failed"]),
  benchmark_status: z.enum(["passed", "failed"]).nullable(),
  latency_ms: z.number().nullable(),
  latency_class: z.enum(["fast", "normal", "slow"]).nullable(),
  price_estimate: z.number().nullable(),
})

const ModelMatrixSchema = z.object({
  providers: z.array(z.object({
    provider_id: z.string(),
    name: z.string(),
    verification: VerificationSchema,
  })),
  models: z.array(z.object({
    model_id: z.string(),
    display_name: z.string(),
    capabilities: z.array(z.string()),
    providers: z.array(MatrixCellSchema),
  })),
})

const BatchResultSchema = z.object({
  results: z.array(z.object({
    provider_id: z.string(),
    configured: z.boolean(),
    status: z.enum(["passed", "failed", "skipped"]),
    verification: VerificationSchema.nullable(),
  })),
})

const BenchmarkResultSchema = z.object({
  results: z.array(z.object({
    provider_id: z.string(),
    model_id: z.string(),
    status: z.enum(["passed", "failed"]),
    checked_at: z.string(),
    latency_ms: z.number().nullable(),
    latency_class: z.enum(["fast", "normal", "slow"]).nullable(),
    error: z.string().nullable(),
  })),
})

export type ProviderVerification = z.infer<typeof VerificationSchema>
export type ProviderView = z.infer<typeof ProviderViewSchema>
export type ModelMatrix = z.infer<typeof ModelMatrixSchema>
export type ProviderModelDraft = { readonly id: string; readonly display_name: string }
export type ProviderDraft = {
  readonly provider_id?: string
  readonly display_name?: string
  readonly api_base?: string
  readonly api_key?: string
  readonly api_mode?: string
  readonly auth_type?: string
  readonly test_model?: string
  readonly models?: readonly ProviderModelDraft[]
  readonly refresh_models?: boolean
}
export type BenchmarkCombination = { readonly provider_id: string; readonly model_id: string }

export async function ownerProviders(): Promise<readonly ProviderView[]> {
  return z.array(ProviderViewSchema).parse(await ownerRead("/api/owner/providers/"))
}

export async function createProvider(
  draft: ProviderDraft,
  csrfToken: string,
): Promise<ProviderView> {
  return ProviderViewSchema.parse(await ownerWrite("/api/owner/providers/", "POST", csrfToken, draft))
}

export async function updateProvider(
  providerId: string,
  draft: ProviderDraft,
  csrfToken: string,
): Promise<ProviderView> {
  return ProviderViewSchema.parse(await ownerWrite(`/api/owner/providers/${encodeURIComponent(providerId)}`, "PUT", csrfToken, draft))
}

export async function deleteProvider(providerId: string, csrfToken: string): Promise<void> {
  await ownerWrite(`/api/owner/providers/${encodeURIComponent(providerId)}`, "DELETE", csrfToken)
}

export async function verifyProvider(providerId: string, csrfToken: string): Promise<void> {
  await ownerWrite(`/api/owner/providers/${encodeURIComponent(providerId)}/verify`, "POST", csrfToken)
}

export async function verifyProvidersBatch(
  csrfToken: string,
): Promise<z.infer<typeof BatchResultSchema>> {
  return BatchResultSchema.parse(await ownerWrite("/api/owner/providers/verify-batch", "POST", csrfToken, {}))
}

export async function ownerModelMatrix(): Promise<ModelMatrix> {
  return ModelMatrixSchema.parse(await ownerRead("/api/owner/providers/model-matrix"))
}

export async function benchmarkProviderModels(
  combinations: readonly BenchmarkCombination[],
  csrfToken: string,
): Promise<z.infer<typeof BenchmarkResultSchema>> {
  return BenchmarkResultSchema.parse(await ownerWrite(
    "/api/owner/providers/models/benchmark",
    "POST",
    csrfToken,
    { combinations },
  ))
}
