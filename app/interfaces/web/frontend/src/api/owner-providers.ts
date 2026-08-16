import { z } from "zod"

import { ownerRead, ownerWrite } from "./http"

const ValidationModeSchema = z.enum(["none", "full", "cached", "heartbeat", "benchmark"])

const VerificationSchema = z.object({
  status: z.enum(["never", "passed", "failed"]),
  checked_at: z.string().nullable(),
  latency_ms: z.number().nullable(),
  error: z.string().nullable(),
  validation_mode: ValidationModeSchema.optional(),
  cache_hit: z.boolean().optional(),
  needs_full_validation: z.boolean().optional(),
  needs_heartbeat: z.boolean().optional(),
  full_run_id: z.string().nullable().optional(),
  full_checked_at: z.string().nullable().optional(),
  heartbeat_checked_at: z.string().nullable().optional(),
  heartbeat_status: z.enum(["passed", "failed"]).nullable().optional(),
  representative_model_id: z.string().nullable().optional(),
  reason: z.string().nullable().optional(),
  availability_status: z.enum(["available", "degraded", "unavailable", "unknown"]).optional(),
  reason_code: z.string().nullable().optional(),
  evidence_source: z.string().nullable().optional(),
  expires_at: z.string().nullable().optional(),
  is_core: z.boolean().optional(),
})

const ProviderModelSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  canonical_model_id: z.string().nullable(),
  source: z.enum(["official", "remote_catalog", "bundled_catalog", "manual"]),
  context_window_tokens: z.number().nullable(),
  max_output_tokens: z.number().nullable(),
  supports_tools: z.boolean().nullable(),
  supports_vision: z.boolean().nullable(),
  supports_reasoning: z.boolean().nullable(),
  supports_structured_output: z.boolean().nullable().optional(),
  hidden: z.boolean(),
  retired: z.boolean(),
  available: z.boolean(),
  discovery_state: z.enum(["present", "source_missing"]).optional(),
  consecutive_missing: z.number().int().min(0).optional(),
  last_seen_at: z.string().nullable().optional(),
  request_profile_id: z.string().optional(),
  request_profile_version: z.number().int().positive().optional(),
  capability_evidence: z.record(
    z.enum(["tools", "vision", "reasoning", "structured_output"]),
    z.enum(["declared", "declared_by_user", "accepted", "verified", "unknown"]),
  ).optional(),
  verification: VerificationSchema,
})

const CapabilityProbeResultSchema = z.object({
  capability: z.enum(["tools", "vision", "reasoning", "structured_output"]),
  state: z.enum(["supported", "unsupported", "unknown"]),
  evidence: z.enum(["declared", "declared_by_user", "accepted", "verified", "unknown"]),
  status: z.enum(["passed", "failed"]),
  latency_ms: z.number(),
  error: z.string().nullable(),
  error_code: z.string().nullable(),
  error_scope: z.string().nullable(),
  error_category: z.string().nullable(),
})

const ProviderCapabilityProbeSchema = z.object({
  reference: z.string(),
  results: z.array(CapabilityProbeResultSchema),
})

const ProviderObsoleteModelSchema = z.object({
  model: ProviderModelSchema,
  eligible: z.boolean(),
  reason: z.string(),
  last_production_at: z.string().nullable(),
})

const ProviderObsoleteModelsSchema = z.object({
  items: z.array(ProviderObsoleteModelSchema),
})

const ProviderProductSchema = z.object({
  catalog_id: z.string(),
  name: z.string(),
  brand: z.object({
    brand_id: z.string(),
    name: z.string(),
    logo_asset: z.string(),
  }),
  connection_method: z.enum(["local", "api_key", "oauth"]),
  oauth_available: z.boolean(),
  usage_scope: z.string(),
  discovery_strategy: z.string(),
  api_mode: z.string(),
})

const ModelRefreshSchema = z.object({
  status: z.string(),
  checked_at: z.string(),
  message: z.string().nullable(),
  models: z.array(ProviderModelSchema),
}).nullable()

