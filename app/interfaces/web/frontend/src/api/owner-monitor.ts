import { z } from "zod"

import { adminElfies } from "./admin/elfies"
import { ownerFoods, type FoodCatalog } from "./admin/food-packages"
import { embodimentSessions } from "./admin/embodiment-sessions"
import { ApiError, ownerRead } from "./http"
import { supportedOllamaModelCounts, type SupportedOllamaModelCounts } from "./owner-ollama"
import { setupModelCatalog } from "./setup"

const HealthSchema = z.object({
  status: z.string(),
  engine_ready: z.boolean(),
  godot_web_ready: z.boolean(),
  godot_runtime_ready: z.boolean(),
  instance_id: z.string(),
  generation: z.number().int(),
}).strict()

const ModelExecutionEventSchema = z.object({
  event_type: z.string(),
  status: z.string(),
  subject: z.string(),
  metadata: z.record(z.string(), z.unknown()),
}).passthrough()

const RuntimeStatusSchema = z.object({
  status: z.string(),
  observer: z.object({ event_count: z.number(), last_event: ModelExecutionEventSchema.nullable() }),
  lifecycle: z.object({
    schema_version: z.number().int(),
    instance_id: z.string(),
    generation: z.number().int(),
    revision: z.number().int(),
    tier: z.enum(["offline", "core_ready", "world_ready"]),
    phase: z.string(),
    subphase: z.string(),
    desired_target: z.enum(["core", "world", "normal"]),
    reached_target: z.enum(["core", "world", "normal"]).nullable().optional(),
    components: z.array(z.object({
      component: z.string(),
      state: z.string(),
      detail: z.string(),
      pid: z.number().int().nullable().optional(),
      executable: z.string().nullable().optional(),
      birth_identity: z.string().nullable().optional(),
    }).strict()),
    endpoints: z.array(z.object({
      name: z.string(),
      scheme: z.string(),
      host: z.string(),
      port: z.number().int(),
      protocol_version: z.string(),
    }).strict()),
    model_state: z.enum(["unconfigured", "ready", "degraded", "unavailable"]),
    model_common_state: z.enum(["unconfigured", "ready", "degraded", "unavailable"]),
    model_emergency_state: z.enum(["unconfigured", "ready", "degraded", "unavailable"]),
    model_revision: z.number().int().nullable().optional(),
    failures: z.array(z.object({ code: z.string(), detail: z.string(), phase: z.string() }).strict()),
    timings: z.array(z.object({ phase: z.string(), duration_ms: z.number().int().nullable().optional(), elapsed_ms: z.number().int().nullable().optional() }).strict()),
    protocol_versions: z.array(z.string()),
  }).strict().optional(),
}).strict()

const UserSummarySchema = z.object({
  presence: z.enum(["online", "away", "offline"]),
}).passthrough()

const ElfieSummarySchema = z.object({
  elfie_id: z.string(),
  profile: z.object({
    online_status: z.enum(["online", "offline", "unknown"]),
  }).strict(),
}).strict()

const ProviderModelCountsSchema = z.object({
  total: z.number().int().min(0),
  enabled: z.number().int().min(0),
  in_use: z.number().int().min(0),
  available: z.number().int().min(0),
  degraded: z.number().int().min(0),
  pending: z.number().int().min(0),
  unavailable: z.number().int().min(0),
}).strict()

const RoomSummarySchema = z.object({
  beds: z.array(z.object({ occupant_id: z.string().nullable() }).passthrough()),
}).passthrough()
const RoomListSchema = z.object({ items: z.array(RoomSummarySchema) }).transform(({ items }) => items)

const ProviderSummarySchema = z.object({
  catalog_id: z.string(),
  alias: z.string(),
  enabled: z.boolean(),
  archived: z.boolean(),
  verification: z.object({
    status: z.enum(["never", "passed", "failed"]),
    availability_status: z.enum(["available", "degraded", "unavailable", "unknown"]).optional(),
  }).passthrough(),
  model_counts: ProviderModelCountsSchema,
  models: z.array(z.object({
    available: z.boolean(),
    hidden: z.boolean(),
    retired: z.boolean(),
    discovery_state: z.enum(["present", "source_missing"]).optional(),
    verification: z.object({
      availability_status: z.enum(["available", "degraded", "unavailable", "unknown"]).optional(),
      is_core: z.boolean().optional(),
    }).passthrough().optional(),
  }).passthrough()),
}).passthrough()
const ProviderListSchema = z.object({ items: z.array(ProviderSummarySchema) }).transform(({ items }) => items)

const OllamaStatusSchema = z.object({
  state: z.enum(["unknown", "absent", "healthy", "stopped", "deleted", "installing", "failed", "cancelled", "repair_required"]),
  recommended_model: z.string().nullable(),
  installed_model_count: z.number().int().min(0),
  model_counts: z.object({
    installed: z.number().int().min(0),
    available: z.number().int().min(0),
    degraded: z.number().int().min(0),
    pending: z.number().int().min(0),
    unavailable: z.number().int().min(0),
  }).strict(),
  models: z.array(z.object({
    id: z.string(),
    installed: z.boolean(),
    available: z.boolean().optional(),
    availability_status: z.enum(["available", "degraded", "unavailable", "unknown"]).optional(),
  }).passthrough()),
}).passthrough()