const ProviderConnectionSchema = z.object({
  connection_id: z.string(),
  catalog_id: z.string(),
  alias: z.string(),
  api_base: z.string(),
  api_mode: z.string(),
  auth_type: z.string(),
  has_api_key: z.boolean(),
  has_credential: z.boolean().optional(),
  enabled: z.boolean(),
  archived: z.boolean(),
  usage_scope: z.string(),
  verification: VerificationSchema,
  models: z.array(ProviderModelSchema),
  model_refresh: ModelRefreshSchema,
})

const MatrixCellSchema = z.object({
  connection_id: z.string(),
  model_id: z.string().nullable(),
  available: z.boolean(),
  verification_status: z.enum(["never", "passed", "failed"]),
  benchmark_status: z.enum(["passed", "failed"]).nullable(),
  latency_ms: z.number().nullable(),
  latency_class: z.enum(["fast", "normal", "slow"]).nullable(),
  price_estimate: z.number().nullable(),
})

const ModelMatrixSchema = z.object({
  snapshot: z.object({
    mode: z.string(),
    run_id: z.string().nullable().optional(),
    as_of: z.string().nullable().optional(),
    status: z.string().nullable().optional(),
    started_at: z.string().nullable().optional(),
    finished_at: z.string().nullable().optional(),
  }),
  connections: z.array(z.object({
    connection_id: z.string(),
    name: z.string(),
    verification: VerificationSchema,
  })),
  models: z.array(z.object({
    model_key: z.string(),
    display_name: z.string(),
    capabilities: z.array(z.string()),
    connections: z.array(MatrixCellSchema),
  })),
})

const BenchmarkResultSchema = z.object({
  run_id: z.string(),
  status: z.string(),
  results: z.array(z.object({
    connection_id: z.string(),
    model_id: z.string(),
    status: z.enum(["passed", "failed"]),
    checked_at: z.string(),
    latency_ms: z.number().nullable(),
    latency_class: z.enum(["fast", "normal", "slow"]).nullable(),
    error: z.string().nullable(),
  })),
})

const ValidateAllResultSchema = z.object({
  run_id: z.string(),
  status: z.string(),
  results: z.array(z.object({
    subject: z.string(),
    status: z.string(),
    checked_at: z.string().nullable().optional(),
  })),
})

const VerifyConnectionResultSchema = z.object({
  connection_id: z.string(),
  verification: VerificationSchema,
})

const ProviderOAuthLoginStartSchema = z.object({
  catalog_id: z.string(),
  login_id: z.string(),
  authorization_url: z.string().url(),
  user_code: z.string(),
  poll_interval_seconds: z.number().int().positive(),
  expires_at: z.string(),
})

const ProviderOAuthLoginStatusSchema = z.object({
  catalog_id: z.string(),
  login_id: z.string(),
  state: z.enum(["pending", "completed"]),
  account_id: z.string().nullable(),
  expires_at: z.string().nullable(),
  connection: ProviderConnectionSchema.nullable(),
})

export type ProviderProduct = z.infer<typeof ProviderProductSchema>
export type ProviderConnection = z.infer<typeof ProviderConnectionSchema>
export type ProviderOAuthLoginStart = z.infer<typeof ProviderOAuthLoginStartSchema>
export type ProviderOAuthLoginStatus = z.infer<typeof ProviderOAuthLoginStatusSchema>
export type ProviderModel = z.infer<typeof ProviderModelSchema>
export type ProviderCapabilityProbe = z.infer<typeof CapabilityProbeResultSchema>
export type ProviderObsoleteModel = z.infer<typeof ProviderObsoleteModelSchema>
export type ModelMatrix = z.infer<typeof ModelMatrixSchema>
export type ProviderModelDraft = {
  readonly id: string
  readonly original_id?: string
  readonly display_name?: string
  readonly canonical_model_id?: string | null
  readonly context_window_tokens?: number | null
  readonly max_output_tokens?: number | null
  readonly supports_tools?: boolean | null
  readonly supports_vision?: boolean | null
  readonly supports_reasoning?: boolean | null
  readonly supports_structured_output?: boolean | null
  readonly request_profile_id?: string
  readonly request_profile_version?: number
  readonly hidden?: boolean
}
export type ProviderConnectionDraft = {
  readonly catalog_id: string
  readonly alias?: string
  readonly api_base?: string
  readonly api_key?: string
  readonly api_mode?: string
  readonly auth_type?: string
  readonly models?: readonly ProviderModelDraft[]
  readonly refresh_models?: boolean
  readonly verify?: boolean
}
export type ProviderConnectionUpdate = Omit<ProviderConnectionDraft, "catalog_id">
export type BenchmarkCombination = {
  readonly connection_id: string
  readonly model_id: string
}

export async function ownerProviderCatalog(): Promise<readonly ProviderProduct[]> {
  return z.object({ items: z.array(ProviderProductSchema) }).parse(
    await ownerRead("/api/v1/admin/model-providers/catalog"),
  ).items
}

export async function ownerProviderConnections(): Promise<readonly ProviderConnection[]> {
  return z.object({ items: z.array(ProviderConnectionSchema) }).parse(
    await ownerRead("/api/v1/admin/model-providers/connections"),
  ).items
}

export async function startProviderOAuthLogin(
  catalogId: string,
  csrfToken: string,
): Promise<ProviderOAuthLoginStart> {
  return ProviderOAuthLoginStartSchema.parse(await ownerWrite(
    "/api/v1/admin/model-providers/oauth-logins",
    "POST",
    csrfToken,
    { catalog_id: catalogId },
  ))
}

export async function completeProviderOAuthLogin(
  loginId: string,
  catalogId: string,
  alias: string | undefined,
  csrfToken: string,
): Promise<ProviderOAuthLoginStatus> {
  return ProviderOAuthLoginStatusSchema.parse(await ownerWrite(
    `/api/v1/admin/model-providers/oauth-logins/${encodeURIComponent(loginId)}/complete`,
    "POST",
    csrfToken,
    { catalog_id: catalogId, ...(alias ? { alias } : {}) },
  ))
}

export async function createProviderConnection(
  draft: ProviderConnectionDraft,
  csrfToken: string,
): Promise<ProviderConnection> {
  return ProviderConnectionSchema.parse(await ownerWrite(
    "/api/v1/admin/model-providers/connections",
    "POST",
    csrfToken,
    draft,
  ))
}

export async function updateProviderConnection(
  connectionId: string,
  draft: ProviderConnectionUpdate,
  csrfToken: string,
): Promise<ProviderConnection> {
  return ProviderConnectionSchema.parse(await ownerWrite(
    `/api/v1/admin/model-providers/connections/${encodeURIComponent(connectionId)}`,
    "PATCH",
    csrfToken,
    draft,
  ))
}

export async function deleteProviderConnection(
  connectionId: string,
  csrfToken: string,
): Promise<void> {
  await ownerWrite(
    `/api/v1/admin/model-providers/connections/${encodeURIComponent(connectionId)}`,
    "DELETE",
    csrfToken,
  )
}

export async function verifyProviderConnection(
  connectionId: string,
  csrfToken: string,
  forceFull = false,
): Promise<z.infer<typeof VerifyConnectionResultSchema>> {
  const query = forceFull ? "?force_full=true" : ""
  return VerifyConnectionResultSchema.parse(await ownerWrite(
    `/api/v1/admin/model-providers/connections/${encodeURIComponent(connectionId)}/verify${query}`,
    "POST",
    csrfToken,
    undefined,
    { timeout: false },
  ))
}

export async function changeProviderConnectionLifecycle(
  connectionId: string,
  action: "enable" | "disable" | "archive" | "restore",
  csrfToken: string,
): Promise<ProviderConnection> {
  return ProviderConnectionSchema.parse(await ownerWrite(
    `/api/v1/admin/model-providers/connections/${encodeURIComponent(connectionId)}/${action}`,
    "POST",
    csrfToken,
  ))
}