export type MonitorHealth = z.infer<typeof HealthSchema>
export type MonitorRuntimeStatus = z.infer<typeof RuntimeStatusSchema>
export type MonitorUser = z.infer<typeof UserSummarySchema>
export type MonitorElfie = z.infer<typeof ElfieSummarySchema>
export type MonitorRoom = z.infer<typeof RoomSummarySchema>
export type MonitorProvider = z.infer<typeof ProviderSummarySchema>
type MonitorOllamaStatus = z.infer<typeof OllamaStatusSchema>
export type MonitorOllama = MonitorOllamaStatus & {
  readonly supported_model_counts: SupportedOllamaModelCounts | null
}
export type MonitorFood = FoodCatalog["packages"][number]

export const MONITOR_SOURCE_KEYS = ["health", "runtime", "users", "elfies", "rooms", "providers", "ollama", "foods"] as const
export type MonitorSourceKey = (typeof MONITOR_SOURCE_KEYS)[number]
const INTERSTELLAR_PROVIDER_TIMEOUT_MS = 3000

export type MonitorSnapshot = {
  readonly health: MonitorHealth | null
  readonly runtime: MonitorRuntimeStatus | null
  readonly users: readonly MonitorUser[] | null
  readonly elfies: readonly MonitorElfie[] | null
  readonly rooms: readonly MonitorRoom[] | null
  readonly providers: readonly MonitorProvider[] | null
  readonly ollama: MonitorOllama | null
  readonly foods: readonly MonitorFood[] | null
  readonly failedSources: readonly MonitorSourceKey[]
  readonly authRequired: boolean
}

const UserListSchema = z.object({ items: z.array(UserSummarySchema) }).strict()

async function readSchema<Output, Input>(
  path: string,
  schema: z.ZodType<Output, z.ZodTypeDef, Input>,
  options?: { readonly timeout?: number | false },
): Promise<Output> {
  return schema.parse(await ownerRead(path, options))
}

function sourceValue<T>(result: PromiseSettledResult<T>): T | null {
  return result.status === "fulfilled" ? result.value : null
}

function sourceFailed<T>(result: PromiseSettledResult<T>): boolean {
  return result.status === "rejected"
}

function sourceRequiresAuth(result: PromiseSettledResult<unknown>): boolean {
  return result.status === "rejected" && result.reason instanceof ApiError && (result.reason.status === 401 || result.reason.status === 403)
}

export async function loadMonitorSnapshot(
  onProviders?: (providers: readonly MonitorProvider[] | null) => void,
): Promise<MonitorSnapshot> {
  const providerRequest = readSchema(
    "/api/v1/admin/model-providers/connections",
    ProviderListSchema,
    { timeout: INTERSTELLAR_PROVIDER_TIMEOUT_MS },
  ).then(
    (providers) => {
      onProviders?.(providers)
      return providers
    },
    (error: unknown) => {
      onProviders?.(null)
      throw error
    },
  )
  const results = await Promise.allSettled([
    readSchema("/api/health", HealthSchema),
    readSchema("/api/v1/admin/runtime/status", RuntimeStatusSchema),
    readSchema("/api/v1/admin/users", UserListSchema).then(({ items }) => items),
    Promise.all([adminElfies(), embodimentSessions()]).then(([elfies, sessions]) => {
      const stateByElfie = new Map(sessions.map((session) => [session.elfie_id, session.state]))
      return elfies.map((elfie) => ({
        elfie_id: elfie.profile.elfie_id,
        profile: { online_status: onlineStatus(stateByElfie.get(elfie.profile.elfie_id)) },
      }))
    }).then((items) => z.array(ElfieSummarySchema).parse(items)),
    readSchema("/api/v1/admin/nest/rooms", RoomListSchema),
    providerRequest,
    Promise.all([
      readSchema("/api/v1/admin/model-providers/ollama", OllamaStatusSchema),
      setupModelCatalog().then((models) => models.map((model) => model.model_id)).catch(() => null),
    ]).then(([status, supportedModelIds]): MonitorOllama => ({
      ...status,
      supported_model_counts: supportedModelIds === null
        ? null
        : supportedOllamaModelCounts(status, supportedModelIds),
    })),
    ownerFoods().then(({ packages }) => packages),
  ] as const)
  const [health, runtime, users, elfies, rooms, providers, ollama, foods] = results
  const failedSources: MonitorSourceKey[] = []
  if (sourceFailed(health)) failedSources.push("health")
  if (sourceFailed(runtime)) failedSources.push("runtime")
  if (sourceFailed(users)) failedSources.push("users")
  if (sourceFailed(elfies)) failedSources.push("elfies")
  if (sourceFailed(rooms)) failedSources.push("rooms")
  if (sourceFailed(providers)) failedSources.push("providers")
  if (sourceFailed(ollama)) failedSources.push("ollama")
  if (sourceFailed(foods)) failedSources.push("foods")
  const authRequired = results.some(sourceRequiresAuth)
  return {
    health: sourceValue(health),
    runtime: sourceValue(runtime),
    users: sourceValue(users),
    elfies: sourceValue(elfies),
    rooms: sourceValue(rooms),
    providers: sourceValue(providers),
    ollama: sourceValue(ollama),
    foods: sourceValue(foods),
    failedSources,
    authRequired,
  }
}

function onlineStatus(state: string | undefined): "online" | "offline" | "unknown" {
  if (state === "hosted") return "online"
  if (state === "offline") return "offline"
  return "unknown"
}