export async function validateAllProviderModels(
  csrfToken: string,
): Promise<z.infer<typeof ValidateAllResultSchema>> {
  return ValidateAllResultSchema.parse(await ownerWrite(
    "/api/v1/admin/model-providers/model-validations",
    "POST",
    csrfToken,
    undefined,
    { timeout: false },
  ))
}

export async function refreshProviderModels(
  connectionId: string,
  csrfToken: string,
): Promise<z.infer<typeof ModelRefreshSchema>> {
  return ModelRefreshSchema.parse(await ownerWrite(
    `/api/v1/admin/model-providers/connections/${encodeURIComponent(connectionId)}/models/refresh`,
    "POST",
    csrfToken,
  ))
}

export async function addProviderModel(
  connectionId: string,
  model: ProviderModelDraft,
  csrfToken: string,
): Promise<ProviderModel> {
  return ProviderModelSchema.parse(await ownerWrite(
    `/api/v1/admin/model-providers/connections/${encodeURIComponent(connectionId)}/models`,
    "POST",
    csrfToken,
    model,
  ))
}

export async function updateProviderModel(
  connectionId: string,
  modelId: string,
  update: Readonly<Partial<Omit<ProviderModelDraft, "id">> & {
    readonly hidden?: boolean
    readonly retired?: boolean
  }>,
  csrfToken: string,
): Promise<ProviderModel> {
  return ProviderModelSchema.parse(await ownerWrite(
    `/api/v1/admin/model-providers/connections/${encodeURIComponent(connectionId)}/models/${encodeURIComponent(modelId)}`,
    "PATCH",
    csrfToken,
    update,
  ))
}

export async function probeProviderModelCapabilities(
  connectionId: string,
  modelId: string,
  capabilities: readonly ("tools" | "vision" | "reasoning" | "structured_output")[],
  csrfToken: string,
): Promise<z.infer<typeof ProviderCapabilityProbeSchema>> {
  return ProviderCapabilityProbeSchema.parse(await ownerWrite(
    `/api/v1/admin/model-providers/connections/${encodeURIComponent(connectionId)}/models/${encodeURIComponent(modelId)}/capability-probes`,
    "POST",
    csrfToken,
    { capabilities },
  ))
}

export async function listObsoleteProviderModels(
  connectionId: string,
): Promise<readonly ProviderObsoleteModel[]> {
  return ProviderObsoleteModelsSchema.parse(await ownerRead(
    `/api/v1/admin/model-providers/connections/${encodeURIComponent(connectionId)}/models/obsolete`,
  )).items
}

export async function cleanupObsoleteProviderModels(
  connectionId: string,
  modelIds: readonly string[],
  csrfToken: string,
): Promise<ProviderConnection> {
  return ProviderConnectionSchema.parse(await ownerWrite(
    `/api/v1/admin/model-providers/connections/${encodeURIComponent(connectionId)}/models/obsolete/cleanup`,
    "POST",
    csrfToken,
    { model_ids: modelIds },
  ))
}

export async function saveProviderModels(
  connectionId: string,
  models: readonly ProviderModelDraft[],
  csrfToken: string,
): Promise<ProviderConnection> {
  return ProviderConnectionSchema.parse(await ownerWrite(
    `/api/v1/admin/model-providers/connections/${encodeURIComponent(connectionId)}/models`,
    "PUT",
    csrfToken,
    { models },
  ))
}

export async function ownerModelMatrix(): Promise<ModelMatrix> {
  return ModelMatrixSchema.parse(
    await ownerRead("/api/v1/admin/model-providers/model-matrix"),
  )
}

export async function benchmarkProviderModels(
  combinations: readonly BenchmarkCombination[],
  csrfToken: string,
): Promise<z.infer<typeof BenchmarkResultSchema>> {
  return BenchmarkResultSchema.parse(await ownerWrite(
    "/api/v1/admin/model-providers/model-benchmarks",
    "POST",
    csrfToken,
    { combinations },
  ))
}
